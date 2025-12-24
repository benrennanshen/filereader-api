from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pypandoc

logger = logging.getLogger(__name__)


def _get_bool(env_key: str, default: bool) -> bool:
    val = os.getenv(env_key)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "y", "on"}


class DocxToMarkdownHandler:
    """将 DOCX 文档转换为 Markdown 文本的处理类，使用 pandoc 进行转换。"""

    def __init__(
        self,
        storage_root: Path,
        storage_url_prefix: str,
        subdir_by_date: bool = True,
        keep_original_name: bool = False,
        inline_image_base64: bool = False,
    ) -> None:
        self._storage_root = storage_root
        self._storage_url_prefix = storage_url_prefix.rstrip("/")
        self._subdir_by_date = subdir_by_date
        self._keep_original_name = keep_original_name
        self._inline_image_base64 = inline_image_base64

        # 检查pandoc是否可用
        try:
            pypandoc.get_pandoc_version()
            logger.info("Pandoc已安装并可用")
        except (OSError, RuntimeError) as e:
            logger.error(f"Pandoc未安装或不可用: {e}")
            raise RuntimeError(
                "Pandoc未安装。请先安装Pandoc: https://pandoc.org/installing.html"
            ) from e

    def convert(self, docx_bytes: bytes) -> str:
        """
        将 DOCX 文档转换为 Markdown 格式。
        
        Args:
            docx_bytes: DOCX文件的字节内容
            
        Returns:
            转换后的Markdown文本。默认：图片存储到仓库并以 URL 引用；如配置
            INLINE_IMAGE_BASE64=True，则回退为内联 base64。
        """
        if not isinstance(docx_bytes, (bytes, bytearray)):
            raise TypeError("docx_bytes must be bytes")
        if not docx_bytes:
            raise ValueError("docx file is empty")

        logger.info(f"开始DOCX转换，文件大小: {len(docx_bytes) / (1024*1024):.2f}MB")

        # 创建临时文件保存docx内容
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(docx_bytes)
            tmp_docx_path = tmp_docx.name

        # 创建临时目录用于存放提取的图片
        with tempfile.TemporaryDirectory() as tmp_media_dir:
            try:
                # 使用pandoc转换为markdown，并提取媒体文件
                markdown_text = self._convert_with_pandoc(
                    tmp_docx_path, tmp_media_dir
                )
                # 去除 pandoc 生成的尺寸属性，避免阻塞图片替换
                markdown_text = self._strip_image_size_attributes(markdown_text)
                
                # 根据配置决定图片处理策略
                if self._inline_image_base64:
                    markdown_text = self._convert_images_to_base64(
                        markdown_text, tmp_media_dir
                    )
                else:
                    markdown_text = self._convert_images_to_urls(
                        markdown_text,
                        tmp_media_dir,
                        self._storage_root,
                    )
                
                logger.info("DOCX转换完成")
                return markdown_text.strip()
            finally:
                # 清理临时docx文件
                try:
                    os.unlink(tmp_docx_path)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")

    def _convert_with_pandoc(self, docx_path: str, media_dir: str) -> str:
        """
        使用pandoc将docx转换为markdown。
        
        Args:
            docx_path: docx文件路径
            media_dir: 媒体文件输出目录
            
        Returns:
            转换后的markdown文本
        """
        try:
            # pandoc转换参数
            # --extract-media: 提取图片到指定目录
            # --wrap=none: 不自动换行
            # --markdown-headings=atx: 使用ATX风格标题（#）
            extra_args = [
                "--extract-media=" + media_dir,
                "--wrap=none",
                "--markdown-headings=atx",
            ]
            
            # 转换为markdown
            markdown_text = pypandoc.convert_file(
                docx_path,
                "markdown",
                format="docx",
                extra_args=extra_args,
            )
            
            # 检查转换后的 markdown 中是否包含图片
            image_count = len(re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', markdown_text))
            logger.info(f"Pandoc转换完成，Markdown长度: {len(markdown_text)}，包含 {image_count} 个图片引用")
            if image_count > 0:
                # 提取前几个图片路径作为示例
                sample_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', markdown_text)[:3]
                logger.debug(f"图片路径示例: {sample_images}")
            
            return markdown_text
        except Exception as exc:
            logger.exception(f"Pandoc转换失败: {exc}")
            raise ValueError(f"Failed to convert DOCX with pandoc: {exc}") from exc

    @staticmethod
    def _strip_image_size_attributes(markdown_text: str) -> str:
        """
        去除 pandoc 转换后附在图片后的尺寸属性块 {width="..."}，避免影响后续替换。
        """
        pattern = re.compile(r'(!\[[^\]]*\]\([^)]+\))\s*\{[^}]*\}')
        return pattern.sub(r"\1", markdown_text)

    def _convert_images_to_urls(
        self, markdown_text: str, media_dir: str, storage_root: Path
    ) -> str:
        """
        将 markdown 中的图片路径替换为可访问的 URL，并把图片迁移到存储仓库。
        """
        image_pattern = re.compile(
            r'!\[([^\]]*)\]\(([^)]+)\)|<img[^>]+src=["\']([^"\']+)["\']',
            re.IGNORECASE
        )

        # 先迁移文件，生成路径映射
        path_map = self._store_media_files(media_dir, storage_root)
        if not path_map:
            logger.warning("未找到任何媒体文件，无法生成图片 URL")
            return markdown_text

        # 记录 path_map 内容用于调试
        logger.debug(f"图片路径映射表: {path_map}")

        # 查找所有图片引用
        all_images = image_pattern.findall(markdown_text)
        logger.info(f"在 Markdown 中找到 {len(all_images)} 个图片引用")

        replaced = 0
        media_path = Path(media_dir)

        def replace_image(match: re.Match) -> str:
            nonlocal replaced
            if match.group(2):
                alt_text = match.group(1) or ""
                image_path = match.group(2)
            else:
                alt_text = ""
                image_path = match.group(3)

            if not image_path or image_path.startswith(("data:", "http://", "https://")):
                logger.debug(f"跳过已处理的图片路径: {image_path}")
                return match.group(0)

            # 标准化路径：统一使用正斜杠
            normalized = image_path.replace("\\", "/")
            
            # 尝试多种匹配方式：
            # 1. 如果路径是绝对路径且包含 media_dir，提取相对路径
            try:
                if os.path.isabs(normalized) and str(media_path) in normalized:
                    # 提取相对于 media_dir 的路径
                    abs_path = Path(normalized)
                    if abs_path.exists() and abs_path.is_relative_to(media_path):
                        rel_path = abs_path.relative_to(media_path).as_posix()
                        if rel_path in path_map:
                            replaced += 1
                            final_url = path_map[rel_path]
                            # 从 URL 中提取存储路径用于日志显示（相对于 STORAGE_ROOT）
                            url_path = final_url.replace(self._storage_url_prefix, "").lstrip("/")
                            storage_path = str(storage_root / url_path) if url_path else str(storage_root)
                            logger.info(f"图片路径匹配成功: 临时路径={image_path} -> 存储路径={storage_path}, URL={final_url}")
                            return f"![{alt_text}]({final_url})"
            except (ValueError, TypeError):
                pass
            
            # 2. 去掉开头的 ./ 和 /，然后尝试匹配
            normalized_clean = normalized.lstrip("./")
            basename = Path(normalized_clean).name
            
            logger.debug(f"尝试匹配图片路径: 原始={image_path}, 标准化={normalized_clean}, 文件名={basename}")
            
            # 3. 尝试匹配：标准化路径、清理后的路径、文件名
            for key in (normalized_clean, normalized, basename):
                if key in path_map:
                    replaced += 1
                    final_url = path_map[key]
                    # 从 URL 中提取存储路径用于日志显示（相对于 STORAGE_ROOT）
                    url_path = final_url.replace(self._storage_url_prefix, "").lstrip("/")
                    storage_path = str(storage_root / url_path) if url_path else str(storage_root)
                    logger.info(f"图片路径匹配成功: 临时路径={image_path} -> 存储路径={storage_path}, URL={final_url}")
                    return f"![{alt_text}]({final_url})"

            logger.warning(f"图片路径未找到映射，保留原路径: {image_path} (可用映射键: {list(path_map.keys())})")
            return match.group(0)

        result = image_pattern.sub(replace_image, markdown_text)
        if replaced:
            logger.info(f"已将 {replaced} 张图片替换为 URL 引用")
        else:
            logger.warning("未找到可替换的图片路径，请检查图片路径匹配逻辑")
        return result

    def _store_media_files(self, media_dir: str, storage_root: Path) -> dict[str, str]:
        """
        将 pandoc 提取的媒体文件迁移到存储目录，并生成路径映射表。
        返回: {相对路径/文件名: url}
        """
        path_map: dict[str, str] = {}
        media_path = Path(media_dir)
        if not media_path.exists():
            logger.warning(f"媒体目录不存在: {media_dir}")
            return path_map

        date_subdir = datetime.now().strftime("%Y/%m/%d") if self._subdir_by_date else ""

        for root, _dirs, files in os.walk(media_dir):
            for fname in files:
                src_path = Path(root) / fname
                rel_path = src_path.relative_to(media_path).as_posix()

                target_dir = Path(storage_root)
                if date_subdir:
                    target_dir = target_dir / Path(date_subdir)
                target_dir.mkdir(parents=True, exist_ok=True)

                suffix = src_path.suffix.lower()
                if self._keep_original_name:
                    dest_name = fname
                    candidate = target_dir / dest_name
                    if candidate.exists():
                        dest_name = f"{Path(fname).stem}-{uuid4().hex[:8]}{suffix}"
                else:
                    dest_name = f"{uuid4().hex}{suffix}"

                dest_path = target_dir / dest_name
                try:
                    shutil.move(str(src_path), str(dest_path))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"移动图片失败 {src_path}: {exc}")
                    continue

                # 生成对外 URL
                url_parts = [self._storage_url_prefix]
                if date_subdir:
                    url_parts.append(date_subdir.replace("\\", "/"))
                url_parts.append(dest_name)
                url = "/".join(part.strip("/") for part in url_parts if part)

                # 存储多种路径格式用于匹配：
                # 1. 相对路径（相对于 media_dir）
                path_map[rel_path] = url
                # 2. 文件名
                path_map[fname] = url
                # 3. 绝对路径（pandoc 可能在 markdown 中使用绝对路径）
                path_map[str(src_path)] = url
                path_map[str(src_path).replace("\\", "/")] = url
                # 4. 标准化后的相对路径（去掉开头的 ./）
                if rel_path.startswith("./"):
                    path_map[rel_path[2:]] = url
                
                logger.info(f"图片文件已迁移到存储目录: {src_path} -> {dest_path} (URL: {url})")

        if path_map:
            logger.info(f"已迁移 {len(set(path_map.values()))} 个媒体文件到 {storage_root}，生成 {len(path_map)} 个路径映射")
            logger.debug(f"生成的图片 URL 示例: {list(path_map.values())[0] if path_map.values() else '无'}")
        else:
            logger.warning(f"未在媒体目录中找到文件: {media_dir}")

        return path_map

    def _convert_images_to_base64(
        self, markdown_text: str, media_dir: str
    ) -> str:
        """
        将markdown中的图片路径替换为base64格式的data URI。
        
        Args:
            markdown_text: 包含图片路径的markdown文本
            media_dir: 图片文件所在的目录
            
        Returns:
            图片已转换为base64的markdown文本
        """
        # 匹配markdown中的图片语法: ![alt](path) 或 <img src="path">
        # 匹配相对路径和绝对路径
        image_pattern = re.compile(
            r'!\[([^\]]*)\]\(([^)]+)\)|<img[^>]+src=["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        
        def replace_image(match: re.Match) -> str:
            """替换单个图片为base64格式"""
            # 处理 ![alt](path) 格式
            if match.group(2):
                alt_text = match.group(1) or ""
                image_path = match.group(2)
            # 处理 <img src="path"> 格式
            else:
                alt_text = ""
                image_path = match.group(3)
            
            # 跳过已经是data URI的图片
            if image_path.startswith("data:"):
                return match.group(0)
            
            # 构建完整的图片路径
            # pandoc提取的图片路径可能是相对于media_dir的
            if os.path.isabs(image_path):
                full_path = image_path
            else:
                # 尝试多个可能的路径
                # pandoc可能会在media_dir下创建子目录结构
                possible_paths = [
                    os.path.join(media_dir, image_path),  # 直接路径
                    os.path.join(media_dir, os.path.basename(image_path)),  # 仅文件名
                    image_path,  # 相对路径（当前目录）
                ]
                
                # 递归搜索media_dir下的所有文件
                if not any(os.path.exists(p) for p in possible_paths):
                    # 在media_dir及其子目录中搜索文件名匹配的文件
                    image_filename = os.path.basename(image_path)
                    for root, dirs, files in os.walk(media_dir):
                        if image_filename in files:
                            possible_paths.append(os.path.join(root, image_filename))
                            break
                
                full_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        full_path = path
                        break
                
                if not full_path:
                    logger.warning(f"图片文件未找到: {image_path}，搜索目录: {media_dir}")
                    return match.group(0)
            
            # 读取图片并转换为base64
            try:
                with open(full_path, "rb") as img_file:
                    image_data = img_file.read()
                
                # 确定MIME类型
                ext = Path(full_path).suffix.lower()
                mime_types = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".bmp": "image/bmp",
                    ".svg": "image/svg+xml",
                    ".webp": "image/webp",
                }
                content_type = mime_types.get(ext, "image/png")
                
                # 转换为base64
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                data_uri = f"data:{content_type};base64,{image_base64}"
                
                # 返回替换后的markdown图片语法
                return f"![{alt_text}]({data_uri})"
            except Exception as e:
                logger.warning(f"转换图片失败 {image_path}: {e}")
                return match.group(0)
        
        # 替换所有图片
        result = image_pattern.sub(replace_image, markdown_text)
        
        # 统计替换的图片数量
        replaced_count = len(image_pattern.findall(markdown_text))
        if replaced_count > 0:
            logger.info(f"已将 {replaced_count} 张图片转换为base64格式")
        
        return result
