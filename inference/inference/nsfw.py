import io
import logging

import torch
from PIL import Image
from transformers import AutoModelForImageClassification, AutoProcessor

from inference.config import settings

logger = logging.getLogger(__name__)


class NSFWClassifier:
    def __init__(self) -> None:
        self.model = None
        self.processor = None
        self.loaded = False

    def load(self) -> None:
        model_name = "falconsai/nsfw_image_detection"
        logger.info(f"Loading NSFW model: {model_name} on {settings.NSFW_DEVICE}")
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = AutoModelForImageClassification.from_pretrained(model_name)
        self.model.to(settings.NSFW_DEVICE)
        self.model.eval()
        self.loaded = True
        logger.info("NSFW model loaded")

    def classify(self, image_data: bytes) -> tuple[bool, float]:
        """Classify image. Returns (is_nsfw, confidence)."""
        if not self.loaded:
            raise RuntimeError("NSFW model not loaded")

        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(settings.NSFW_DEVICE) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        probs = torch.softmax(outputs.logits, dim=1)
        labels = self.model.config.id2label

        nsfw_idx = None
        for idx, label in labels.items():
            if label.lower() == "nsfw":
                nsfw_idx = idx
                break

        if nsfw_idx is None:
            logger.error(f"NSFW label not found in model labels: {labels}")
            return False, 0.0

        nsfw_score = probs[0][nsfw_idx].item()
        is_nsfw = nsfw_score >= settings.NSFW_THRESHOLD

        logger.info(f"NSFW score: {nsfw_score:.4f}, threshold: {settings.NSFW_THRESHOLD}, is_nsfw: {is_nsfw}")
        return is_nsfw, nsfw_score


nsfw_classifier = NSFWClassifier()
