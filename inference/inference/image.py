import io
import logging

from PIL import Image

from inference.config import settings

logger = logging.getLogger(__name__)


def resize_image(image_data: bytes) -> bytes:
    """Resize image to max_size, keeping aspect ratio."""
    max_size = settings.MAX_IMAGE_SIZE

    try:
        image = Image.open(io.BytesIO(image_data))

        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size))

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
        return output.getvalue()
    except Exception:
        logger.exception("Failed to resize image")
        return image_data
