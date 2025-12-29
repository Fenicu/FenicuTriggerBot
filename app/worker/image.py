import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


def resize_image(image_data: bytes, max_size: int = 512) -> bytes:
    """Изменить размер изображения, если оно слишком большое."""
    try:
        image = Image.open(io.BytesIO(image_data))

        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85)
            return output.getvalue()
        return image_data
    except Exception as e:
        logger.error(f"Failed to resize image: {e}")
        return image_data
