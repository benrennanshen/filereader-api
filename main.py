import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List
from urllib.parse import urlparse

from fastapi import FastAPI, File, Query, UploadFile, Request, APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from io import BytesIO
from pathlib import Path

from handlers.docx_handler import DocxToMarkdownHandler
from handlers.excel_handler import ExcelToMarkdownHandler
from handlers.html_handler import HtmlToMarkdownHandler
from handlers.pdf_handler import PdfToMarkdownHandler
from handlers.download_handler import MarkdownZipGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def _load_env_file(env_file: str = ".env") -> dict[str, str]:
    """尝试从 .env 文件加载环境变量（如果环境变量未设置）。"""
    env_vars = {}
    env_path = Path(env_file)
    if env_path.exists() and env_path.is_file():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        # 只在环境变量未设置时才使用 .env 的值
                        if key and value and os.getenv(key) is None:
                            env_vars[key] = value
            if env_vars:
                logger.debug(f"从 {env_file} 加载了 {len(env_vars)} 个环境变量")
        except Exception as e:
            logger.warning(f"读取 {env_file} 失败: {e}")
    return env_vars


def _get_env(key: str, default: str = "") -> str:
    """获取环境变量，如果未设置则尝试从 .env 文件读取。"""
    val = os.getenv(key)
    if val is not None:
        return val
    
    # 尝试从 .env 文件读取
    env_vars = _load_env_file()
    return env_vars.get(key, default)


ROOT_PATH = os.getenv("ROOT_PATH", "")

def _get_bool(env_key: str, default: bool) -> bool:
    val = os.getenv(env_key)
    if val is None:
        # 尝试从 .env 文件读取
        env_vars = _load_env_file()
        val = env_vars.get(env_key)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "y", "on"}


STORAGE_ROOT = Path(_get_env("STORAGE_ROOT", "/data/filereader/storage")).resolve()
# 如果 STORAGE_URL_PREFIX 未设置，且 ROOT_PATH 存在，则使用相对路径
_default_storage_url_prefix = _get_env("STORAGE_URL_PREFIX", "")
if not _default_storage_url_prefix:
    # 如果 ROOT_PATH 存在，构建相对路径
    if ROOT_PATH:
        _default_storage_url_prefix = f"{ROOT_PATH.rstrip('/')}/static"
    else:
        _default_storage_url_prefix = "/static"
# 确保相对路径以 / 开头（如果不是绝对URL）
if not _default_storage_url_prefix.startswith(("http://", "https://")) and not _default_storage_url_prefix.startswith("/"):
    _default_storage_url_prefix = "/" + _default_storage_url_prefix
STORAGE_URL_PREFIX = _default_storage_url_prefix.rstrip("/")
SUBDIR_BY_DATE = _get_bool("SUBDIR_BY_DATE", True)
KEEP_ORIGINAL_NAME = _get_bool("KEEP_ORIGINAL_NAME", False)
INLINE_IMAGE_BASE64 = _get_bool("INLINE_IMAGE_BASE64", False)

app = FastAPI(
    title="FileReader API",
    description="Convert uploaded files to Markdown.",
    root_path=ROOT_PATH,
)

# 创建 API 路由器，所有 API 路由使用 /api 前缀
api_router = APIRouter(prefix="/api")

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

# 创建 ZIP 生成器
zip_generator = MarkdownZipGenerator(
    storage_root=STORAGE_ROOT,
    storage_url_prefix=STORAGE_URL_PREFIX,
)

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


@api_router.post(
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


@api_router.get(
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

        # 标准化路径：统一使用正斜杠，并确保有前导斜杠用于匹配
        candidate_path = candidate_path.replace("\\", "/")
        candidate_path_normalized = candidate_path if candidate_path.startswith("/") else "/" + candidate_path

        # 处理 STORAGE_URL_PREFIX：如果是相对路径，直接使用；如果是绝对URL，提取路径部分
        if STORAGE_URL_PREFIX.startswith(("http://", "https://")):
            storage_prefix_path = urlparse(STORAGE_URL_PREFIX).path.rstrip("/")
        else:
            # 相对路径，直接使用
            storage_prefix_path = STORAGE_URL_PREFIX.rstrip("/")
        
        # 标准化storage_prefix_path，确保有前导斜杠
        if storage_prefix_path and not storage_prefix_path.startswith("/"):
            storage_prefix_path = "/" + storage_prefix_path
        
        # 尝试匹配并去掉前缀（支持有/无前导斜杠的情况）
        if storage_prefix_path:
            # 尝试匹配带前导斜杠的路径
            if candidate_path_normalized.startswith(storage_prefix_path):
                candidate_path = candidate_path_normalized[len(storage_prefix_path):]
            # 尝试匹配不带前导斜杠的路径（去掉storage_prefix_path的前导斜杠）
            elif storage_prefix_path.startswith("/") and candidate_path.startswith(storage_prefix_path[1:]):
                candidate_path = candidate_path[len(storage_prefix_path[1:]):]
            # 尝试匹配原始candidate_path（可能没有前导斜杠）
            elif candidate_path.startswith(storage_prefix_path.lstrip("/")):
                candidate_path = candidate_path[len(storage_prefix_path.lstrip("/")):]
        
        # 如果还有/static前缀，也去掉
        if candidate_path.startswith("/static"):
            candidate_path = candidate_path[len("/static"):]
        elif candidate_path.startswith("static/"):
            candidate_path = candidate_path[len("static/"):]

        # 清理路径：去掉前导的斜杠和反斜杠
        candidate_path = candidate_path.lstrip("/\\")
        
        # 构建文件路径
        file_path = (STORAGE_ROOT / candidate_path).resolve()

        # 安全检查：确保文件路径在STORAGE_ROOT内
        if not str(file_path).startswith(str(STORAGE_ROOT.resolve())):
            logger.warning(f"非法的图片路径: {file_path} (不在存储根目录 {STORAGE_ROOT} 内)")
            return build_response(400, "", "Invalid image path")

        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"图片不存在: {file_path}")
            return build_response(404, "", "Image not found")

        return FileResponse(file_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"下载图片失败: {exc}")
        return build_response(500, "", f"下载图片失败: {exc}")


@api_router.post(
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


@api_router.post(
    "/download-markdown-zip",
    summary="下载 Markdown 和图片的 ZIP 包",
    description=(
        "根据提供的 Markdown 内容，提取其中的图片 URL，"
        "收集所有图片文件，生成包含 Markdown 文件和图片文件夹的 ZIP 包。\n\n"
        "- 请求体：JSON 对象，包含 `markdown_content` 和可选的 `filename`\n"
        "- 返回：ZIP 文件流，包含 `document.md` 和 `images/` 文件夹\n"
        "- 图片路径：ZIP 中的 Markdown 文件使用相对路径引用图片\n"
        "- 文件名：如果提供了原始文件名，ZIP 包名称将使用文件名+时间戳"
    ),
)
async def download_markdown_zip(
    request_data: dict = Body(..., description="包含 markdown_content 和 filename 的 JSON 对象")
):
    """生成包含 Markdown 文件和关联图片的 ZIP 包"""
    # 支持两种格式：直接传字符串（向后兼容）或传 JSON 对象
    if isinstance(request_data, str):
        markdown_content = request_data
        filename = ""
    else:
        markdown_content = request_data.get("markdown_content", "")
        filename = request_data.get("filename", "")

    if not markdown_content:
        logger.warning("下载 ZIP - Markdown 内容为空")
        return build_response(400, "", "Markdown content is required")

    try:
        logger.info(f"开始生成 Markdown ZIP 包，原始文件名: {filename or '未提供'}")
        
        # 生成 ZIP 包内的 md 文件名（使用原始文件名）
        md_filename = filename if filename else "document.md"
        if md_filename and not md_filename.lower().endswith('.md'):
            # 如果原始文件名没有 .md 扩展名，添加它
            from pathlib import Path
            md_filename = f"{Path(md_filename).stem}.md"
        
        # 使用线程池执行 ZIP 生成（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        zip_buffer = await loop.run_in_executor(
            executor, zip_generator.generate_zip, markdown_content, md_filename
        )

        # 获取 ZIP 包文件名（仅使用时间戳）
        zip_filename = zip_generator.get_zip_filename()

        # 读取 BytesIO 的所有内容
        zip_data = zip_buffer.read()
        zip_buffer.close()

        # 处理文件名编码，支持中文等非 ASCII 字符
        # 使用 RFC 5987 格式：filename*=UTF-8''encoded_filename
        try:
            from urllib.parse import quote
            # 对文件名进行 URL 编码
            encoded_filename = quote(zip_filename.encode('utf-8'), safe='')
            content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"
            # 同时提供 ASCII 回退版本（用于兼容旧浏览器）
            try:
                ascii_filename = zip_filename.encode('ascii', 'ignore').decode('ascii')
                if not ascii_filename:
                    ascii_filename = 'download.zip'
            except Exception:
                ascii_filename = 'download.zip'
            content_disposition += f"; filename=\"{ascii_filename}\""
        except Exception as e:
            logger.warning(f"文件名编码处理失败: {e}，使用默认文件名")
            # 如果编码失败，使用安全的 ASCII 文件名
            safe_filename = zip_filename.encode('ascii', 'ignore').decode('ascii') or 'download.zip'
            content_disposition = f"attachment; filename=\"{safe_filename}\""

        logger.info(f"ZIP 包生成成功: {zip_filename}, 大小: {len(zip_data) / 1024:.2f}KB")
        return Response(
            content=zip_data,
            media_type="application/zip",
            headers={"Content-Disposition": content_disposition},
        )

    except ValueError as exc:
        logger.error(f"下载 ZIP - 参数错误: {exc}")
        return build_response(400, "", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"生成 ZIP 包失败: {exc}")
        return build_response(500, "", f"生成 ZIP 包失败: {exc}")


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


# 注册 API 路由器
app.include_router(api_router)

# 前端静态文件目录（构建后的 dist 目录）
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
FRONTEND_DIST = FRONTEND_DIST.resolve()

# 挂载前端静态文件（必须在所有路由之后，确保 API 路由优先）
if FRONTEND_DIST.exists() and FRONTEND_DIST.is_dir():
    try:
        # 根据 ROOT_PATH 确定前端挂载路径
        frontend_base = ROOT_PATH.rstrip("/") if ROOT_PATH else ""
        
        # 挂载静态资源（JS、CSS、图片等）
        # 同时挂载到根路径和 ROOT_PATH 路径，以支持不同的部署方式
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")
        if frontend_base:
            # 如果设置了 ROOT_PATH，也挂载到该路径下
            assets_path = f"{frontend_base}/assets"
            app.mount(assets_path, StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets-prefixed")
        logger.info(f"前端静态资源已挂载: /assets" + (f" 和 {frontend_base}/assets" if frontend_base else "") + f" -> {FRONTEND_DIST / 'assets'}")
        
        # SPA 路由处理：所有非 API 路径返回 index.html
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(request: Request, full_path: str):
            """处理 SPA 路由，所有非 API 路径返回 index.html"""
            # 如果设置了 ROOT_PATH，需要处理带前缀的路径
            original_path = full_path
            if frontend_base:
                base_stripped = frontend_base.lstrip("/")
                if full_path.startswith(base_stripped + "/") or full_path == base_stripped:
                    full_path = full_path[len(base_stripped):].lstrip("/")
            
            # 排除 API 路径和静态资源路径
            if full_path.startswith(("api/", "static/", "assets/", "docs", "openapi.json", "redoc")):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            
            # 排除根路径下的 API 文档路径
            if full_path in ("docs", "redoc", "openapi.json"):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            
            # 检查是否是静态文件请求
            static_file = FRONTEND_DIST / full_path
            if static_file.exists() and static_file.is_file():
                return FileResponse(static_file)
            
            # 如果请求的是 ROOT_PATH 本身或 ROOT_PATH/index.html，返回 index.html
            if (frontend_base and (original_path == frontend_base.lstrip("/") or original_path == frontend_base.lstrip("/") + "/index.html")) or \
               (not frontend_base and (full_path == "" or full_path == "index.html")):
                index_file = FRONTEND_DIST / "index.html"
                if index_file.exists():
                    return FileResponse(index_file)
            
            # 其他路径返回 index.html（SPA 路由）
            index_file = FRONTEND_DIST / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            
            return JSONResponse(status_code=404, content={"detail": "Frontend not found"})
        
        logger.info(f"前端 SPA 路由已配置: {FRONTEND_DIST}, base path: {frontend_base or '/'}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"挂载前端静态文件失败: {exc}，前端可能未构建")
else:
    logger.info(f"前端构建目录不存在: {FRONTEND_DIST}，跳过前端静态文件服务")


# 方便直接运行: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
