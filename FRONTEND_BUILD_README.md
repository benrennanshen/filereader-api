# 前端静态文件构建说明

## 概述

项目已配置为支持前端构建成静态文件，并由后端 FastAPI 提供服务。这样可以将前后端部署在一起，简化部署流程。

## 主要改动

### 1. 后端改动 (`main.py`)

- ✅ 添加了 `/api` 前缀的 API 路由（使用 `APIRouter`）
- ✅ 添加了前端静态文件服务（挂载 `frontend/dist` 目录）
- ✅ 添加了 SPA 路由支持（所有非 API 路径返回 `index.html`）
- ✅ 确保 API 路由优先于静态文件路由

### 2. 前端改动 (`frontend/vite.config.js`)

- ✅ 配置了构建输出目录 (`dist`)
- ✅ 配置了资源文件路径 (`assets`)
- ✅ 保留了开发环境的代理配置

### 3. Dockerfile 改动

- ✅ 添加了 Node.js 安装步骤
- ✅ 添加了前端构建步骤（`npm run build`）

## 使用方法

### 方法一：本地构建（开发/测试）

1. **构建前端**：
   ```bash
   cd frontend
   npm install
   npm run build
   ```
   
   > **注意**：前端已配置为使用相对路径（`base: './'`），因此无论部署在根路径还是子路径下都能正常工作，无需设置 `VITE_BASE_PATH`。

2. **运行后端**：
   ```bash
   # 在项目根目录
   python main.py
   # 或
   uvicorn main:app --host 0.0.0.0 --port 8002
   ```

3. **访问应用**：
   - 前端页面：`http://localhost:8002`
   - API 文档：`http://localhost:8002/docs`

### 方法二：Docker 构建（生产环境）

1. **构建 Docker 镜像**：
   ```bash
   docker build -t filereader-api .
   ```
   
   > **注意**：由于使用相对路径，无需传递 `ROOT_PATH` 参数，一个构建可以适用于任何部署路径。

2. **运行容器**：
   ```bash
   docker run -d -p 8002:8002 \
     -v /path/to/storage:/data/filereader/storage \
     filereader-api
   ```

3. **访问应用**：
   - 前端页面：`http://localhost:8002`
   - API 文档：`http://localhost:8002/docs`

## API 路径说明

所有 API 端点现在都使用 `/api` 前缀：

- `POST /api/convert-to-md` - 单个文件转换
- `POST /api/convert-multiple-to-md` - 批量文件转换
- `GET /api/download-image` - 下载图片

前端代码中的 API 调用路径（`/api/...`）无需修改，可以直接使用。

## 路由优先级

1. **API 路由** (`/api/*`) - 最高优先级
2. **静态资源路由** (`/static/*`, `/assets/*`) - 中等优先级
3. **SPA 路由** (`/*`) - 最低优先级，返回 `index.html`

## 注意事项

1. **前端构建目录**：确保 `frontend/dist` 目录存在，否则后端会跳过前端静态文件服务
2. **开发环境**：开发时仍可使用 `npm run dev` 启动 Vite 开发服务器，使用代理访问后端
3. **生产环境**：构建后的前端文件由后端提供，无需单独的 Web 服务器
4. **API 文档**：FastAPI 的自动文档仍然可用（`/docs`, `/redoc`）

## 环境变量配置

前端构建时可以通过环境变量配置：

- `VITE_API_BASE_URL` - 后端 API 地址（开发环境代理使用）
- `VITE_BASE_PATH` - 前端部署的基础路径（默认为 `./`，使用相对路径）

> **注意**：默认使用相对路径（`./`），这样无论部署在什么路径下都能正常工作。如果需要使用绝对路径，可以通过环境变量覆盖，例如：`VITE_BASE_PATH=/filereader-api npm run build`

## 故障排查

1. **前端页面无法访问**：
   - 检查 `frontend/dist` 目录是否存在
   - 检查后端日志，确认前端静态文件已挂载

2. **API 调用失败**：
   - 确认 API 路径使用 `/api` 前缀
   - 检查后端日志，查看 API 请求是否正常

3. **图片无法显示**：
   - 确认 `/static` 路径正确挂载
   - 检查图片 URL 是否正确

