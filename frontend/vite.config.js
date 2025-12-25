import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // 加载环境变量
    const env = loadEnv(mode, process.cwd(), '')
    // 从环境变量读取后端地址，默认使用 192.168.1.10:8002（与之前保持一致）
    const API_BASE_URL = env.VITE_API_BASE_URL || 'http://192.168.1.10:8002'
    // 使用相对路径，这样无论部署在什么路径下都能正常工作
    // 如果确实需要绝对路径，可以通过环境变量 VITE_BASE_PATH 覆盖
    const BASE_PATH = env.VITE_BASE_PATH || ''

    return {
        plugins: [vue()],
        base: BASE_PATH,
        server: {
            host: '0.0.0.0',  // 允许外部访问
            port: 5173,        // 指定端口
            proxy: {
                '/api': {
                    target: API_BASE_URL,
                    changeOrigin: true,
                    rewrite: (path) => path.replace(/^\/api/, '')
                },
                // 添加 /static 代理，确保静态文件可以通过代理访问
                '/static': {
                    target: API_BASE_URL,
                    changeOrigin: true
                }
            }
        },
        build: {
            outDir: 'dist',
            assetsDir: 'assets',
            // 确保构建后的资源路径正确
            rollupOptions: {
                output: {
                    // 确保资源文件名包含 hash，便于缓存
                    assetFileNames: 'assets/[name].[hash].[ext]',
                    chunkFileNames: 'assets/[name].[hash].js',
                    entryFileNames: 'assets/[name].[hash].js'
                }
            }
        }
    }
})

