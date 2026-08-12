import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './theme.css'
import './styles.css'
import './execution.css'
import './views.css'
import './shell.css'
import './composer.css'
import './stream.css'
import { App } from './App'
import { initTheme } from './runtime/theme'

initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
