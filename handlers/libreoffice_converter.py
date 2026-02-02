from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class LibreOfficeConverter:
    """使用 LibreOffice 将 Office 文件转换为 PDF 的工具类"""

    def __init__(self, timeout: int = 120):
        """
        初始化转换器
        
        Args:
            timeout: 转换超时时间（秒），默认 120 秒
        """
        self.timeout = timeout
        self._check_libreoffice_available()

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

                logger.info(
                    f"DOCX 转 PDF 成功: {len(pdf_bytes) / 1024:.1f}KB"
                )

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
