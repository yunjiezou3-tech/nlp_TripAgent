import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd(), '')
  
  // 从环境变量获取端口，如果未设置则使用默认值
  const port = parseInt(env.VITE_PORT || '8081')
  
  return {
    plugins: [vue()],
    server: {
      port: port,
      open: true,
      strictPort: false // 允许端口被占用时自动选择其他端口
    }
  }
})


