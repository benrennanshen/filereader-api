"""下载处理模块，用于生成包含 Markdown 和图片的 ZIP 包。"""

import base64
import logging
import re
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class MarkdownZipGenerator:
    """生成包含 Markdown 文件和关联图片的 ZIP 包。"""

    def __init__(self, storage_root: Path, storage_url_prefix: str):
        """
        初始化 ZIP 生成器。

        Args:
            storage_root: 图片存储根目录
            storage_url_prefix: 图片 URL 前缀
        """
        self._storage_root = storage_root
        self._storage_url_prefix = storage_url_prefix.rstrip("/")

    def generate_zip(self, markdown_content: str) -> BytesIO:
        """
        生成包含 Markdown 文件和图片的 ZIP 包。

        Args:
            markdown_content: Markdown 内容

        Returns:
            ZIP 文件的 BytesIO 对象

        Raises:
            ValueError: 如果 Markdown 内容为空
            Exception: 如果生成 ZIP 失败
        """
        if not markdown_content:
            raise ValueError("Markdown content is required")

        # 创建 ZIP 缓冲区
        zip_buffer = BytesIO()

        try:
            # Python 3.11+ 的 zipfile 默认支持 UTF-8 编码的文件名
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                # 1. 提取所有图片 URL
                image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)', re.IGNORECASE)
                image_matches = image_pattern.findall(markdown_content)

                logger.info(f"找到 {len(image_matches)} 个图片引用")

                # 2. 收集图片文件并更新 markdown 中的路径
                updated_markdown = markdown_content
                images_dir = "images"
                used_filenames = set()  # 用于跟踪已使用的文件名，避免冲突

                for idx, (alt_text, image_url) in enumerate(image_matches):
                    # 处理 data URI 图片
                    if image_url.startswith("data:"):
                        try:
                            # 解析 data URI: data:image/png;base64,...
                            header, data = image_url.split(",", 1)
                            mime_type = header.split(":")[1].split(";")[0]
                            ext_map = {
                                "image/png": ".png",
                                "image/jpeg": ".jpg",
                                "image/jpg": ".jpg",
                                "image/gif": ".gif",
                                "image/webp": ".webp",
                                "image/svg+xml": ".svg",
                                "image/bmp": ".bmp",
                            }
                            ext = ext_map.get(mime_type, ".png")
                            image_data = base64.b64decode(data)

                            # 生成唯一文件名
                            image_filename = self._get_unique_filename(
                                f"image_{idx + 1}{ext}", used_filenames
                            )
                            local_path = f"{images_dir}/{image_filename}"
                            zip_file.writestr(local_path, image_data)

                            # 更新 markdown 中的路径
                            updated_markdown = updated_markdown.replace(
                                f"![{alt_text}]({image_url})",
                                f"![{alt_text}]({local_path})",
                                1  # 只替换第一个匹配项
                            )
                            logger.info(f"已添加 base64 图片到 ZIP: {local_path}")
                        except Exception as e:
                            logger.warning(f"处理 base64 图片失败: {e}")
                        continue

                    # 跳过外部 URL（http/https）
                    if image_url.startswith(("http://", "https://")):
                        # 检查是否是同源的 /static/ 路径
                        try:
                            url = urlparse(image_url)
                            if url.path.startswith("/static/"):
                                # 这是同源的静态资源，需要处理
                                local_path_result = self._resolve_image_path(url.path)
                                if local_path_result:
                                    file_path, local_path = local_path_result
                                    if file_path.exists() and file_path.is_file():
                                        image_filename = self._get_unique_filename(
                                            file_path.name, used_filenames
                                        )
                                        final_local_path = f"{images_dir}/{image_filename}"
                                        zip_file.write(str(file_path), final_local_path)

                                        # 更新 markdown 中的路径
                                        updated_markdown = updated_markdown.replace(
                                            f"![{alt_text}]({image_url})",
                                            f"![{alt_text}]({final_local_path})",
                                            1
                                        )
                                        logger.info(f"已添加图片到 ZIP: {file_path} -> {final_local_path}")
                        except Exception as e:
                            logger.warning(f"处理外部 URL 图片失败: {e}")
                        continue

                    # 处理相对路径或本地路径
                    local_path_result = self._resolve_image_path(image_url)
                    if not local_path_result:
                        logger.warning(f"无法解析图片路径: {image_url}")
                        continue

                    file_path, _ = local_path_result

                    # 安全检查：确保文件路径在 STORAGE_ROOT 内
                    if not str(file_path).startswith(str(self._storage_root.resolve())):
                        logger.warning(f"非法的图片路径: {file_path} (不在存储根目录内)")
                        continue

                    if not file_path.exists() or not file_path.is_file():
                        logger.warning(f"图片不存在: {file_path}")
                        continue

                    # 生成唯一文件名
                    image_filename = self._get_unique_filename(
                        file_path.name, used_filenames
                    )
                    local_path = f"{images_dir}/{image_filename}"
                    zip_file.write(str(file_path), local_path)

                    # 更新 markdown 中的路径为相对路径
                    updated_markdown = updated_markdown.replace(
                        f"![{alt_text}]({image_url})",
                        f"![{alt_text}]({local_path})",
                        1
                    )

                    logger.info(f"已添加图片到 ZIP: {file_path} -> {local_path}")

                # 3. 添加更新后的 markdown 文件到 ZIP
                # 使用 UTF-8 编码确保中文内容正确
                zip_file.writestr("document.md", updated_markdown.encode('utf-8'))
                logger.info("已添加 Markdown 文件到 ZIP")

            # 重置缓冲区位置
            zip_buffer.seek(0)
            return zip_buffer

        except Exception as e:
            logger.exception(f"生成 ZIP 包失败: {e}")
            raise

    def _resolve_image_path(self, image_url: str) -> Optional[Tuple[Path, str]]:
        """
        解析图片 URL 为本地文件路径。

        Args:
            image_url: 图片 URL 或路径

        Returns:
            (文件路径, 原始路径) 元组，如果无法解析则返回 None
        """
        # 解析 URL
        parsed = urlparse(image_url)
        candidate_path = parsed.path if (parsed.scheme or parsed.netloc) else image_url

        # 标准化路径
        candidate_path = candidate_path.replace("\\", "/")
        candidate_path_normalized = (
            candidate_path if candidate_path.startswith("/") else "/" + candidate_path
        )

        # 处理 STORAGE_URL_PREFIX
        if self._storage_url_prefix.startswith(("http://", "https://")):
            storage_prefix_path = urlparse(self._storage_url_prefix).path.rstrip("/")
        else:
            storage_prefix_path = self._storage_url_prefix.rstrip("/")

        if storage_prefix_path and not storage_prefix_path.startswith("/"):
            storage_prefix_path = "/" + storage_prefix_path

        # 去掉前缀
        if storage_prefix_path:
            if candidate_path_normalized.startswith(storage_prefix_path):
                candidate_path = candidate_path_normalized[len(storage_prefix_path):]
            elif candidate_path.startswith(storage_prefix_path.lstrip("/")):
                candidate_path = candidate_path[len(storage_prefix_path.lstrip("/")):]

        if candidate_path.startswith("/static"):
            candidate_path = candidate_path[len("/static"):]
        elif candidate_path.startswith("static/"):
            candidate_path = candidate_path[len("static/"):]

        candidate_path = candidate_path.lstrip("/\\")

        # 构建文件路径
        file_path = (self._storage_root / candidate_path).resolve()

        return (file_path, candidate_path)

    def _get_unique_filename(self, filename: str, used_filenames: set) -> str:
        """
        生成唯一的文件名，避免冲突。

        Args:
            filename: 原始文件名
            used_filenames: 已使用的文件名集合

        Returns:
            唯一的文件名
        """
        if filename not in used_filenames:
            used_filenames.add(filename)
            return filename

        # 如果文件名已存在，添加序号
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1
        while True:
            new_filename = f"{stem}_{counter}{suffix}"
            if new_filename not in used_filenames:
                used_filenames.add(new_filename)
                return new_filename
            counter += 1

    def get_zip_filename(self, original_filename: str = "") -> str:
        """
        生成 ZIP 文件名。

        Args:
            original_filename: 原始文件名（可选）

        Returns:
            ZIP 文件名
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if original_filename:
            # 提取文件名（不含扩展名）
            file_path = Path(original_filename)
            name_without_ext = file_path.stem
            # 清理文件名，移除可能的不合法字符
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', name_without_ext)
            # 限制长度，避免文件名过长
            if len(safe_name) > 50:
                safe_name = safe_name[:50]
            return f"{safe_name}_{timestamp}.zip"
        else:
            return f"markdown_with_images_{timestamp}.zip"

