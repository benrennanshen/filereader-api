from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)


class LibreOfficeConverter:
    """使用 LibreOffice 将 Office 文件转换为 PDF 的工具类"""

    def __init__(self, timeout: int = 120, pdf_save_dir: str | Path | None = None):
        """
        初始化转换器
        
        Args:
            timeout: 转换超时时间（秒），默认 120 秒
            pdf_save_dir: PDF 文件保存目录，如果为 None 则从环境变量读取，默认 /fskj/workspace/filereaderapi/file_parse
        """
        self.timeout = timeout
        self._check_libreoffice_available()
        
        # 设置PDF保存目录
        if pdf_save_dir is None:
            pdf_save_dir = os.getenv("PDF_SAVE_DIR", "/fskj/workspace/filereaderapi/file_parse")
        
        self._pdf_save_dir = Path(pdf_save_dir)
        # 确保目录存在
        self._pdf_save_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"PDF 文件保存目录: {self._pdf_save_dir}")

    def _check_libreoffice_available(self) -> None:
        """检查 LibreOffice 是否已安装并可用"""
        try:
            result = subprocess.run(
                ["libreoffice", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                logger.info(f"LibreOffice 已安装: {version}")
            else:
                raise RuntimeError("LibreOffice 未正确安装")
        except FileNotFoundError:
            raise RuntimeError(
                "LibreOffice 未安装。请先安装 LibreOffice: "
                "apt-get install -y libreoffice libreoffice-writer"
            )
        except Exception as e:
            raise RuntimeError(f"检查 LibreOffice 失败: {e}")

    def convert_docx_to_pdf(self, docx_bytes: bytes) -> bytes:
        """
        将 DOCX 文件字节内容转换为 PDF 字节内容
        
        Args:
            docx_bytes: DOCX 文件的字节内容
            
        Returns:
            转换后的 PDF 文件的字节内容
            
        Raises:
            RuntimeError: 转换失败时抛出
        """
        if not isinstance(docx_bytes, (bytes, bytearray)):
            raise TypeError("docx_bytes must be bytes")
        if not docx_bytes:
            raise ValueError("DOCX file is empty")

        logger.info(f"开始 DOCX 转 PDF，文件大小: {len(docx_bytes) / (1024*1024):.2f}MB")

        # 创建临时文件保存 docx 内容
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(docx_bytes)
            tmp_docx_path = tmp_docx.name

        try:
            # 使用临时目录进行转换（避免 Docker 挂载卷写入问题）
            with tempfile.TemporaryDirectory(prefix="libreoffice_") as temp_dir:
                temp_dir_path = Path(temp_dir)

                # 复制输入文件到临时目录
                temp_input = temp_dir_path / Path(tmp_docx_path).name
                shutil.copy2(tmp_docx_path, temp_input)

                # 构建 LibreOffice 转换命令
                cmd = [
                    "libreoffice",
                    "--headless",  # 无界面模式
                    "--convert-to",
                    "pdf",  # 转换为 PDF
                    "--outdir",
                    str(temp_dir_path),  # 输出到临时目录
                    str(temp_input),  # 输入文件
                ]

                logger.debug(f"执行 LibreOffice 转换命令: {' '.join(cmd)}")

                # 执行转换
                result = subprocess.run(
                    cmd,
                    check=True,
                    timeout=self.timeout,
                    capture_output=True,
                    text=True,
                )

                # 临时输出文件路径
                temp_pdf = temp_dir_path / f"{temp_input.stem}.pdf"

                # 验证输出文件是否存在
                if not temp_pdf.exists():
                    stderr_output = result.stderr if result.stderr else "No error output"
                    raise RuntimeError(
                        f"LibreOffice 转换失败: 输出文件未找到: {temp_pdf}\n"
                        f"stderr: {stderr_output}"
                    )

                # 读取 PDF 文件内容
                with open(temp_pdf, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()

                # 验证并记录 PDF 文件详细信息
                self._log_pdf_info(pdf_bytes, temp_pdf)
                
                # 保存PDF文件到指定目录
                saved_path = self._save_pdf_file(pdf_bytes, temp_pdf)
                logger.info(f"📁 PDF 文件已保存到: {saved_path}")

                return pdf_bytes

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"LibreOffice 转换超时（>{self.timeout}秒）"
            )
        except subprocess.CalledProcessError as e:
            stderr_output = e.stderr if e.stderr else "No error output"
            raise RuntimeError(
                f"LibreOffice 转换失败: {stderr_output}"
            )
        except Exception as e:
            raise RuntimeError(f"DOCX 转 PDF 转换错误: {e}")
        finally:
            # 清理临时 docx 文件
            try:
                os.unlink(tmp_docx_path)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")

    def _save_pdf_file(self, pdf_bytes: bytes, original_path: Path) -> Path:
        """
        保存PDF文件到指定目录
        
        Args:
            pdf_bytes: PDF 文件的字节内容
            original_path: 原始临时文件路径（用于获取文件名）
            
        Returns:
            保存后的文件路径
        """
        # 使用时间戳和原始文件名生成保存路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 获取原始文件名（不含扩展名）
        original_name = original_path.stem
        # 生成新的文件名：时间戳_原文件名.pdf
        filename = f"{timestamp}_{original_name}.pdf"
        saved_path = self._pdf_save_dir / filename
        
        # 如果文件已存在，添加序号
        counter = 1
        while saved_path.exists():
            filename = f"{timestamp}_{original_name}_{counter}.pdf"
            saved_path = self._pdf_save_dir / filename
            counter += 1
        
        # 保存文件
        with open(saved_path, "wb") as f:
            f.write(pdf_bytes)
        
        logger.info(f"  保存路径: {saved_path}")
        logger.info(f"  保存大小: {len(pdf_bytes) / 1024:.2f} KB")
        
        return saved_path

    def _log_pdf_info(self, pdf_bytes: bytes, pdf_path: Path) -> None:
        """
        验证并记录 PDF 文件的详细信息
        
        Args:
            pdf_bytes: PDF 文件的字节内容
            pdf_path: PDF 文件的路径（用于日志显示）
        """
        try:
            # 基本信息
            pdf_size = len(pdf_bytes)
            pdf_size_mb = pdf_size / (1024 * 1024)
            pdf_size_kb = pdf_size / 1024
            
            logger.info("=" * 60)
            logger.info("📄 PDF 转换成功 - 文件信息:")
            logger.info(f"  临时文件路径: {pdf_path} (处理完成后将保存到持久化目录)")
            logger.info(f"  文件大小: {pdf_size_kb:.2f} KB ({pdf_size_mb:.4f} MB)")
            logger.info(f"  文件大小(字节): {pdf_size:,} bytes")
            
            # 验证 PDF 文件格式（检查 PDF 文件头）
            if pdf_bytes[:4] == b"%PDF":
                pdf_version = pdf_bytes[4:8].decode("ascii", errors="ignore").strip()
                logger.info(f"  PDF 版本: {pdf_version}")
            else:
                logger.warning("  ⚠️ PDF 文件头验证失败，可能不是有效的 PDF 文件")
            
            # 使用 pdfplumber 获取更详细的信息
            try:
                import pdfplumber
                with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                    page_count = len(pdf.pages)
                    logger.info(f"  页数: {page_count} 页")
                    
                    # 获取第一页的信息作为示例
                    if page_count > 0:
                        first_page = pdf.pages[0]
                        width = first_page.width
                        height = first_page.height
                        logger.info(f"  页面尺寸: {width:.2f} x {height:.2f} 点")
                        
                        # 尝试提取第一页的文本长度（用于验证内容）
                        try:
                            text = first_page.extract_text()
                            if text:
                                text_length = len(text.strip())
                                logger.info(f"  第一页文本长度: {text_length} 字符")
                            else:
                                logger.info("  第一页文本: 无文本内容（可能是扫描件或图片）")
                        except Exception as e:
                            logger.debug(f"  提取第一页文本时出错: {e}")
                    
                    # 记录元数据（如果有）
                    if pdf.metadata:
                        logger.info("  元数据:")
                        for key, value in pdf.metadata.items():
                            if value:
                                logger.info(f"    {key}: {value}")
                    
            except ImportError:
                logger.warning("  pdfplumber 未安装，无法获取详细页数信息")
            except Exception as e:
                logger.warning(f"  获取 PDF 详细信息时出错: {e}")
                # 即使出错，也尝试简单验证 PDF 是否可读
                try:
                    # 简单检查：查找 PDF 中的页面对象
                    page_count_estimate = pdf_bytes.count(b"/Type/Page")
                    if page_count_estimate > 0:
                        logger.info(f"  估算页数: {page_count_estimate} 页（基于 /Type/Page 对象）")
                except Exception:
                    pass
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.warning(f"记录 PDF 信息时出错: {e}")
            # 即使出错，也记录基本信息
            logger.info(f"DOCX 转 PDF 成功: {len(pdf_bytes) / 1024:.1f}KB")
