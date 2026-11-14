import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'

// vite-plugin-cesium copies Cesium's Workers/Assets/Widgets into the build
// and sets CESIUM_BASE_URL, so the globe works fully offline (no CDN).
export default defineConfig({
  plugins: [react(), cesium()],
  // Old OpenLayers files live in ./static for the legacy FastAPI page — not a Vite public dir.
  publicDir: 'public',
  server: { port: 5173, strictPort: true },
})
