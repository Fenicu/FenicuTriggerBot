import asyncio
import io
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

MAGIC_SIGNATURES = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG": "PNG",
    b"RIFF": "RIFF/WebP",
    b"GIF8": "GIF",
    b"\x00\x00\x00": "MP4/HEIC",
    b"BM": "BMP",
}


def _detect_format(data: bytes) -> str:
    """Detect image format from magic bytes."""
    header = data[:12]
    for sig, fmt in MAGIC_SIGNATURES.items():
        if header.startswith(sig):
            if fmt == "RIFF/WebP" and b"WEBP" in header:
                return "WebP"
            return fmt
    return f"unknown (header: {header[:8].hex()})"


async def _convert_with_ffmpeg(image_data: bytes, max_size: int = 512) -> bytes | None:
    """Convert any image format to JPEG using ffmpeg as fallback."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", "pipe:0",
            "-vframes", "1",
            "-vf", f"scale='min({max_size},iw)':'min({max_size},ih)':force_original_aspect_ratio=decrease",
            "-f", "mjpeg",
            "-q:v", "2",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=image_data), timeout=15
        )

        if proc.returncode == 0 and stdout:
            logger.info("ffmpeg fallback converted image successfully (%d bytes)", len(stdout))
            return stdout

        logger.warning("ffmpeg fallback failed (rc=%d): %s", proc.returncode, stderr.decode()[:200])
        return None
    except TimeoutError:
        logger.warning("ffmpeg fallback timed out")
        proc.kill()
        await proc.wait()
        return None
    except FileNotFoundError:
        logger.warning("ffmpeg not found for image conversion fallback")
        return None
    except Exception as e:
        logger.warning("ffmpeg fallback error: %s", e)
        return None


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


async def resize_image(image_data: bytes, max_size: int = 512, ensure_jpeg: bool = False) -> bytes | None:
    """Resize image and optionally force JPEG output.

    Returns JPEG bytes on success, None if the image cannot be processed.
    Uses PIL first, falls back to ffmpeg for unsupported formats (WebP, AVIF, etc.).
    """
    # Try PIL first
    try:
        image = Image.open(io.BytesIO(image_data))

        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        needs_resize = max(image.size) > max_size
        if needs_resize:
            image.thumbnail((max_size, max_size))

        if needs_resize or ensure_jpeg:
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85)
            return output.getvalue()
        return image_data
    except Exception as e:
        detected = _detect_format(image_data)
        logger.warning("PIL cannot open image (format: %s, size: %d bytes): %s", detected, len(image_data), e)

    # Fallback to ffmpeg
    logger.info("Trying ffmpeg fallback for image conversion")
    return await _convert_with_ffmpeg(image_data, max_size)
