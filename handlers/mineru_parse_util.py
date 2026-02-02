from __future__ import annotations

import logging
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class MinerUParseUtil:
    """使用 MinerU API 进行 PDF 转 Markdown 的工具类"""

    def __init__(
        self,
        api_url: str | None = None,
        timeout: int = 600,
        parse_method: str = "auto",
        backend: str = "hybrid-auto-engine",
        lang_list: str = "ch",
        start_page_id: int = 0,
        end_page_id: int = 99999,
        table_enable: bool = True,
        formula_enable: bool = True,
        return_md: bool = True,
        return_images: bool = True,
        return_content_list: bool = True,
        return_middle_json: bool = False,
        return_model_output: bool = False,
        response_format_zip: bool = True,
    ):
        """
        初始化 MinerU 解析工具
        
        Args:
            api_url: MinerU API 地址，如果为 None 则从环境变量 MINERU_API_URL 读取
            timeout: 请求超时时间（秒），默认 600 秒（10分钟）
            parse_method: 解析方法，默认 "auto"
            backend: 后端引擎，默认 "hybrid-auto-engine"
            lang_list: 语言列表，默认 "ch"
            start_page_id: 起始页码，默认 0
            end_page_id: 结束页码，默认 99999
            table_enable: 是否启用表格解析，默认 True
            formula_enable: 是否启用公式解析，默认 True
            return_md: 是否返回 Markdown，默认 True
            return_images: 是否返回图片，默认 True
            return_content_list: 是否返回内容列表，默认 True
            return_middle_json: 是否返回中间 JSON，默认 False
            return_model_output: 是否返回模型输出，默认 False
            response_format_zip: 响应格式是否为 ZIP，默认 True
        """
        # 从环境变量读取 API URL
        if api_url is None:
            api_url = os.getenv("MINERU_API_URL", "")
        
        if not api_url:
            raise ValueError(
                "MinerU API URL 未配置。请设置环境变量 MINERU_API_URL 或传入 api_url 参数"
            )
        
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.parse_method = parse_method
        self.backend = backend
        self.lang_list = lang_list
        self.start_page_id = start_page_id
        self.end_page_id = end_page_id
        self.table_enable = table_enable
        self.formula_enable = formula_enable
        self.return_md = return_md
        self.return_images = return_images
        self.return_content_list = return_content_list
        self.return_middle_json = return_middle_json
        self.return_model_output = return_model_output
        self.response_format_zip = response_format_zip
        
        logger.info(f"MinerU API 地址: {self.api_url}")

    async def parse_pdf_to_markdown(
        self, pdf_bytes: bytes, filename: str = "document.pdf"
    ) -> str:
        """
        将 PDF 文件转换为 Markdown
        
        Args:
            pdf_bytes: PDF 文件的字节内容
            filename: PDF 文件名（用于上传）
            
        Returns:
            转换后的 Markdown 文本
            
        Raises:
            RuntimeError: 转换失败时抛出
        """
        if not pdf_bytes:
            raise ValueError("PDF 文件为空")
        
        logger.info(f"开始调用 MinerU API 解析 PDF: {filename}, 大小: {len(pdf_bytes) / 1024:.2f} KB")
        
        start_time = time.time()
        
        try:
            # 准备请求参数
            files = {
                "files": (filename, pdf_bytes, "application/pdf")
            }
            
            data = {
                "return_middle_json": str(self.return_middle_json).lower(),
                "return_model_output": str(self.return_model_output).lower(),
                "return_md": str(self.return_md).lower(),
                "return_images": str(self.return_images).lower(),
                "end_page_id": str(self.end_page_id),
                "parse_method": self.parse_method,
                "start_page_id": str(self.start_page_id),
                "lang_list": self.lang_list,
                "output_dir": "./output",
                "server_url": "",
                "return_content_list": str(self.return_content_list).lower(),
                "backend": self.backend,
                "table_enable": str(self.table_enable).lower(),
                "response_format_zip": str(self.response_format_zip).lower(),
                "formula_enable": str(self.formula_enable).lower(),
            }
            
            logger.debug(f"请求参数: {data}")
            logger.info(f"请求 URL: {self.api_url}")
            
            # 发送 HTTP 请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    files=files,
                    data=data,
                )
                
                # 记录响应信息
                elapsed_time = time.time() - start_time
                response_size = len(response.content) if response.content else 0
                
                logger.info(f"MinerU API 请求成功:")
                logger.info(f"  HTTP 状态码: {response.status_code}")
                logger.info(f"  响应大小: {response_size / 1024:.2f} KB ({response_size:,} bytes)")
                logger.info(f"  请求耗时: {elapsed_time:.2f} 秒")
                logger.info(f"  响应类型: {response.headers.get('content-type', 'unknown')}")
                
                response.raise_for_status()
                
                # 处理响应
                if self.response_format_zip:
                    # 如果返回的是 ZIP 文件
                    markdown_text = await self._extract_markdown_from_zip(response.content)
                    logger.info(f"MinerU API 解析完成: Markdown 长度 {len(markdown_text)} 字符")
                    return markdown_text
                else:
                    # 如果返回的是 JSON
                    markdown_text = await self._extract_markdown_from_json(response.json())
                    logger.info(f"MinerU API 解析完成: Markdown 长度 {len(markdown_text)} 字符")
                    return markdown_text
        
        except httpx.HTTPStatusError as e:
            error_msg = f"MinerU API 请求失败: HTTP {e.response.status_code}"
            if e.response.text:
                error_msg += f" - {e.response.text[:500]}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except httpx.TimeoutException:
            error_msg = f"MinerU API 请求超时（>{self.timeout}秒）"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"MinerU API 调用失败: {e}"
            logger.exception(error_msg)
            raise RuntimeError(error_msg) from e

    async def _extract_markdown_from_zip(self, zip_bytes: bytes) -> str:
        """
        从 ZIP 响应中提取 Markdown 内容
        
        Args:
            zip_bytes: ZIP 文件的字节内容
            
        Returns:
            Markdown 文本
        """
        try:
            with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zip_file:
                # 查找 Markdown 文件
                markdown_files = [
                    name for name in zip_file.namelist()
                    if name.endswith(".md") or name.endswith(".markdown")
                ]
                
                if not markdown_files:
                    # 如果没有找到 .md 文件，尝试查找其他文本文件
                    text_files = [
                        name for name in zip_file.namelist()
                        if not name.endswith("/") and not name.endswith(".json")
                    ]
                    if text_files:
                        markdown_files = [text_files[0]]
                
                if not markdown_files:
                    raise ValueError("ZIP 文件中未找到 Markdown 文件")
                
                # 读取第一个 Markdown 文件
                markdown_file = markdown_files[0]
                content = zip_file.read(markdown_file).decode("utf-8")
                
                logger.info(f"从 ZIP 中提取 Markdown:")
                logger.info(f"  文件: {markdown_file}")
                logger.info(f"  内容长度: {len(content)} 字符")
                logger.info(f"  ZIP 文件总数: {len(zip_file.namelist())} 个")
                
                return content
        except zipfile.BadZipFile:
            raise ValueError("响应不是有效的 ZIP 文件")
        except Exception as e:
            raise RuntimeError(f"从 ZIP 提取 Markdown 失败: {e}") from e

    async def _extract_markdown_from_json(self, json_data: dict) -> str:
        """
        从 JSON 响应中提取 Markdown 内容
        
        Args:
            json_data: JSON 响应数据
            
        Returns:
            Markdown 文本
        """
        try:
            # 根据 MinerU API 的响应格式提取 Markdown
            # 这里需要根据实际 API 响应格式调整
            if "markdown" in json_data:
                return json_data["markdown"]
            elif "content" in json_data:
                return json_data["content"]
            elif "result" in json_data:
                result = json_data["result"]
                if isinstance(result, str):
                    return result
                elif isinstance(result, dict) and "markdown" in result:
                    return result["markdown"]
            
            raise ValueError("JSON 响应中未找到 Markdown 内容")
        except Exception as e:
            raise RuntimeError(f"从 JSON 提取 Markdown 失败: {e}") from e
