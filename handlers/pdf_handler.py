from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from typing import List

import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes

MAX_OCR_WORKERS = 4


@dataclass
class PageData:
    index: int
    text: str
    tables: List[List[List[str]]]


class PdfToMarkdownHandler:
    """将 PDF 文档转换为 Markdown（段落 + 表格，图片忽略）。"""

    def __init__(self, ocr_lang: str = "chi_sim+eng") -> None:
        self._ocr_lang = ocr_lang

    def convert(self, pdf_bytes: bytes) -> str:
        if not isinstance(pdf_bytes, (bytes, bytearray)):
            raise TypeError("pdf_bytes must be bytes")
        if not pdf_bytes:
            raise ValueError("PDF file is empty")

        pages = self._extract_with_pdfplumber(pdf_bytes)
        if all(not page.text and not page.tables for page in pages):
            ocr_text = self._extract_with_ocr(pdf_bytes)
            if not ocr_text.strip():
                raise ValueError("未能从 PDF 中提取任何文本")
            return ocr_text.strip()

        markdown_parts: List[str] = []
        for page in pages:
            markdown_parts.append(f"## Page {page.index}")

            if page.text:
                markdown_parts.append(page.text.strip())

            for table in page.tables:
                table_md = self._table_to_markdown(table)
                markdown_parts.append(table_md)

        return "\n\n".join(markdown_parts).strip()

    def _extract_with_pdfplumber(self, pdf_bytes: bytes) -> List[PageData]:
        pages: List[PageData] = []

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                normalized_tables = [self._normalize_table(table) for table in tables if table]
                pages.append(PageData(index=idx, text=text, tables=normalized_tables))

        return pages

    def _extract_with_ocr(self, pdf_bytes: bytes) -> str:
        images = convert_from_bytes(pdf_bytes, fmt="png")
        if not images:
            return ""

        worker_count = min(MAX_OCR_WORKERS, len(images))
        ocr_results: List[str] = [""] * len(images)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self._ocr_image, image, idx): idx for idx, image in enumerate(images)
            }

            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    ocr_results[idx] = future.result()
                except Exception:  # noqa: BLE001
                    ocr_results[idx] = ""

        for image in images:
            image.close()

        filtered = [text for text in ocr_results if text]
        return "\n\n".join(filtered)

    def _ocr_image(self, image, idx: int) -> str:
        text = pytesseract.image_to_string(image, lang=self._ocr_lang)
        cleaned = text.strip()
        return cleaned

    @staticmethod
    def _normalize_table(table: List[List[str | None]]) -> List[List[str]]:
        normalized: List[List[str]] = []
        for row in table:
            normalized.append([PdfToMarkdownHandler._clean_cell(cell) for cell in row])
        return normalized

    @staticmethod
    def _clean_cell(value: str | None) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return " ".join(text.split())

    @staticmethod
    def _table_to_markdown(table: List[List[str]]) -> str:
        if not table:
            return ""

        column_count = max(len(row) for row in table)
        padded_rows = [row + [""] * (column_count - len(row)) for row in table]

        header = padded_rows[0]
        body = padded_rows[1:]

        lines: List[str] = []
        lines.append(PdfToMarkdownHandler._format_row(header))
        lines.append(PdfToMarkdownHandler._format_row(["---"] * column_count))

        for row in body:
            lines.append(PdfToMarkdownHandler._format_row(row))

        if len(padded_rows) == 1:
            lines.append(PdfToMarkdownHandler._format_row(["---"] * column_count))

        return "\n".join(lines)

    @staticmethod
    def _format_row(row: List[str]) -> str:
        return "| " + " | ".join(row) + " |"

