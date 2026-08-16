import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App'
import { initThemeEarly } from './hooks/useTheme'
import './index.css'

// Apply persisted appearance + theme before first paint to avoid a flash.
initThemeEarly()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>
)
