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
mkdir -Force .\storage, .\logs

# 2. （可选）创建 .env 文件配置环境变量
# 复制 .env.example 为 .env 并根据实际情况修改

# 3. 构建并启动服务
docker-compose up -d --build

# 4. 查看日志
docker-compose logs -f filereader-api

# 5. 停止服务
docker-compose down

# 6. 停止并删除卷（清理数据）
docker-compose down -v
```

### 方式二：使用 Docker 命令

```powershell
# （可选）在 PowerShell 中设置代理或远程 Docker 主机
$env:HTTP_PROXY="http://192.168.1.198:10811"
$env:HTTPS_PROXY="http://192.168.1.198:10811"
$env:DOCKER_HOST="tcp://192.168.1.10:2375"

# 1. 准备存储目录（用于存放解析出的图片等静态资源）
mkdir -Force .\storage, .\logs

# 2. 构建镜像
docker build -t filereaderapi:latest .

# 3. 运行容器（映射 8002 端口，挂载日志与静态目录）
docker run -d `
  --name filereaderapi `
  -p 8002:8002 `
  -e ROOT_PATH=/filereader-api `
  -e STORAGE_ROOT=/storage/ `
  -e STORAGE_URL_PREFIX=http://192.168.1.10:8002/static `
  -v ${PWD}/storage:/storage/ `
  -v ${PWD}/logs:/app/logs `
  filereaderapi:latest

# 4. 查看日志
docker logs -f filereaderapi

# 5. 停止并删除容器
docker stop filereaderapi && docker rm filereaderapi
```

## 🌐 访问服务
- API 文档：`http://localhost:8002/docs`
- OpenAPI JSON：`http://localhost:8002/openapi.json`
- 静态文件：`http://localhost:8002/static/...`
- 如果设置了 `ROOT_PATH=/filereader-api`，则访问：`http://your-domain.com/filereader-api/docs`

## 📁 目录与文件
- `Dockerfile`：基于 `python:3.11-slim-bookworm`，预装 poppler、tesseract（含简体/英文语言包）以支持 PDF OCR。
- `.dockerignore`：建议排除 `.venv/`、`__pycache__/`、`logs/` 等，确保镜像干净（如需可自行扩展）。
- `requirements.txt`：包含 HTML/Word/Excel/PDF 解析所需的 Python 依赖。
- `main.py`：FastAPI 入口，统一 150 MB 文件上限。
- 环境变量：存储配置（图片/附件目录、URL 前缀、是否按日期分目录、是否回退 base64）。

## ⚙️ 关键配置说明

### 运行命令
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8002
```

### 环境变量

#### 必需的系统依赖
- **pandoc**：DOCX 转 Markdown 必需，版本通过 `pandoc --version` 验证
- **poppler-utils**：PDF 转图片必需，包含 `pdftoppm`、`pdftotext` 等工具
- **tesseract-ocr**：OCR 必需，支持中英文识别

#### 应用配置环境变量
| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| `PYTHONPATH` | Python 模块搜索路径 | `/app` | - |
| `PYTHONUNBUFFERED` | 禁用 Python 输出缓冲 | `1` | - |
| `STORAGE_ROOT` | 静态文件存储根目录（容器内路径） | `/storage/` | `/storage/` |
| `STORAGE_URL_PREFIX` | 静态文件对外访问前缀 | `http://localhost:8002/static` | `https://your-domain.com/static` |
| `SUBDIR_BY_DATE` | 是否按日期分目录存储 | `true` | `true` / `false` |
| `KEEP_ORIGINAL_NAME` | 是否保留原文件名 | `false` | `true` / `false` |
| `INLINE_IMAGE_BASE64` | 是否内联 base64（不推荐） | `false` | `true` / `false` |
| `ROOT_PATH` | API 根路径（用于反向代理） | `""` | `/filereader-api` |

### Docker Compose 配置说明

#### 开发/测试环境（docker-compose.yml）
- 端口映射：`8002:8002`
- 卷挂载：
  - `./storage:/storage/`：持久化存储目录
  - `./logs:/app/logs`：日志目录
- 资源限制：CPU 2核，内存 2GB（上限）
- 健康检查：每 30 秒检查一次

#### 生产环境（docker-compose.prod.yml）
- 建议移除端口映射，通过反向代理访问
- 资源限制：CPU 4核，内存 4GB（上限）
- 日志轮转：最大 10MB，保留 3 个文件
- 自动重启：`always`

### 端口说明
- 容器内端口：`8002`
- 宿主机端口：可按需映射到其他端口，如 `8080:8002`

### 日志说明
- 容器日志：通过 `docker-compose logs` 或 `docker logs` 查看
- 应用日志：如果应用写入日志文件，会保存到挂载的 `./logs` 目录

## 🧩 常见问题
1. **构建慢或失败**：确认可访问阿里云源；无法访问时可把 Dockerfile 中的源换回官方。
2. **端口占用**：启动前确认宿主 `8002` 未占用，可 `netstat -ano | findstr 8002`。
3. **OCR 依赖报错**：确保镜像内已安装 `tesseract` & `poppler`，当前 Dockerfile 已处理；若需要额外语言包，可在 `apt-get install` 中追加。
4. **文件超过 150 MB**：服务会直接返回 400；如需更大，请调整 `main.py` 的 `MAX_FILE_SIZE` 并重新构建镜像。

## 🔐 生产部署建议

### 1. 使用 Docker Compose 部署
```bash
# 使用生产配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f filereader-api
```

### 2. 反向代理配置（Nginx 示例）
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 文件上传大小限制
    client_max_body_size 200M;

    location /filereader-api {
        proxy_pass http://localhost:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持（如果需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 超时设置
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 静态文件直接服务（可选，提高性能）
    location /static {
        alias /path/to/storage;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 3. 环境变量配置
创建 `.env` 文件（不要提交到 Git）：
```bash
ROOT_PATH=/filereader-api
STORAGE_ROOT=/storage/
STORAGE_URL_PREFIX=https://your-domain.com/static
SUBDIR_BY_DATE=true
KEEP_ORIGINAL_NAME=false
INLINE_IMAGE_BASE64=false
```

### 4. 安全建议
- ✅ 使用 HTTPS（通过反向代理）
- ✅ 设置文件上传大小限制
- ✅ 定期更新基础镜像和依赖
- ✅ 使用非 root 用户运行（Dockerfile 已配置）
- ✅ 限制资源使用（CPU、内存）
- ✅ 配置日志轮转，避免磁盘占满
- ✅ 定期备份存储目录

### 5. 监控和维护
```bash
# 查看容器资源使用
docker stats filereaderapi

# 清理无用镜像和容器
docker system prune -a

# 查看磁盘使用
docker system df

# 备份存储目录
tar -czf storage-backup-$(date +%Y%m%d).tar.gz ./storage
```

### 6. CI/CD 集成示例（GitHub Actions）
```yaml
name: Build and Deploy

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker image
        run: docker build -t filereaderapi:latest .
      - name: Push to registry
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
          docker push your-registry/filereaderapi:latest
```

## 📚 相关文档
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Docker 文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Pandoc 文档](https://pandoc.org/)
- [Tesseract OCR 文档](https://tesseract-ocr.github.io/)

## 🆘 获取帮助
如遇到问题，请检查：
1. Docker 和 Docker Compose 版本是否符合要求
2. 系统依赖是否正确安装（查看构建日志）
3. 环境变量配置是否正确
4. 端口和卷挂载是否正确
5. 查看容器日志：`docker-compose logs -f`

