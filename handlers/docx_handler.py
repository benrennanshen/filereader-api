from __future__ import annotations

from io import BytesIO
from typing import Dict, List
from uuid import uuid4

import mammoth
from bs4 import BeautifulSoup, Tag

from handlers.html_handler import HtmlToMarkdownHandler

PLACEHOLDER_PREFIX = "__DOCX_TABLE_PLACEHOLDER__"


class DocxToMarkdownHandler:
    """将 DOCX 文档转换为 Markdown 文本的处理类。"""

    def __init__(self, html_handler: HtmlToMarkdownHandler | None = None) -> None:
        self._html_handler = html_handler or HtmlToMarkdownHandler()

    def convert(self, docx_bytes: bytes) -> str:
        if not isinstance(docx_bytes, (bytes, bytearray)):
            raise TypeError("docx_bytes must be bytes")
        if not docx_bytes:
            raise ValueError("docx file is empty")

        html_text = self._docx_to_html(docx_bytes)
        placeholder_map: Dict[str, str] = {}
        cleaned_html = self._preprocess_html(html_text, placeholder_map)
        markdown_text = self._html_handler.convert(cleaned_html)

        for placeholder, table_md in placeholder_map.items():
            markdown_text = markdown_text.replace(placeholder, table_md)

        return markdown_text.strip()

    @staticmethod
    def _docx_to_html(docx_bytes: bytes) -> str:
        with BytesIO(docx_bytes) as buffer:
            result = mammoth.convert_to_html(
                buffer,
            )

        html_text = result.value or ""
        return html_text

    def _preprocess_html(self, html_text: str, placeholder_map: Dict[str, str]) -> str:
        soup = BeautifulSoup(html_text, "html.parser")

        for img in soup.find_all("img"):
            img.decompose()

        for table in soup.find_all("table"):
            placeholder = f"{PLACEHOLDER_PREFIX}{uuid4().hex}"
            markdown_table = self._table_to_markdown(table)
            if markdown_table is None:
                continue

            placeholder_tag = soup.new_tag("p")
            placeholder_tag.string = placeholder
            table.replace_with(placeholder_tag)
            placeholder_map[placeholder] = markdown_table

        return str(soup)

    def _table_to_markdown(self, table: Tag) -> str | None:
        if self._has_merged_cells(table):
            return None

        rows = self._extract_rows(table)
        if not rows:
            return None

        header = rows[0] if self._has_header(table) else None
        body_rows = rows[1:] if header else rows

        column_count = len(rows[0])
        if any(len(row) != column_count for row in rows):
            return None

        markdown_lines: List[str] = []

        if header:
            markdown_lines.append(self._format_row(header))
            markdown_lines.append(self._format_row(["---"] * column_count))

        for row in body_rows:
            markdown_lines.append(self._format_row(row))

        if not header:
            separator = ["---"] * column_count
            markdown_lines.insert(1, self._format_row(separator))

        return "\n".join(markdown_lines)

    @staticmethod
    def _has_header(table: Tag) -> bool:
        return bool(table.find("th"))

    @staticmethod
    def _has_merged_cells(table: Tag) -> bool:
        cell_tags = table.find_all(["td", "th"])
        for cell in cell_tags:
            rowspan = int(cell.get("rowspan", "1") or "1")
            colspan = int(cell.get("colspan", "1") or "1")
            if rowspan > 1 or colspan > 1:
                return True
        return False

    @staticmethod
    def _extract_rows(table: Tag) -> List[List[str]]:
        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row_text = [DocxToMarkdownHandler._cell_text(cell) for cell in cells]
            rows.append(row_text)
        return rows

    @staticmethod
    def _cell_text(cell: Tag) -> str:
        text = cell.get_text(separator=" ", strip=True)
        normalized = " ".join(text.split())
        return normalized

    @staticmethod
    def _format_row(row: List[str]) -> str:
        return "| " + " | ".join(row) + " |"

