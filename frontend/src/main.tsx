import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'cesium/Build/Cesium/Widgets/widgets.css'
// The app's one font, bundled locally (no Google Fonts request — the app runs offline).
import '@fontsource/space-grotesk/400.css'
import '@fontsource/space-grotesk/500.css'
import '@fontsource/space-grotesk/600.css'
import '@fontsource/space-grotesk/700.css'
import './App.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
