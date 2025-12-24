import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List
from urllib.parse import urlparse

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from handlers.docx_handler import DocxToMarkdownHandler
from handlers.excel_handler import ExcelToMarkdownHandler
from handlers.html_handler import HtmlToMarkdownHandler
from handlers.pdf_handler import PdfToMarkdownHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


ROOT_PATH = os.getenv("ROOT_PATH", "")

def _get_bool(env_key: str, default: bool) -> bool:
    val = os.getenv(env_key)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "y", "on"}


STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/data/filereader/storage")).resolve()
STORAGE_URL_PREFIX = os.getenv("STORAGE_URL_PREFIX", "http://localhost:8002/static").rstrip("/")
SUBDIR_BY_DATE = _get_bool("SUBDIR_BY_DATE", True)
KEEP_ORIGINAL_NAME = _get_bool("KEEP_ORIGINAL_NAME", False)
INLINE_IMAGE_BASE64 = _get_bool("INLINE_IMAGE_BASE64", False)

app = FastAPI(
    title="FileReader API",
    description="Convert uploaded files to Markdown.",
    root_path=ROOT_PATH,
)

# 挂载静态目录，暴露解析后存储的图片/附件
try:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STORAGE_ROOT)), name="static")
    logger.info(f"静态目录已挂载: /static -> {STORAGE_ROOT}")
except Exception as exc:  # noqa: BLE001
    logger.exception(f"挂载静态目录失败: {exc}")

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50MB，超过此大小使用线程池
HTML_EXTENSIONS = {"html", "htm"}
TEXT_EXTENSIONS = {"txt"}
EXCEL_EXTENSIONS = {"xls", "xlsx"}
PDF_EXTENSIONS = {"pdf"}

html_handler = HtmlToMarkdownHandler()
docx_handler = DocxToMarkdownHandler(
    storage_root=STORAGE_ROOT,
    storage_url_prefix=STORAGE_URL_PREFIX,
    subdir_by_date=SUBDIR_BY_DATE,
    keep_original_name=KEEP_ORIGINAL_NAME,
    inline_image_base64=INLINE_IMAGE_BASE64,
)
excel_handler = ExcelToMarkdownHandler()
pdf_handler = PdfToMarkdownHandler()

# 创建线程池用于CPU密集型任务（大文件转换）
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="convert")


def build_response(http_code: int, data, message: str) -> JSONResponse:
    """统一响应格式构建函数。"""
    return JSONResponse(
        status_code=http_code,
        content={
            "httpCode": http_code,
            "data": data,
            "message": message,
        },
    )


async def _convert_file_content(raw_content: bytes, ext: str, filename: str = "") -> str:
    """统一的文件转换函数，根据文件大小自动选择同步或异步处理。"""
    file_size = len(raw_content)
    file_size_mb = file_size / (1024 * 1024)
    is_large_file = file_size > LARGE_FILE_THRESHOLD
    
    logger.info(f"开始转换文件: {filename}, 类型: {ext}, 大小: {file_size_mb:.2f}MB")
    
    # 对于大文件的DOCX转换，使用线程池避免阻塞事件循环
    if ext == "docx" and is_large_file:
        logger.info(f"大文件检测，使用线程池异步处理: {filename} ({file_size_mb:.2f}MB)")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, docx_handler.convert, raw_content)
        logger.info(f"文件转换完成: {filename}")
        return result
    
    # 其他情况使用同步处理
    if ext in HTML_EXTENSIONS:
        logger.info(f"转换HTML文件: {filename}")
        return _convert_html_bytes(raw_content)
    elif ext == "docx":
        logger.info(f"转换DOCX文件: {filename}")
        result = docx_handler.convert(raw_content)
        logger.info(f"DOCX转换完成: {filename}")
        return result
    elif ext in TEXT_EXTENSIONS:
        logger.info(f"转换TXT文件: {filename}")
        return _convert_text_bytes(raw_content)
    elif ext in EXCEL_EXTENSIONS:
        logger.info(f"转换Excel文件: {filename}")
        return excel_handler.convert(raw_content, ext)
    elif ext in PDF_EXTENSIONS:
        logger.info(f"转换PDF文件: {filename}")
        return pdf_handler.convert(raw_content)
    else:
        logger.error(f"不支持的文件类型: {ext or 'unknown'}, 文件: {filename}")
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")


async def convert_single_file_to_markdown(file: UploadFile) -> str:
    """转换单个文件到 Markdown，返回转换结果字符串。如果转换失败，返回错误信息。"""
    filename = file.filename or ""
    logger.info(f"批量处理 - 开始转换文件: {filename}")

    # 简单根据扩展名判断类型
    ext = ""
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    try:
        raw_content = await file.read()
        if not raw_content:
            logger.warning(f"批量处理 - 文件为空: {filename}")
            return f"文件 {filename} 为空"

        if len(raw_content) > MAX_FILE_SIZE:
            logger.warning(f"批量处理 - 文件超过大小限制: {filename}")
            return f"文件 {filename} 超过大小限制 (200MB)"

        markdown_text = await _convert_file_content(raw_content, ext, filename)
        logger.info(f"批量处理 - 文件转换成功: {filename}")
        return markdown_text

    except ValueError as exc:
        logger.error(f"批量处理 - 文件类型不支持: {filename}, 错误: {exc}")
        return f"文件 {filename} 类型不支持: {exc}"
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"批量处理 - 文件转换失败: {filename}, 错误: {exc}")
        return f"文件 {filename} 转换失败: {exc}"


@app.post(
    "/convert-to-md",
    summary="文档转 Markdown",
    description=(
        "将上传的文件转换为 Markdown 文本。\n\n"
        "- 支持格式：`html` / `htm`、`txt`、`docx`、`xls` / `xlsx`、`pdf`（扫描件会自动 OCR）\n"
        "- 文件大小：统一限制为 200MB，超出会返回 400\n"
        "- 大文件优化：超过 50MB 的文件会自动使用异步处理，避免阻塞\n"
        "- 返回字段：`data` 为 Markdown 字符串，`message` 表示状态"
    ),
)
async def convert_to_markdown(file: UploadFile = File(...)):
    """接受上传文件并将其内容转换为 Markdown。"""
    filename = file.filename or ""
    logger.info(f"收到文件上传请求: {filename}")

    # 简单根据扩展名判断类型
    ext = ""
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    try:
        raw_content = await file.read()
        if not raw_content:
            logger.warning(f"文件为空: {filename}")
            return build_response(400, "", "Empty file")

        if len(raw_content) > MAX_FILE_SIZE:
            logger.warning(f"文件超过大小限制: {filename}, 大小: {len(raw_content) / (1024*1024):.2f}MB")
            return build_response(400, "", "File is too large (limit 200MB)")

        markdown_text = await _convert_file_content(raw_content, ext, filename)
        logger.info(f"文件转换成功: {filename}")
        return build_response(200, markdown_text, "success")

    except ValueError as exc:
        logger.error(f"不支持的文件类型: {filename}, 错误: {exc}")
        return build_response(400, "", f"Unsupported file type: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"文件转换失败: {filename}, 错误: {exc}")
        return build_response(500, "", f"转换失败: {exc}")


@app.get(
    "/download-image",
    summary="下载存储中的图片",
    description="基于转换结果中的图片 URL 下载并回传图片文件。",
)
async def download_image(image_url: str = Query(..., description="图片的原始 URL 或路径")):
    """将 Markdown 中的图片 URL 解析为存储路径并返回文件。"""
    if not image_url:
        return build_response(400, "", "image_url is required")

    try:
        parsed = urlparse(image_url)
        candidate_path = parsed.path if (parsed.scheme or parsed.netloc) else image_url

        storage_prefix_path = urlparse(STORAGE_URL_PREFIX).path.rstrip("/")
        if storage_prefix_path and candidate_path.startswith(storage_prefix_path):
            candidate_path = candidate_path[len(storage_prefix_path) :]
        elif candidate_path.startswith("/static"):
            candidate_path = candidate_path[len("/static") :]

        candidate_path = candidate_path.lstrip("/\\")
        file_path = (STORAGE_ROOT / candidate_path).resolve()

        if not str(file_path).startswith(str(STORAGE_ROOT)):
            logger.warning(f"非法的图片路径: {file_path}")
            return build_response(400, "", "Invalid image path")

        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"图片不存在: {file_path}")
            return build_response(404, "", "Image not found")

        return FileResponse(file_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"下载图片失败: {exc}")
        return build_response(500, "", f"下载图片失败: {exc}")


@app.post(
    "/convert-multiple-to-md",
    summary="批量文档转 Markdown",
    description=(
        "将上传的多个文件批量转换为 Markdown 文本数组。\n\n"
        "- 支持格式：`html` / `htm`、`txt`、`docx`、`xls` / `xlsx`、`pdf`（扫描件会自动 OCR）\n"
        "- 文件大小：每个文件限制为 200MB\n"
        "- 处理方式：并行处理多个文件以提高效率\n"
        "- 返回字段：`data` 为 Markdown 字符串数组（按上传顺序），`message` 表示处理状态"
    ),
)
async def convert_multiple_to_markdown(files: List[UploadFile] = File(...)):
    """接受多个上传文件并将其内容批量转换为 Markdown 数组。"""
    if not files:
        logger.warning("批量转换 - 没有上传文件")
        return build_response(400, [], "没有上传文件")

    logger.info(f"批量转换 - 收到 {len(files)} 个文件")
    try:
        # 使用异步任务并行处理多个文件转换
        tasks = [convert_single_file_to_markdown(file) for file in files]
        results = await asyncio.gather(*tasks)

        logger.info(f"批量转换 - 成功处理 {len(files)} 个文件")
        return build_response(200, results, f"成功处理 {len(files)} 个文件")

    except Exception as exc:  # noqa: BLE001
        logger.exception(f"批量转换失败: {exc}")
        return build_response(500, [], f"批量转换失败: {exc}")


def _convert_html_bytes(raw_content: bytes) -> str:
    # 尝试以 UTF-8 解码，必要时忽略非法字符
    try:
        html_text = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        html_text = raw_content.decode("utf-8", errors="ignore")

    return html_handler.convert(html_text)


def _convert_text_bytes(raw_content: bytes) -> str:
    try:
        text = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_content.decode("utf-8", errors="ignore")
    return text.strip()


# 方便直接运行: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
