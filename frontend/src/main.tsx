import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { retrieveLaunchParams, init, miniApp, viewport } from '@telegram-apps/sdk-react'
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

// Инициализация Telegram SDK: включает нативные компоненты (BackButton, ready/expand,
// см. useTelegramBackButton). Вне Telegram (обычный браузер) init() бросает исключение,
// т.к. под капотом снова читает launch-параметры, которых там нет -- это ожидаемо,
// приложение должно продолжать работать без нативного Telegram-хрома.
try {
  init()

  // ready() как можно раньше скрывает загрузочный плейсхолдер Telegram и показывает
  // приложение; expand() разворачивает Mini App на всю доступную высоту вместо
  // половины экрана. isAvailable() отдельно проверяет каждый вызов -- на случай
  // клиента Telegram, который поддерживает init(), но не конкретную функцию.
  if (miniApp.ready.isAvailable()) miniApp.ready()
  if (viewport.expand.isAvailable()) viewport.expand()
} catch {
  // не в Telegram -- нативные компоненты недоступны, это нормально
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
