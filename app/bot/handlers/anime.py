from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from fluentogram import TranslatorRunner

from app.services.anime_service import AnimeService

router = Router()


@router.message(Command("wait"))
async def wait_command(message: Message, i18n: TranslatorRunner) -> None:
    if not message.reply_to_message:
        await message.reply(i18n.get("anime-error-reply"))
        return

    reply = message.reply_to_message
    file_id = None
    is_gif = False

    if reply.photo:
        file_id = reply.photo[-1].file_id
    elif reply.animation:
        # If it's a GIF, we can try to extract frames.
        # Telegram often converts GIFs to MP4 (video/mp4).
        # If it is video/mp4, Pillow cannot open it.
        # We will use the thumbnail for MP4 animations/videos to be safe,
        # unless it is explicitly image/gif.
        if reply.animation.mime_type == "image/gif":
            file_id = reply.animation.file_id
            is_gif = True
        elif reply.animation.thumbnail:
            file_id = reply.animation.thumbnail.file_id
        else:
            # Fallback if no thumbnail (unlikely for animation)
            file_id = reply.animation.file_id
    elif reply.video:
        file_id = reply.video.thumbnail.file_id if reply.video.thumbnail else reply.video.file_id
    else:
        await message.reply(i18n.get("anime-error-reply"))
        return

    status_msg = await message.reply(i18n.get("anime-searching"))

    try:
        # Download file
        file_io = await message.bot.download(file_id)
        file_bytes = file_io.getvalue()

        result = await AnimeService.search_anime(file_bytes, is_gif=is_gif)

        if result:
            similarity = round(result.similarity * 100, 2)

            # Handle timecode
            seconds = getattr(result, "from_", getattr(result, "start", 0))
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            timecode = f"{minutes:02d}:{secs:02d}"

            # Handle titles
            native_title = "???"
            english_title = "???"
            if result.anilist and result.anilist.title:
                native_title = result.anilist.title.native or "???"
                english_title = result.anilist.title.english or "???"

            episode = result.episode or "?"

            caption = i18n.get(
                "anime-found",
                title_native=native_title,
                title_english=english_title,
                episode=episode,
                timecode=timecode,
                similarity=similarity,
            )

            # Send preview
            # result.video and result.image are URLs usually.
            # We can send them directly.
            if result.video:
                await message.reply_video(result.video, caption=caption)
            elif result.image:
                await message.reply_photo(result.image, caption=caption)
            else:
                await message.reply(caption)
        else:
            await message.reply(i18n.get("anime-not-found"))

    except Exception:
        await message.reply(i18n.get("anime-error"))
    finally:
        await status_msg.delete()
