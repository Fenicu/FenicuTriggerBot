from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("src"))
async def src_command(message: Message) -> None:
    """Показать JSON-представление сообщения от Telegram Bot API."""
    target = message.reply_to_message if message.reply_to_message else message
    json_text = target.model_dump_json(exclude_none=True, indent=2)

    # Telegram ограничивает сообщения 4096 символами
    if len(json_text) > 4080:
        for i in range(0, len(json_text), 4080):
            chunk = json_text[i : i + 4080]
            await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML")
    else:
        await message.answer(f"<pre>{json_text}</pre>", parse_mode="HTML")
