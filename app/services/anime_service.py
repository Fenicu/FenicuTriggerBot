import io
import logging
from typing import Any

import aiotracemoeapi
from PIL import Image, ImageSequence

logger = logging.getLogger(__name__)


class AnimeService:
    @staticmethod
    def extract_frames(gif_bytes: bytes) -> list[bytes]:
        """
        Extracts start, middle, and end frames from a GIF.
        """
        with Image.open(io.BytesIO(gif_bytes)) as img:
            frames = []
            iterator = ImageSequence.Iterator(img)
            all_frames = list(iterator)
            total_frames = len(all_frames)

            if total_frames == 0:
                return []

            indices = [0]
            if total_frames > 1:
                indices.append(total_frames // 2)
            if total_frames > 2:
                indices.append(total_frames - 1)

            # Remove duplicates if any (e.g. if total_frames is small)
            indices = sorted(set(indices))

            for i in indices:
                frame = all_frames[i].convert("RGB")
                byte_arr = io.BytesIO()
                frame.save(byte_arr, format="JPEG")
                frames.append(byte_arr.getvalue())

            return frames

    @classmethod
    async def search_anime(cls, file_bytes: bytes, is_gif: bool = False) -> dict[str, Any] | None:
        """
        Searches for anime using TraceMoe API.
        If is_gif is True, extracts frames and searches for each, returning the best result.
        """
        async with aiotracemoeapi.TraceMoe() as client:
            if is_gif:
                frames = cls.extract_frames(file_bytes)
                best_result = None
                highest_similarity = 0.0

                for frame in frames:
                    try:
                        result = await client.search(frame, upload_file=True)
                        if result and result.result:
                            # Assuming result.result is a list and we take the first one (best match)
                            top_match = result.result[0]
                            if top_match.similarity > highest_similarity:
                                highest_similarity = top_match.similarity
                                best_result = top_match
                    except Exception:
                        logger.warning("Failed to search frame from GIF", exc_info=True)
                        continue

                return best_result
            result = await client.search(file_bytes, upload_file=True)
            if result and result.result:
                return result.result[0]
            return None
