import asyncio
import base64
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from inference.config import settings
from inference.llm import check_ollama_health, classify_with_llm
from inference.nsfw import nsfw_classifier
from inference.schemas import ClassifyRequest, ClassifyResponse, HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    nsfw_classifier.load()
    yield


app = FastAPI(title="Trigger Inference Server", lifespan=lifespan)


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.post("/classify", response_model=ClassifyResponse, dependencies=[Depends(verify_api_key)])
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    image_data: bytes | None = None
    if request.image_base64:
        try:
            image_data = base64.b64decode(request.image_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image")

    # Step 1: NSFW check for images
    if image_data and nsfw_classifier.loaded:
        is_nsfw, confidence = await asyncio.to_thread(nsfw_classifier.classify, image_data)
        if is_nsfw:
            return ClassifyResponse(
                category="Porn",
                confidence=confidence,
                reasoning="NSFW content detected by image classifier",
                source="nsfw_classifier",
            )

    # Step 2: LLM for drugs/scam (and porn that NSFW missed)
    has_content = request.text or request.caption or image_data
    if not has_content:
        return ClassifyResponse(
            category="Safe",
            confidence=None,
            reasoning="No content to analyze",
            source="llm",
        )

    result = await classify_with_llm(
        text=request.text,
        caption=request.caption,
        image_data=image_data,
    )

    if result is None:
        raise HTTPException(status_code=503, detail="LLM unavailable")

    return result


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ollama_ok = await check_ollama_health()
    return HealthResponse(
        status="ok" if nsfw_classifier.loaded and ollama_ok else "degraded",
        nsfw_model_loaded=nsfw_classifier.loaded,
        ollama_available=ollama_ok,
    )
