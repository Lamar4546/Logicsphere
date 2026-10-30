import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'

function cesiumStaticAssets() {
  return {
    name: 'cesium-static-assets',
    configResolved(config) {
      const source = path.resolve(config.root, 'node_modules/cesium/Build/Cesium')
      const target = path.resolve(config.root, 'public/cesium')
      for (const folder of ['Assets', 'ThirdParty', 'Workers', 'Widgets']) {
        fs.cpSync(path.join(source, folder), path.join(target, folder), { recursive: true })
      }
    },
  }
}

export default defineConfig({
  plugins: [vue(), cesiumStaticAssets()],
  define: { CESIUM_BASE_URL: JSON.stringify('/cesium/') },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
