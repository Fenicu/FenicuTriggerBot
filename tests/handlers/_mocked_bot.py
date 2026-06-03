"""MockedSession и фикстуры для интеграционных тестов wizard'а через реальный Dispatcher.

Aiogram 3 не поставляет встроенного mock-клиента. Мы реализуем `BaseSession`, который
перехватывает все Bot API-вызовы (sendMessage, editMessageText, answerCallbackQuery и т.д.),
складывает их в список для assert'ов и возвращает canned-ответы. Также можно
программировать исключения для конкретных методов — это даёт возможность воспроизвести
«Telegram отказался редактировать чужое сообщение» и подобные сценарии.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.client.telegram import PRODUCTION
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import Chat as AiogramChat
from aiogram.types import Message, User


class MockedSession(BaseSession):
    """Перехватывает Bot API вызовы.

    Атрибуты:
      requests: список (method_name, payload-dict).
      responses: словарь method_name -> заранее заготовленный ответ.
      exceptions: словарь method_name -> исключение, которое будет брошено.
    """

    def __init__(self) -> None:
        super().__init__(api=PRODUCTION)
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, Any] = {}
        self.exceptions: dict[str, Exception] = {}
        self._next_message_id = 1000

    def add_response(self, method_name: str, response: Any) -> None:
        self.responses[method_name] = response

    def raise_on(self, method_name: str, exc: Exception) -> None:
        self.exceptions[method_name] = exc

    def method_names(self) -> list[str]:
        return [r[0] for r in self.requests]

    def payloads_for(self, method_name: str) -> list[dict[str, Any]]:
        return [p for n, p in self.requests if n == method_name]

    def reset(self) -> None:
        self.requests.clear()
        self.responses.clear()
        self.exceptions.clear()

    async def close(self) -> None:
        pass

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        name = method.__class__.__name__
        payload = method.model_dump(exclude_none=True)
        self.requests.append((name, payload))

        if name in self.exceptions:
            raise self.exceptions[name]
        if name in self.responses:
            return self.responses[name]
        return self._default_response(name, payload)

    def _default_response(self, name: str, payload: dict[str, Any]) -> Any:
        if name == "GetMe":
            return User(id=1, is_bot=True, first_name="TestBot", username="testbot")
        if name in ("SendMessage", "SendPhoto", "SendVideo", "SendAnimation",
                    "SendSticker", "SendDocument", "SendVoice", "SendAudio",
                    "CopyMessage", "ForwardMessage", "EditMessageText",
                    "EditMessageCaption", "EditMessageReplyMarkup"):
            return self._stub_message(payload)
        if name in ("AnswerCallbackQuery", "DeleteMessage", "SetMyCommands",
                    "DeleteWebhook", "SetWebhook"):
            return True
        if name == "GetChatMember":
            return None  # тесты должны явно подменить
        # Fallback
        return True

    def _stub_message(self, payload: dict[str, Any]) -> Message:
        self._next_message_id += 1
        chat_id = payload.get("chat_id", 0)
        return Message(
            message_id=self._next_message_id,
            date=0,
            chat=AiogramChat(id=int(chat_id) if isinstance(chat_id, int | str) else 0, type="private"),
            text=payload.get("text"),
            caption=payload.get("caption"),
        )

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""


def build_update_message(
    *,
    update_id: int = 1,
    message_id: int = 1,
    chat_id: int,
    user_id: int,
    text: str | None = None,
    caption: str | None = None,
    sticker: dict | None = None,
) -> dict:
    """Собирает raw-update dict для `dp.feed_raw_update(bot, update)`."""
    msg: dict = {
        "message_id": message_id,
        "date": 0,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
    }
    if text is not None:
        msg["text"] = text
    if caption is not None:
        msg["caption"] = caption
    if sticker is not None:
        msg["sticker"] = sticker
    return {"update_id": update_id, "message": msg}


def build_update_callback(
    *,
    update_id: int,
    cb_id: str,
    chat_id: int,
    user_id: int,
    data: str,
    message_id: int = 999,
) -> dict:
    """Собирает callback_query update."""
    return {
        "update_id": update_id,
        "callback_query": {
            "id": cb_id,
            "chat_instance": "test-instance",
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "message": {
                "message_id": message_id,
                "date": 0,
                "chat": {"id": chat_id, "type": "private"},
                "from": {"id": 1, "is_bot": True, "first_name": "TestBot"},
            },
            "data": data,
        },
    }
