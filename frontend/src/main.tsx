import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { retrieveLaunchParams } from '@telegram-apps/sdk-react'
import './index.css'
import App from './App.tsx'
import { normalizeTelegramHash } from './lib/startParam'

// Telegram открывает Mini App с параметрами запуска в hash:
// #tgWebAppData=...&tgWebAppStartParam=chat_<id>. Для HashRouter это выглядит как
// маршрут, которого нет, и он по `path="*"` уводит на главную -- поэтому переписываем
// hash в реальный маршрут ДО монтирования роутера.
// retrieveLaunchParams вызывается первым намеренно: SDK читает параметры из URL и
// кэширует их, иначе после затирания hash авторизация останется без initData.
try {
  retrieveLaunchParams()
} catch {
  // вне Telegram параметров запуска нет -- это нормально
}
normalizeTelegramHash(window.location)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
