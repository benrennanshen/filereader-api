import os

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from handlers.docx_handler import DocxToMarkdownHandler
from handlers.excel_handler import ExcelToMarkdownHandler
from handlers.html_handler import HtmlToMarkdownHandler
from handlers.pdf_handler import PdfToMarkdownHandler


ROOT_PATH = os.getenv("ROOT_PATH", "")

app = FastAPI(
    title="FileReader API",
    description="Convert uploaded files to Markdown.",
    root_path=ROOT_PATH,
)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
HTML_EXTENSIONS = {"html", "htm"}
TEXT_EXTENSIONS = {"txt"}
EXCEL_EXTENSIONS = {"xls", "xlsx"}
PDF_EXTENSIONS = {"pdf"}

html_handler = HtmlToMarkdownHandler()
docx_handler = DocxToMarkdownHandler(html_handler=html_handler)
excel_handler = ExcelToMarkdownHandler()
pdf_handler = PdfToMarkdownHandler()


def build_response(http_code: int, data: str, message: str) -> JSONResponse:
    """统一响应格式构建函数。"""
    return JSONResponse(
        status_code=http_code,
        content={
            "httpCode": http_code,
            "data": data,
            "message": message,
        },
    )


@app.post(
    "/convert-to-md",
    summary="文档转 Markdown",
    description=(
        "将上传的文件转换为 Markdown 文本。\n\n"
        "- 支持格式：`html` / `htm`、`txt`、`docx`、`xls` / `xlsx`、`pdf`（扫描件会自动 OCR）\n"
        "- 文件大小：统一限制为 50MB，超出会返回 400\n"
        "- 返回字段：`data` 为 Markdown 字符串，`message` 表示状态"
    ),
)
async def convert_to_markdown(file: UploadFile = File(...)):
    """接受上传文件并将其内容转换为 Markdown。"""
    filename = file.filename or ""

    # 简单根据扩展名判断类型
    ext = ""
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    try:
        raw_content = await file.read()
        if not raw_content:
            return build_response(400, "", "Empty file")

        if len(raw_content) > MAX_FILE_SIZE:
            return build_response(400, "", "File is too large (limit 50MB)")

        if ext in HTML_EXTENSIONS:
            markdown_text = _convert_html_bytes(raw_content)
        elif ext == "docx":
            markdown_text = docx_handler.convert(raw_content)
        elif ext in TEXT_EXTENSIONS:
            markdown_text = _convert_text_bytes(raw_content)
        elif ext in EXCEL_EXTENSIONS:
            markdown_text = excel_handler.convert(raw_content, ext)
        elif ext in PDF_EXTENSIONS:
            markdown_text = pdf_handler.convert(raw_content)
        else:
            return build_response(400, "", f"Unsupported file type: {ext or 'unknown'}")

        return build_response(200, markdown_text, "success")

    except Exception as exc:  # noqa: BLE001
        # 实际项目中这里建议增加日志记录
        return build_response(500, "", f"转换失败: {exc}")


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
