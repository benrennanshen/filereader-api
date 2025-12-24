FROM python:3.11-slim-bookworm

# 使用阿里云 Debian 12 源以加快依赖安装
RUN echo "Types: deb\nURIs: https://mirrors.aliyun.com/debian\nSuites: bookworm bookworm-updates\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\nTypes: deb\nURIs: https://mirrors.aliyun.com/debian-security\nSuites: bookworm-security\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg" > /etc/apt/sources.list.d/debian.sources

WORKDIR /app

# 安装系统依赖：curl（健康检查）、poppler（pdf2image）、tesseract（OCR）、pandoc（docx转换）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

