FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 设置环境变量，优化构建和运行
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖：curl（健康检查）、poppler（pdf2image）、tesseract（OCR）、pandoc（docx转换）
# 按依赖关系分组安装，优化缓存层
# 配置国内镜像源（阿里云）加速下载
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    curl \
    ca-certificates \
    # PDF处理依赖（pdf2image需要）
    poppler-utils \
    # OCR依赖（pytesseract需要）
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    # DOCX转换依赖（pypandoc需要）
    pandoc \
    # 图像处理依赖（Pillow可能需要）
    libjpeg-dev \
    zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# 验证关键依赖安装
RUN pandoc --version && \
    tesseract --version && \
    pdftoppm -v && \
    echo "所有系统依赖安装成功"

# 先复制依赖文件，利用Docker缓存层
COPY requirements.txt ./

# 安装Python依赖（使用国内镜像加速，可选）
RUN pip install --no-cache-dir -r requirements.txt \
    # 或者使用国内镜像：pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    && pip list

# 安装 Node.js 和 npm（用于构建前端）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 构建前端
# 使用相对路径，无需传递 ROOT_PATH
COPY frontend/package*.json ./frontend/
COPY frontend/vite.config.js ./frontend/
COPY frontend/index.html ./frontend/
COPY frontend/src ./frontend/src
WORKDIR /app/frontend
# 先删除可能存在的旧 dist 目录，确保使用新配置重新构建
RUN rm -rf dist && \
    npm install && \
    npm run build && \
    npm cache clean --force
WORKDIR /app

# 复制应用代码（后端）
COPY . .

# 创建必要的目录
RUN mkdir -p /app/storage /app/logs /storage && \
    chmod -R 755 /app/storage /app/logs /storage

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8002/docs || exit 1

EXPOSE 8002

# 使用 root 用户运行（简化权限管理）

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

