from __future__ import annotations

import base64
import logging
import re
from io import BytesIO
from typing import Dict, List
from uuid import uuid4

import mammoth
from bs4 import BeautifulSoup, Tag
from docx import Document

from handlers.html_handler import HtmlToMarkdownHandler

logger = logging.getLogger(__name__)

PLACEHOLDER_PREFIX = "__DOCX_TABLE_PLACEHOLDER__"

# 尝试使用lxml解析器（更快），如果不可用则回退到html.parser
try:
    import lxml  # noqa: F401
    HTML_PARSER = "lxml"
except ImportError:
    HTML_PARSER = "html.parser"


class DocxToMarkdownHandler:
    """将 DOCX 文档转换为 Markdown 文本的处理类。"""

    def __init__(self, html_handler: HtmlToMarkdownHandler | None = None) -> None:
        self._html_handler = html_handler or HtmlToMarkdownHandler()

    def convert(self, docx_bytes: bytes) -> str:
        if not isinstance(docx_bytes, (bytes, bytearray)):
            raise TypeError("docx_bytes must be bytes")
        if not docx_bytes:
            raise ValueError("docx file is empty")

        logger.info(f"开始DOCX转换，文件大小: {len(docx_bytes) / (1024*1024):.2f}MB")
        
        # 使用python-docx提取表格
        tables_from_docx = self._extract_tables_with_python_docx(docx_bytes)
        logger.info(f"使用python-docx提取到 {len(tables_from_docx)} 个表格")
        
        html_text = self._docx_to_html(docx_bytes)
        logger.debug(f"DOCX转HTML完成，HTML长度: {len(html_text)}")
        
        # 使用HTML注释方案：直接在HTML中替换表格为注释包裹的Markdown内容
        cleaned_html = self._replace_tables_with_comments(html_text, tables_from_docx)
        logger.info("表格替换完成")
        
        # 转换为Markdown（HTML注释会被markdownify保留）
        markdown_text = self._html_handler.convert(cleaned_html)
        
        # 提取HTML注释中的表格内容并替换
        markdown_text = self._extract_tables_from_comments(markdown_text)
        
        logger.info("DOCX转换完成")
        return markdown_text.strip()

    def _docx_to_html(self, docx_bytes: bytes) -> str:
        """将 DOCX 转换为 HTML，同时提取图片并转换为 base64。"""
        def convert_image(image):
            """处理图片：转换为 base64 并返回 data URI。"""
            try:
                with image.open() as image_bytes:
                    image_data = image_bytes.read()
                
                # 将图片转换为 base64
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                
                # 构建 data URI
                content_type = image.content_type or "image/png"
                image_url = f"data:{content_type};base64,{image_base64}"
                
                return {"src": image_url}
            except Exception:
                # 图片处理失败时返回占位符
                return {"src": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}

        try:
            with BytesIO(docx_bytes) as buffer:
                result = mammoth.convert_to_html(
                    buffer,
                    convert_image=mammoth.images.img_element(convert_image)
                )
            
            html_text = result.value or ""
            # 记录警告信息用于调试
            if result.messages:
                logger.warning(f"DOCX转换警告: {len(result.messages)} 条")
                for msg in result.messages[:5]:  # 只记录前5条警告
                    logger.debug(f"  - {msg}")
            
            logger.debug(f"DOCX转HTML完成，HTML长度: {len(html_text)}")
            return html_text
        except Exception as exc:
            logger.exception(f"DOCX转HTML失败: {exc}")
            raise ValueError(f"Failed to convert DOCX to HTML: {exc}") from exc

    def _extract_tables_with_python_docx(self, docx_bytes: bytes) -> List[str]:
        """使用python-docx直接提取表格并转换为Markdown。"""
        tables_markdown = []
        try:
            doc = Document(BytesIO(docx_bytes))
            logger.debug(f"使用python-docx解析文档，发现 {len(doc.tables)} 个表格")
            
            for idx, table in enumerate(doc.tables, 1):
                try:
                    table_md = self._convert_docx_table_to_markdown(table)
                    if table_md:
                        tables_markdown.append(table_md)
                        logger.debug(f"表格 {idx} 转换成功")
                    else:
                        logger.warning(f"表格 {idx} 转换失败")
                        tables_markdown.append(None)  # 占位，保持索引一致
                except Exception as exc:
                    logger.exception(f"表格 {idx} 转换异常: {exc}")
                    tables_markdown.append(None)
        except Exception as exc:
            logger.exception(f"python-docx提取表格失败: {exc}")
            return []
        
        return tables_markdown

    def _convert_docx_table_to_markdown(self, table) -> str | None:
        """将python-docx的表格对象转换为Markdown格式。"""
        try:
            if not table.rows:
                return None
            
            # 构建表格矩阵来处理合并单元格
            rows_data = []
            max_cols = 0
            total_cell_length = 0  # 统计总单元格内容长度
            
            # 第一遍：收集所有单元格数据
            for row in table.rows:
                row_data = []
                for cell in row.cells:
                    # 提取单元格文本，清理空白
                    cell_text = " ".join(cell.text.split())
                    row_data.append(cell_text)
                    total_cell_length += len(cell_text)
                rows_data.append(row_data)
                max_cols = max(max_cols, len(row_data))
            
            if max_cols == 0:
                return None
            
            # 判断表格复杂度
            is_complex = False
            max_cell_length = 0
            
            # 检查是否有单列内容过长
            for row_data in rows_data:
                for cell_text in row_data:
                    max_cell_length = max(max_cell_length, len(cell_text))
                    # 如果单个单元格超过200字符，认为是复杂表格
                    if len(cell_text) > 200:
                        is_complex = True
                        break
                if is_complex:
                    break
            
            # 如果总内容超过2000字符，也认为是复杂表格
            if total_cell_length > 2000:
                is_complex = True
            
            # 如果表格行数或列数过多，也可能是复杂表格
            if len(rows_data) > 20 or max_cols > 10:
                is_complex = True
            
            if is_complex:
                # 使用文本格式，更易读
                logger.debug(f"检测到复杂表格（总长度: {total_cell_length}, 最大单元格: {max_cell_length}），使用文本格式")
                return self._format_table_as_text(rows_data, max_cols)
            
            # 简单表格，使用Markdown格式
            # 统一所有行的列数
            normalized_rows = []
            for row_data in rows_data:
                normalized_row = row_data + [""] * (max_cols - len(row_data))
                normalized_rows.append(normalized_row[:max_cols])
            
            # 检查是否有表头（第一行通常是表头）
            has_header = len(normalized_rows) > 0
            
            # 构建Markdown表格
            markdown_lines = []
            if has_header and len(normalized_rows) > 0:
                markdown_lines.append(DocxToMarkdownHandler._format_row(normalized_rows[0]))
                markdown_lines.append(DocxToMarkdownHandler._format_row(["---"] * max_cols))
                for row in normalized_rows[1:]:
                    markdown_lines.append(DocxToMarkdownHandler._format_row(row))
            else:
                if normalized_rows:
                    markdown_lines.append(DocxToMarkdownHandler._format_row(normalized_rows[0]))
                    markdown_lines.append(DocxToMarkdownHandler._format_row(["---"] * max_cols))
                    for row in normalized_rows[1:]:
                        markdown_lines.append(DocxToMarkdownHandler._format_row(row))
            
            return "\n".join(markdown_lines)
        except Exception as exc:
            logger.exception(f"转换DOCX表格异常: {exc}")
            return None

    @staticmethod
    def _format_table_as_text(rows_data: List[List[str]], max_cols: int) -> str:
        """将表格格式化为易读的文本格式（用于复杂表格）。"""
        lines = []
        lines.append("\n" + "=" * 80)
        lines.append("【表格内容】")
        lines.append("=" * 80)
        
        for idx, row_data in enumerate(rows_data, 1):
            lines.append(f"\n第 {idx} 行：")
            normalized_row = row_data + [""] * (max_cols - len(row_data))
            for col_idx, cell_text in enumerate(normalized_row[:max_cols], 1):
                if cell_text.strip():
                    # 如果单元格内容很长，换行显示
                    if len(cell_text) > 100:
                        lines.append(f"  列 {col_idx}:")
                        # 每100字符换行
                        for i in range(0, len(cell_text), 100):
                            lines.append(f"    {cell_text[i:i+100]}")
                    else:
                        lines.append(f"  列 {col_idx}: {cell_text}")
        
        lines.append("\n" + "=" * 80 + "\n")
        return "\n".join(lines)

    def _replace_tables_with_comments(self, html_text: str, tables_from_docx: List[str] | None = None) -> str:
        """使用HTML注释方案：直接在HTML中替换表格为注释包裹的Markdown内容。"""
        soup = BeautifulSoup(html_text, HTML_PARSER)
        tables = soup.find_all("table")
        logger.info(f"发现 {len(tables)} 个表格需要处理")
        
        # 优先使用python-docx提取的表格
        use_python_docx = tables_from_docx and len(tables_from_docx) == len(tables)
        
        if use_python_docx:
            logger.info("使用python-docx提取的表格数据")
        
        for idx, table in enumerate(tables, 1):
            logger.debug(f"处理表格 {idx}/{len(tables)}")
            
            # 优先使用python-docx提取的表格
            if use_python_docx and idx <= len(tables_from_docx):
                table_md = tables_from_docx[idx - 1]
                if table_md:
                    # 使用HTML注释包裹表格内容
                    self._replace_table_with_comment(soup, table, table_md)
                    logger.debug(f"表格 {idx} 使用python-docx数据")
                    continue
            
            # 回退到HTML解析
            table_md = self._table_to_markdown(table)
            if table_md is None:
                # 表格转换失败，使用后备文本
                logger.warning(f"表格 {idx} 转换失败，使用后备方案")
                fallback_text = self._extract_table_fallback(table)
                if fallback_text:
                    self._replace_table_with_comment(soup, table, fallback_text)
                    logger.debug(f"表格 {idx} 使用后备文本")
                else:
                    logger.warning(f"表格 {idx} 后备提取也失败，跳过")
                continue

            # 表格转换成功
            self._replace_table_with_comment(soup, table, table_md)
            logger.debug(f"表格 {idx} 转换成功")

        return str(soup)

    @staticmethod
    def _replace_table_with_comment(soup: BeautifulSoup, table: Tag, markdown_content: str) -> None:
        """使用HTML注释包裹表格的Markdown内容，markdownify不会处理注释。"""
        # 使用HTML注释包裹，markdownify会保留注释内容
        # 格式：<!-- TABLE_MARKDOWN_START -->\n内容\n<!-- TABLE_MARKDOWN_END -->
        # 直接使用字符串创建注释，BeautifulSoup会正确处理
        comment_text = f"<!-- TABLE_MARKDOWN_START -->\n{markdown_content}\n<!-- TABLE_MARKDOWN_END -->"
        comment_node = soup.new_string(comment_text)
        table.replace_with(comment_node)

    def _extract_tables_from_comments(self, markdown_text: str) -> str:
        """从Markdown中提取HTML注释中的表格内容。"""
        # 使用更宽松的正则表达式，匹配各种可能的格式
        patterns = [
            # 标准格式：有换行
            r'<!--\s*TABLE_MARKDOWN_START\s*-->\s*\n(.*?)\n\s*<!--\s*TABLE_MARKDOWN_END\s*-->',
            # 可能没有换行
            r'<!--\s*TABLE_MARKDOWN_START\s*-->(.*?)<!--\s*TABLE_MARKDOWN_END\s*-->',
            # 可能有多个换行或空格
            r'<!--\s*TABLE_MARKDOWN_START\s*-->[\s\n]*(.*?)[\s\n]*<!--\s*TABLE_MARKDOWN_END\s*-->',
        ]
        
        result = markdown_text
        extracted_count = 0
        
        # 尝试不同的模式
        for pattern_str in patterns:
            pattern = re.compile(pattern_str, re.DOTALL)
            matches = pattern.findall(result)
            if matches:
                def replace_comment(match):
                    nonlocal extracted_count
                    table_content = match.group(1).strip()
                    extracted_count += 1
                    logger.debug(f"从注释中提取表格内容，长度: {len(table_content)}")
                    return table_content
                
                result = pattern.sub(replace_comment, result)
                logger.info(f"使用模式提取了 {len(matches)} 个表格")
                break  # 如果匹配到了，就不需要尝试其他模式
        
        # 如果还有注释残留，尝试最宽松的匹配
        if 'TABLE_MARKDOWN_START' in result:
            logger.warning("仍有表格注释未提取，尝试最宽松的匹配")
            # 提取所有在注释之间的内容（不限制格式）
            loose_pattern = re.compile(
                r'<!--[^>]*TABLE_MARKDOWN_START[^>]*-->([\s\S]*?)<!--[^>]*TABLE_MARKDOWN_END[^>]*-->',
                re.DOTALL
            )
            loose_matches = loose_pattern.findall(result)
            if loose_matches:
                result = loose_pattern.sub(lambda m: m.group(1).strip(), result)
                logger.info(f"使用宽松模式提取了 {len(loose_matches)} 个表格")
        
        # 最终检查
        if 'TABLE_MARKDOWN_START' in result:
            logger.warning("仍有表格注释未提取，可能格式异常")
        
        return result



    @staticmethod
    def _extract_table_fallback(table: Tag) -> str:
        """提取表格为后备文本格式（用于复杂表格）。"""
        # 尝试更详细的表格提取
        rows_text = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if cells:
                row_data = []
                for cell in cells:
                    cell_text = DocxToMarkdownHandler._cell_text(cell)
                    # 检查合并信息
                    colspan = int(cell.get("colspan", "1") or "1")
                    rowspan = int(cell.get("rowspan", "1") or "1")
                    if colspan > 1 or rowspan > 1:
                        cell_text += f" [跨{colspan}列{rowspan}行]" if rowspan > 1 else f" [跨{colspan}列]"
                    row_data.append(cell_text)
                rows_text.append(" | ".join(row_data))
        
        if not rows_text:
            table_text = table.get_text(separator=" | ", strip=True)
            if not table_text:
                return ""
            return f"\n\n[表格内容]\n{table_text}\n\n"
        
        # 检查是否有合并单元格
        has_merged = any(
            int(cell.get("rowspan", "1") or "1") > 1 or int(cell.get("colspan", "1") or "1") > 1
            for cell in table.find_all(["td", "th"])
        )
        
        prefix = "[表格内容 - 包含合并单元格]" if has_merged else "[表格内容]"
        table_content = "\n".join(rows_text)
        return f"\n\n{prefix}\n{table_content}\n\n"

    def _table_to_markdown(self, table: Tag) -> str | None:
        """将表格转换为Markdown格式，支持合并单元格。"""
        try:
            # 尝试提取表格行（包括合并单元格）
            rows = self._extract_rows_with_merged_cells(table)
            if not rows:
                logger.debug("表格提取失败：没有提取到行数据")
                return None

            # 获取最大列数
            max_column_count = max(len(row) for row in rows) if rows else 0
            if max_column_count == 0:
                logger.debug("表格提取失败：最大列数为0")
                return None

            # 统一所有行的列数
            normalized_rows = self._normalize_rows(rows, max_column_count)

            # 构建Markdown表格
            result = self._build_markdown_table(normalized_rows, self._has_header(table))
            if result:
                logger.debug(f"表格转换成功：{len(rows)} 行 x {max_column_count} 列")
            return result
        except Exception as exc:
            logger.exception(f"表格转换异常: {exc}")
            return None

    def _extract_rows_with_merged_cells(self, table: Tag) -> List[List[str]]:
        """提取表格行，尝试处理合并单元格。"""
        tr_tags = table.find_all("tr")
        if not tr_tags:
            return []

        # 计算实际列数（考虑合并单元格）
        max_cols = self._calculate_max_columns(tr_tags)
        if max_cols == 0:
            return []

        # 构建表格矩阵来处理合并单元格
        table_matrix = [[""] * max_cols for _ in range(len(tr_tags))]
        
        for row_idx, tr in enumerate(tr_tags):
            col_idx = 0
            cells = tr.find_all(["td", "th"])
            
            for cell in cells:
                # 跳过已被占用的列
                while col_idx < max_cols and table_matrix[row_idx][col_idx] != "":
                    col_idx += 1
                
                if col_idx >= max_cols:
                    break

                cell_text = self._cell_text(cell)
                colspan = int(cell.get("colspan", "1") or "1")
                rowspan = int(cell.get("rowspan", "1") or "1")

                # 填充当前单元格
                table_matrix[row_idx][col_idx] = cell_text

                # 处理跨列：标记后续列为已占用（用特殊标记）
                for c in range(1, colspan):
                    if col_idx + c < max_cols:
                        table_matrix[row_idx][col_idx + c] = None  # 标记为合并单元格

                # 处理跨行：标记后续行的所有对应列为已占用
                for r in range(1, rowspan):
                    if row_idx + r < len(table_matrix):
                        # 标记所有被合并的列
                        for c in range(colspan):
                            if col_idx + c < max_cols:
                                table_matrix[row_idx + r][col_idx + c] = None

                col_idx += colspan

        # 将矩阵转换为行列表，处理合并单元格标记
        rows = []
        for row in table_matrix:
            processed_row = []
            for cell in row:
                if cell is None:
                    processed_row.append("")  # 合并单元格位置留空
                elif cell != "":
                    processed_row.append(cell)
            if processed_row:  # 只添加非空行
                rows.append(processed_row)

        return rows if rows else self._extract_rows_simple(table)

    @staticmethod
    def _calculate_max_columns(tr_tags: List[Tag]) -> int:
        """计算表格的最大列数（考虑合并单元格）。"""
        max_cols = 0
        for tr in tr_tags:
            cells = tr.find_all(["td", "th"])
            col_count = 0
            for cell in cells:
                colspan = int(cell.get("colspan", "1") or "1")
                col_count += colspan
            max_cols = max(max_cols, col_count)
        return max_cols

    @staticmethod
    def _extract_rows_simple(table: Tag) -> List[List[str]]:
        """简单提取表格行（不处理合并单元格，作为后备方案）。"""
        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row_text = [DocxToMarkdownHandler._cell_text(cell) for cell in cells]
            rows.append(row_text)
        return rows

    @staticmethod
    def _normalize_rows(rows: List[List[str]], max_cols: int) -> List[List[str]]:
        """统一所有行的列数。"""
        normalized = []
        for row in rows:
            normalized_row = row + [""] * (max_cols - len(row))
            normalized.append(normalized_row[:max_cols])
        return normalized

    @staticmethod
    def _build_markdown_table(normalized_rows: List[List[str]], has_header: bool) -> str:
        """构建Markdown表格字符串。"""
        if not normalized_rows:
            return None

        markdown_lines: List[str] = []
        max_cols = len(normalized_rows[0]) if normalized_rows else 0

        if has_header and len(normalized_rows) > 0:
            markdown_lines.append(DocxToMarkdownHandler._format_row(normalized_rows[0]))
            markdown_lines.append(DocxToMarkdownHandler._format_row(["---"] * max_cols))
            for row in normalized_rows[1:]:
                markdown_lines.append(DocxToMarkdownHandler._format_row(row))
        else:
            # 没有表头，第一行后添加分隔行
            markdown_lines.append(DocxToMarkdownHandler._format_row(normalized_rows[0]))
            markdown_lines.append(DocxToMarkdownHandler._format_row(["---"] * max_cols))
            for row in normalized_rows[1:]:
                markdown_lines.append(DocxToMarkdownHandler._format_row(row))

        return "\n".join(markdown_lines)

    @staticmethod
    def _has_header(table: Tag) -> bool:
        return bool(table.find("th"))


    @staticmethod
    def _cell_text(cell: Tag) -> str:
        text = cell.get_text(separator=" ", strip=True)
        normalized = " ".join(text.split())
        return normalized

    @staticmethod
    def _format_row(row: List[str]) -> str:
        return "| " + " | ".join(row) + " |"

