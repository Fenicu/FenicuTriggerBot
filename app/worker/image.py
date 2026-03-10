import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def extract_frame_from_video_path(video_path: str | Path, position: float = 0.5) -> bytes | None:
    """
    Извлечь кадр из видео с помощью ffmpeg.

    Args:
        video_path: Путь к видео файлу на диске
        position: Позиция кадра (0.0-1.0, где 0.5 = середина видео)

    Returns:
        Байты изображения в формате JPEG или None при ошибке
    """
    video_path = Path(video_path)
    frame_path = video_path.parent / "frame.jpg"

    try:
        duration_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *duration_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        duration = 1.0
        try:
            duration = float(stdout.decode().strip())
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse video duration, using default position. stderr: {stderr.decode()}")

        seek_time = duration * position

        extract_cmd = [
            "ffmpeg",
            "-ss",
            str(seek_time),
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-y",
            str(frame_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *extract_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=60)

        if frame_path.exists():
            return frame_path.read_bytes()

        logger.error("ffmpeg did not create output frame")
        return None

    except TimeoutError:
        logger.error("ffmpeg timed out while extracting frame")
        return None
    except FileNotFoundError:
        logger.error("ffmpeg/ffprobe not found. Please install ffmpeg.")
        return None
    except Exception as e:
        logger.error(f"Failed to extract frame from video: {e}")
        return None
