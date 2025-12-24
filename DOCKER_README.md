# FileReader API Docker 部署指南

本文档参考 `g:\excelapi` 的容器化方案，说明如何为当前项目构建并部署可在线解析多格式文档（含 150 MB PDF）的 Docker 镜像。

## 📋 前置要求
- Docker 20.0+
- 若需使用代理，请提前设置 `HTTP_PROXY / HTTPS_PROXY`
- 目标宿主可访问 `https://mirrors.aliyun.com`（若不能，可自行修改 Dockerfile 中的软件源）

## 🚀 快速开始
```powershell
# （可选）在 PowerShell 中设置代理或远程 Docker 主机
$env:HTTP_PROXY="http://192.168.1.198:10811"
$env:HTTPS_PROXY="http://192.168.1.198:10811"
$env:DOCKER_HOST="tcp://192.168.1.10:2375"

# 1. 准备存储目录（用于存放解析出的图片等静态资源）
mkdir -Force .\storage

# 2. 构建镜像
docker build -t filereaderapi:latest .

# 3. 运行容器（映射 8002 端口，挂载日志与静态目录）
docker run -d ^
  --name filereaderapi ^
  -p 8002:8002 ^
  -e ROOT_PATH=/filereader-api ^
-e STORAGE_ROOT=/app/storage ^
-e STORAGE_URL_PREFIX=http://192.168.1.10:8002/static ^
  -v ${PWD}/storage:/app/storage ^
  -v ${PWD}/logs:/app/logs ^
  filereaderapi:latest

# 4. 查看日志
docker logs -f filereaderapi

# 5. 停止并删除容器
docker stop filereaderapi && docker rm filereaderapi
```

## 🌐 访问服务
- API：`http://192.168.1.10/filereader-api/docs`
- Swagger：`http://localhost:8002/docs`

## 📁 目录与文件
- `Dockerfile`：基于 `python:3.11-slim-bookworm`，预装 poppler、tesseract（含简体/英文语言包）以支持 PDF OCR。
- `.dockerignore`：建议排除 `.venv/`、`__pycache__/`、`logs/` 等，确保镜像干净（如需可自行扩展）。
- `requirements.txt`：包含 HTML/Word/Excel/PDF 解析所需的 Python 依赖。
- `main.py`：FastAPI 入口，统一 150 MB 文件上限。
- 环境变量：存储配置（图片/附件目录、URL 前缀、是否按日期分目录、是否回退 base64）。

## ⚙️ 关键配置说明
- 运行命令：`python -m uvicorn main:app --host 0.0.0.0 --port 8002`
- 环境变量：
  - `PYTHONPATH=/app`
  - `PYTHONUNBUFFERED=1`
  - `STORAGE_ROOT`：静态文件存储根目录（默认 `/data/filereader/storage`，容器内可设 `/app/storage`）
  - `STORAGE_URL_PREFIX`：静态文件对外访问前缀（默认 `http://localhost:8002/static`）
  - `SUBDIR_BY_DATE`：是否按日期分目录（默认 `true`）
  - `KEEP_ORIGINAL_NAME`：是否尽量保留原文件名（默认 `false`）
  - `INLINE_IMAGE_BASE64`：是否改回内联 base64（默认 `false`，推荐保持文件存储）
  - `ROOT_PATH`（可选）：设置为 `/filereader-api` 等前缀时，FastAPI 会在反向代理路径下正确加载 `/docs`、`/openapi.json`
- 端口：容器暴露 `8002`，可按需映射到宿主其它端口。
- OCR 依赖：`poppler-utils` 用于 `pdf2image` 渲染，`tesseract-ocr` + `tesseract-ocr-chi-sim` + `tesseract-ocr-eng` 用于多语言识别。
- 日志：示例命令将宿主 `./logs` 绑定到 `/app/logs`（保持可选，若项目后续增加日志输出即可直接写入）。

## 🧩 常见问题
1. **构建慢或失败**：确认可访问阿里云源；无法访问时可把 Dockerfile 中的源换回官方。
2. **端口占用**：启动前确认宿主 `8002` 未占用，可 `netstat -ano | findstr 8002`。
3. **OCR 依赖报错**：确保镜像内已安装 `tesseract` & `poppler`，当前 Dockerfile 已处理；若需要额外语言包，可在 `apt-get install` 中追加。
4. **文件超过 150 MB**：服务会直接返回 400；如需更大，请调整 `main.py` 的 `MAX_FILE_SIZE` 并重新构建镜像。

## 🔐 生产部署建议
- 建议配合 Nginx/Traefik 做反向代理、TLS 终端与速率限制。
- 使用 `docker system prune` 定期清理无用镜像和容器，保持宿主磁盘充足。
- 可结合 CI/CD（如 GitHub Actions、自建 Runner）实现自动构建、推送和滚动更新。

如需 dev 模式热更新、Compose 编排或与其它服务联动，可告诉我继续扩展。*** End Patch

