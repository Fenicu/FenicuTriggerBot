import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from fluentogram import TranslatorRunner

from app.services.anime_service import AnimeService

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("wait"))
async def wait_command(message: Message, i18n: TranslatorRunner) -> None:
    logger.info("Wait command invoked by user %s", message.from_user.id)
    if not message.reply_to_message:
        await message.reply(i18n.get("anime-error-reply"))
        return

    reply = message.reply_to_message
    file_id = None
    is_gif = False

    if reply.photo:
        logger.info("Processing photo")
        file_id = reply.photo[-1].file_id
    elif reply.animation:
        logger.info("Processing animation. Mime type: %s", reply.animation.mime_type)
        if reply.animation.mime_type == "image/gif":
            file_id = reply.animation.file_id
            is_gif = True
        elif reply.animation.thumbnail:
            file_id = reply.animation.thumbnail.file_id
        else:
            file_id = reply.animation.file_id
    elif reply.video:
        logger.info("Processing video")
        file_id = reply.video.thumbnail.file_id if reply.video.thumbnail else reply.video.file_id
    else:
        logger.info("Unsupported message type")
        await message.reply(i18n.get("anime-error-reply"))
        return

    logger.info("File ID: %s, is_gif: %s", file_id, is_gif)
    status_msg = await message.reply(i18n.get("anime-searching"))

    try:
        file_io = await message.bot.download(file_id)
        file_bytes = file_io.getvalue()
        logger.info("Downloaded file size: %d bytes", len(file_bytes))

        result = await AnimeService.search_anime(file_bytes, is_gif=is_gif)
        logger.info("Search result: %s", result)

        if result:
            similarity = round(result.similarity * 100, 2)

            seconds = getattr(result, "from_", getattr(result, "start", 0))
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            timecode = f"{minutes:02d}:{secs:02d}"

            native_title = "???"
            english_title = "???"
            if result.anilist and result.anilist.title:
                native_title = result.anilist.title.get("native") or "???"
                english_title = result.anilist.title.get("english") or "???"

            episode = result.episode or "?"

            caption = i18n.get(
                "anime-found",
                title_native=native_title,
                title_english=english_title,
                episode=episode,
                timecode=timecode,
                similarity=similarity,
            )

            if result.video:
                await message.reply_video(result.video, caption=caption, parse_mode="HTML")
            elif result.image:
                await message.reply_photo(result.image, caption=caption, parse_mode="HTML")
            else:
                await message.reply(caption, parse_mode="HTML")
        else:
            await message.reply(i18n.get("anime-not-found"))

    except Exception:
        logger.error("Error in wait_command", exc_info=True)
        await message.reply(i18n.get("anime-error"))
    finally:
        await status_msg.delete()
