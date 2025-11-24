from typing import Any, Dict

from markdownify import markdownify as md


class HtmlToMarkdownHandler:
    """专门负责将 HTML 文本转换为 Markdown 的处理类。"""

    def __init__(self, options: Dict[str, Any] | None = None) -> None:
        # 默认使用 ATX 风格标题（# 号），便于阅读
        default_options: Dict[str, Any] = {
            "heading_style": "ATX",
        }
        self._options = {**default_options, **(options or {})}

    def convert(self, html_text: str) -> str:
        """将 HTML 文本转换为 Markdown 字符串。"""
        if not isinstance(html_text, str):
            raise TypeError("html_text must be a string")

        markdown_text = md(html_text, **self._options)
        return self._normalize_markdown(markdown_text)

    @staticmethod
    def _normalize_markdown(markdown_text: str) -> str:
        """移除首尾多余空行，便于直接复制预览。"""
        return markdown_text.strip()