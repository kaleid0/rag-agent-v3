import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'RAG_')
  const proxy = {
    '/api/': {
      target: env.RAG_API_TARGET || 'http://127.0.0.1:8000',
    },
  }

  return {
    plugins: [react()],
    server: { proxy, host: '127.0.0.1', strictPort: true },
    preview: { proxy, host: '127.0.0.1', strictPort: true },
  }
})
