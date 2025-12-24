import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // 加载环境变量
    const env = loadEnv(mode, process.cwd(), '')
    // 从环境变量读取后端地址，默认使用 192.168.1.10:8002（与之前保持一致）
    const API_BASE_URL = env.VITE_API_BASE_URL || 'http://192.168.1.10:8002'

    return {
        plugins: [vue()],
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
        }
    }
})

