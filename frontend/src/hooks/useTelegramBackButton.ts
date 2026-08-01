import { useEffect, useRef } from 'react';
import { backButton } from '@telegram-apps/sdk-react';

/**
 * Синхронизирует нативную кнопку "Назад" Telegram Mini App со страницей.
 *
 * На страницах деталей вызывать с колбэком навигации назад (обычно `() => navigate(-1)`) --
 * кнопка появится, и по тапу выполнится колбэк. На корневых вкладках вызывать с `false` --
 * кнопка гарантированно спрячется (подстраховка на случай, если предыдущая страница
 * не успела скрыть её сама, например при быстрой навигации).
 *
 * Вне Telegram (обычный браузер) каждый вызов SDK защищён isAvailable() и превращается
 * в no-op -- ничего не падает и не показывается. Существующие внутристраничные кнопки
 * "назад" не трогаем -- они остаются нужны вне Telegram.
 */
export function useTelegramBackButton(onBack: (() => void) | false): void {
  const onBackRef = useRef(onBack);
  useEffect(() => {
    onBackRef.current = onBack;
  });

  useEffect(() => {
    if (backButton.mount.isAvailable() && !backButton.isMounted()) {
      backButton.mount();
    }

    if (!onBack) {
      if (backButton.hide.isAvailable()) backButton.hide();
      return;
    }

    if (backButton.show.isAvailable()) backButton.show();
    if (!backButton.onClick.isAvailable()) return;

    const off = backButton.onClick(() => onBackRef.current && onBackRef.current());
    return () => {
      off();
      if (backButton.hide.isAvailable()) backButton.hide();
    };
    // Подписываемся заново только при смене режима "детали <-> корень", а не на каждый
    // новый onBack (обычно инлайн-функция вида `() => navigate(-1)`, актуальный колбэк
    // и так всегда читается из onBackRef)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!onBack]);
}
