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
            logger.info("Extracted %d frames from GIF", total_frames)

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
        logger.info("Starting anime search. File size: %d bytes, is_gif: %s", len(file_bytes), is_gif)
        try:
            async with aiotracemoeapi.TraceMoe() as client:
                if is_gif:
                    frames = cls.extract_frames(file_bytes)
                    best_result = None
                    highest_similarity = 0.0

                    for i, frame in enumerate(frames):
                        try:
                            logger.info("Searching frame %d/%d", i + 1, len(frames))
                            result = await client.search(io.BytesIO(frame))
                            logger.debug("Frame %d result: %s", i + 1, result)
                            if result and result.result:
                                # Assuming result.result is a list and we take the first one (best match)
                                top_match = result.result[0]
                                logger.info("Frame %d top match similarity: %s", i + 1, top_match.similarity)
                                if top_match.similarity > highest_similarity:
                                    highest_similarity = top_match.similarity
                                    best_result = top_match
                        except Exception:
                            logger.warning("Failed to search frame %d from GIF", i + 1, exc_info=True)
                            continue

                    logger.info("Best result from GIF search: %s", best_result)
                    return best_result

                logger.info("Searching single image")
                result = await client.search(io.BytesIO(file_bytes))
                logger.debug("Single image search result: %s", result)
                if result and result.result:
                    logger.info("Found match with similarity: %s", result.result[0].similarity)
                    return result.result[0]
                logger.info("No result found for single image")
                return None
        except Exception:
            logger.error("Error during anime search", exc_info=True)
            raise
