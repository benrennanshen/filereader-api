"""工具函数模块，用于处理 Markdown 文本的清理和转换。"""
import re
import logging

logger = logging.getLogger(__name__)


def strip_image_size_attributes(markdown_text: str) -> str:
    """
    去除 pandoc 转换后附在图片后的尺寸属性块 {width="..."}，避免影响后续替换。
    
    Args:
        markdown_text: 包含图片尺寸属性的 Markdown 文本
        
    Returns:
        清理后的 Markdown 文本
    """
    pattern = re.compile(r'(!\[[^\]]*\]\([^)]+\))\s*\{[^}]*\}')
    return pattern.sub(r"\1", markdown_text)


def strip_style_attributes(markdown_text: str) -> str:
    """
    去除 pandoc 转换后生成的样式属性块，如 {.underline}、{.bold}、{color="red"} 等。
    这些属性在表格、文本等元素中可能出现，但 markdown 渲染器通常不支持。
    
    注意：保留表格对齐属性 {.left}、{.right}、{.center}，因为这些对表格有用。
    
    Args:
        markdown_text: 包含样式属性的 Markdown 文本
        
    Returns:
        清理后的 Markdown 文本
    """
    def replace_style(match):
        content = match.group(0)
        # 如果是表格对齐属性，保留
        if re.match(r'\{\.(left|right|center)\}', content):
            return content
        # 如果是表格列对齐属性（在表格定义行中），也保留
        # 例如：|:---|:---:|---:|
        if re.match(r'\{:\.(left|right|center)\}', content):
            return content
        # 其他样式属性，去除
        return ''
    
    # 匹配所有样式属性块 {xxx}，但通过回调函数决定是否保留
    result = re.sub(r'\{[^}]*\}', replace_style, markdown_text)
    
    # 清理可能留下的多余空格（但保留换行）
    # 将多个连续空格替换为单个空格，但保留换行符
    lines = result.split('\n')
    cleaned_lines = [re.sub(r'[ \t]+', ' ', line) for line in lines]
    result = '\n'.join(cleaned_lines)
    
    return result

