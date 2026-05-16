import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
      '/tamagochi/pictures': { target: 'http://localhost:8000', changeOrigin: true },
      '/avatars': { target: 'http://localhost:8000', changeOrigin: true },
      '/app/pictures': { target: 'http://localhost:8000', changeOrigin: true }
    }
  }
})
