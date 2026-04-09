# GPU Inference Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate AI moderation from Ollama to a standalone gRPC inference server running Gemma 4 e4b (INT4) on a dedicated GPU server (Tesla V100 16GB).

**Architecture:** Two independent projects communicating via gRPC. GPU server (`trigger-inference`) handles only model inference. Bot's `ai_worker` downloads media, prepares images, sends gRPC requests, and handles results. Proto contract is shared between both.

**Tech Stack:** Python 3.12+, torch + transformers + torchao (INT4), grpcio, pydantic-settings, uv, Docker + nvidia-runtime

**Spec:** `docs/superpowers/specs/2026-04-10-gpu-inference-refactoring-design.md`

---

## File Map

### New project: trigger-inference/ (on aiserver)

| File | Responsibility |
|---|---|
| `proto/moderation.proto` | gRPC contract (shared with bot) |
| `inference/__init__.py` | Package init |
| `inference/config.py` | Settings via env vars (pydantic-settings) |
| `inference/model_manager.py` | Load/unload model, idle timeout, semaphore |
| `inference/moderator.py` | System prompt, Gemma 4 generation, JSON parsing |
| `inference/server.py` | gRPC server, Moderate + HealthCheck RPCs |
| `generated/moderation_pb2.py` | Auto-generated protobuf classes |
| `generated/moderation_pb2_grpc.py` | Auto-generated gRPC stubs |
| `pyproject.toml` | Dependencies (uv) |
| `Dockerfile` | CUDA + uv + torch + transformers |
| `compose.yml` | Docker Compose with nvidia runtime |
| `.env.example` | Example environment variables |

### Modified files in trigger bot (myprojects/trigger/)

| File | Change |
|---|---|
| `app/core/config.py` | Remove Ollama settings, add gRPC settings |
| `app/schemas/moderation.py` | Add Violence, PersonalData categories; remove image_description |
| `app/db/models/moderation_history.py` | Add AI_ANALYZING, AI_COMPLETED steps |
| `app/worker/llm.py` | Complete rewrite: InferenceClient gRPC class |
| `app/worker/service.py` | process_media returns bytes; handle_moderation_result drops image_description |
| `app/worker/main.py` | Simplify analyze_trigger pipeline; add GPU stale alert |
| `proto/moderation.proto` | Copy of shared proto |
| `generated/moderation_pb2.py` | Auto-generated protobuf classes |
| `generated/moderation_pb2_grpc.py` | Auto-generated gRPC stubs |
| `pyproject.toml` | Add grpcio, grpcio-tools |
| `compose.yml` | Replace Ollama env with gRPC env in ai_worker |
| `.env.example` | Add GRPC_INFERENCE_URL etc. |
| `frontend/src/components/ModerationTimeline.tsx` | Replace vision/text steps with ai steps; improve detail display |

---

## Task 1: Proto contract and code generation (trigger-inference)

**Files:**
- Create: `trigger-inference/proto/moderation.proto`
- Create: `trigger-inference/pyproject.toml`
- Create: `trigger-inference/inference/__init__.py`
- Generate: `trigger-inference/generated/moderation_pb2.py`
- Generate: `trigger-inference/generated/moderation_pb2_grpc.py`

- [ ] **Step 1: Create project directory and pyproject.toml**

```bash
mkdir -p ~/myprojects/trigger-inference/{proto,inference,generated}
cd ~/myprojects/trigger-inference
```

```toml
# pyproject.toml
[project]
name = "trigger-inference"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "torch>=2.7.0",
    "torchao>=0.9.0",
    "torchvision>=0.22.0",
    "transformers>=4.51.0",
    "grpcio>=1.70.0",
    "grpcio-tools>=1.70.0",
    "grpcio-reflection>=1.70.0",
    "pydantic-settings>=2.12.0",
    "pillow>=12.1.0",
]

[tool.uv]
index-url = "http://10.10.40.8:3141/root/pypi/+simple/"
```

- [ ] **Step 2: Create proto file**

```protobuf
// proto/moderation.proto
syntax = "proto3";

package moderation;

service ModerationService {
  rpc Moderate (ModerationRequest) returns (ModerationResponse);
  rpc HealthCheck (Empty) returns (HealthStatus);
}

message Empty {}

message ModerationRequest {
  string text = 1;
  string caption = 2;
  bytes image = 3;
  string request_id = 4;
}

message ModerationResponse {
  string category = 1;
  float confidence = 2;
  string reasoning = 3;
  string request_id = 4;
}

message HealthStatus {
  bool model_loaded = 1;
  float gpu_memory_used_mb = 2;
  float gpu_memory_total_mb = 3;
  int64 uptime_seconds = 4;
  int64 requests_processed = 5;
}
```

- [ ] **Step 3: Create empty __init__.py**

```bash
touch inference/__init__.py
```

- [ ] **Step 4: Install dependencies and generate protobuf code**

```bash
cd ~/myprojects/trigger-inference
uv sync
uv run python -m grpc_tools.protoc \
  -Iproto \
  --python_out=generated \
  --grpc_python_out=generated \
  proto/moderation.proto
touch generated/__init__.py
```

- [ ] **Step 5: Verify generated files exist**

```bash
ls generated/moderation_pb2.py generated/moderation_pb2_grpc.py
```

Expected: both files listed.

- [ ] **Step 6: Commit**

```bash
cd ~/myprojects/trigger-inference
git init && git add -A
git commit -m "feat: proto contract and project scaffold"
```

---

## Task 2: Config and model manager (trigger-inference)

**Files:**
- Create: `trigger-inference/inference/config.py`
- Create: `trigger-inference/inference/model_manager.py`

- [ ] **Step 1: Create config.py**

```python
# inference/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MODEL_NAME: str = "google/gemma-4-e4b-it"
    MODEL_UNLOAD_TIMEOUT: int = 300
    GRPC_PORT: int = 50051
    GRPC_MAX_MESSAGE_SIZE: int = 16_777_216
    TLS_CERT_PATH: str = ""
    TLS_KEY_PATH: str = ""
    HF_TOKEN: str = ""
    MAX_NEW_TOKENS: int = 256
    IMAGE_SOFT_TOKENS: int = 280

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
```

- [ ] **Step 2: Create model_manager.py**

```python
# inference/model_manager.py
import asyncio
import gc
import logging
import time

import torch
from transformers import AutoProcessor, Gemma4ForConditionalGeneration, TorchAoConfig

from inference.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages Gemma 4 model lifecycle: lazy load, idle unload, concurrency guard."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(1)
        self._last_used: float = 0.0
        self._unload_task: asyncio.Task | None = None
        self._requests_processed: int = 0
        self._start_time: float = time.time()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def requests_processed(self) -> int:
        return self._requests_processed

    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self._start_time)

    def gpu_memory_used_mb(self) -> float:
        if not torch.cuda.is_available():
            return 0.0
        return torch.cuda.memory_allocated() / 1024 / 1024

    def gpu_memory_total_mb(self) -> float:
        if not torch.cuda.is_available():
            return 0.0
        return torch.cuda.get_device_properties(0).total_memory / 1024 / 1024

    async def ensure_loaded(self) -> tuple:
        """Return (model, processor), loading if necessary."""
        async with self._lock:
            if self._model is None:
                logger.info("Loading model %s with INT4 quantization...", settings.MODEL_NAME)
                quantization_config = TorchAoConfig("int4_weight_only", group_size=128)
                self._model = Gemma4ForConditionalGeneration.from_pretrained(
                    settings.MODEL_NAME,
                    dtype=torch.float16,
                    device_map="auto",
                    attn_implementation="sdpa",
                    quantization_config=quantization_config,
                    token=settings.HF_TOKEN or None,
                )
                self._processor = AutoProcessor.from_pretrained(
                    settings.MODEL_NAME,
                    padding_side="left",
                    token=settings.HF_TOKEN or None,
                )
                logger.info(
                    "Model loaded. VRAM used: %.0f MB",
                    self.gpu_memory_used_mb(),
                )
            self._touch()
        return self._model, self._processor

    async def unload(self) -> None:
        """Unload model from VRAM."""
        async with self._lock:
            if self._model is None:
                return
            logger.info("Unloading model from VRAM...")
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Model unloaded. VRAM used: %.0f MB", self.gpu_memory_used_mb())

    def _touch(self) -> None:
        """Reset idle timer."""
        self._last_used = time.time()
        if self._unload_task and not self._unload_task.done():
            self._unload_task.cancel()
        self._unload_task = asyncio.create_task(self._idle_watcher())

    async def _idle_watcher(self) -> None:
        """Unload model after idle timeout."""
        try:
            await asyncio.sleep(settings.MODEL_UNLOAD_TIMEOUT)
            elapsed = time.time() - self._last_used
            if elapsed >= settings.MODEL_UNLOAD_TIMEOUT:
                await self.unload()
        except asyncio.CancelledError:
            pass

    def increment_requests(self) -> None:
        self._requests_processed += 1


model_manager = ModelManager()
```

- [ ] **Step 3: Commit**

```bash
git add inference/config.py inference/model_manager.py
git commit -m "feat: config and model manager with INT4 quantization and idle unload"
```

---

## Task 3: Moderator — prompt and inference (trigger-inference)

**Files:**
- Create: `trigger-inference/inference/moderator.py`

- [ ] **Step 1: Create moderator.py**

```python
# inference/moderator.py
import json
import logging
import re
from io import BytesIO

from PIL import Image

from inference.config import settings
from inference.model_manager import model_manager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Telegram content moderation system. Your task is to classify \
user-submitted content (text and/or image) that will be stored as an \
automated reply trigger in a Telegram bot.

Classify into EXACTLY ONE category:

- "Drugs" — Sale, advertising, or distribution of illegal substances. \
Signs: price lists, shop contacts, bot links selling drugs, substance \
photos with intent to sell, coded language (❄️ 🍬 🌿 💎), stash/dead-drop \
instructions ("клад", "закладка"), graffiti with contacts (@username, URLs). \
Russian slang: "мефедрон", "скорость", "шишки", "гашиш", "амфетамин", \
"закладки", "кристаллы". Obfuscated: "м3ф", "ск", "a-pvp".

- "Porn" — Explicit sexual content: genitalia, sexual acts, masturbation, \
pornographic links/previews. ESPECIALLY flag any content that may involve \
or depict minors (CSAM) — this is the highest-priority violation. \
Does NOT include: artistic nudity, medical illustrations, memes without \
explicit content.

- "Scam" — Recruitment for illegal activities or financial fraud. \
Signs: "easy money no experience", courier/delivery jobs with suspicious \
pay, pyramid schemes, fake giveaways, phishing links. \
Russian: "работа курьером", "высокий доход без опыта", "лёгкие деньги", \
"прогулки по городу", "вакансия кладмен".

- "Violence" — Threats, extremist content, terrorism propaganda, weapon \
sales/trading, graphic violence, calls for violence against individuals \
or groups. Signs: weapon photos with price tags, extremist symbols, \
beheading/torture imagery, death threats. \
Russian: "купить ствол", "заказать", "убью", propaganda channels.

- "PersonalData" — Leaked personal data: passport scans, ID documents, \
database dumps with personal info, doxxing (publishing private addresses, \
phone numbers to harass). Signs: photos of documents, spreadsheets with \
names+phones+addresses, "слив базы", "пробив по номеру".

- "Safe" — Everything else. News, discussions, memes, educational content, \
opinions, general media, entertainment.

IMPORTANT RULES:
- If an image is provided, analyze BOTH the image and any visible text in it.
- Transcribe ALL visible text in images, especially Russian text and slang.
- Focus on INTENT: news about drugs ≠ selling drugs. A joke about money ≠ scam.
- When uncertain between categories, choose the more dangerous one.
- When uncertain between Safe and any violation, lean toward the violation. \
False positives go to human review. False negatives risk the bot being deleted.

Respond in JSON:
{"category": "...", "confidence": 0.0-1.0, "reasoning": "explanation in Russian"}\
"""

VALID_CATEGORIES = {"Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe"}
MAX_RETRIES = 2
JSON_PATTERN = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _build_messages(text: str, caption: str, image_bytes: bytes | None) -> list[dict]:
    """Build chat messages for Gemma 4."""
    user_parts = []

    if image_bytes:
        pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
        user_parts.append({"type": "image", "image": pil_image})

    user_text = f"Classify this trigger content:\n\nText: {text or 'No text'}\nCaption: {caption or 'No caption'}"
    user_parts.append({"type": "text", "text": user_text})

    return [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {"role": "user", "content": user_parts},
    ]


def _parse_response(raw: str) -> dict | None:
    """Extract and validate JSON from model output."""
    match = JSON_PATTERN.search(raw)
    if not match:
        return None

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    category = data.get("category")
    if category not in VALID_CATEGORIES:
        return None

    confidence = data.get("confidence", 0.5)
    if isinstance(confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(confidence)))
    else:
        confidence = 0.5

    reasoning = data.get("reasoning", "")
    if not isinstance(reasoning, str):
        reasoning = str(reasoning)

    return {"category": category, "confidence": confidence, "reasoning": reasoning}


async def classify(text: str, caption: str, image_bytes: bytes | None) -> dict | None:
    """Classify content using Gemma 4. Returns dict with category/confidence/reasoning or None."""
    model, processor = await model_manager.ensure_loaded()
    messages = _build_messages(text, caption, image_bytes)

    for attempt in range(MAX_RETRIES + 1):
        try:
            inputs = processor.apply_chat_template(
                messages,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                add_generation_prompt=True,
            ).to(model.device)

            input_len = inputs["input_ids"].shape[-1]
            output = model.generate(**inputs, max_new_tokens=settings.MAX_NEW_TOKENS)
            raw = processor.decode(output[0][input_len:], skip_special_tokens=True)

            logger.debug("Model raw output (attempt %d): %s", attempt + 1, raw[:500])

            result = _parse_response(raw)
            if result:
                model_manager.increment_requests()
                return result

            logger.warning("Failed to parse model response (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, raw[:200])

        except Exception as e:
            logger.error("Inference error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, e)

    return None
```

- [ ] **Step 2: Commit**

```bash
git add inference/moderator.py
git commit -m "feat: moderator with system prompt and JSON parsing"
```

---

## Task 4: gRPC server (trigger-inference)

**Files:**
- Create: `trigger-inference/inference/server.py`

- [ ] **Step 1: Create server.py**

```python
# inference/server.py
import asyncio
import logging
import signal
import sys
from concurrent import futures
from pathlib import Path

import grpc

from generated import moderation_pb2, moderation_pb2_grpc
from inference.config import settings
from inference.model_manager import model_manager
from inference.moderator import classify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ModerationServicer(moderation_pb2_grpc.ModerationServiceServicer):
    async def Moderate(self, request, context):
        request_id = request.request_id
        logger.info("Moderate request %s (text=%d bytes, image=%d bytes)",
                     request_id, len(request.text), len(request.image))

        async with model_manager._semaphore:
            result = await classify(
                text=request.text,
                caption=request.caption,
                image_bytes=request.image if request.image else None,
            )

        if result is None:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Model failed to produce a valid response")
            return moderation_pb2.ModerationResponse()

        logger.info("Moderate result %s: %s (%.0f%%)",
                     request_id, result["category"], result["confidence"] * 100)

        return moderation_pb2.ModerationResponse(
            category=result["category"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            request_id=request_id,
        )

    async def HealthCheck(self, request, context):
        return moderation_pb2.HealthStatus(
            model_loaded=model_manager.is_loaded,
            gpu_memory_used_mb=model_manager.gpu_memory_used_mb(),
            gpu_memory_total_mb=model_manager.gpu_memory_total_mb(),
            uptime_seconds=model_manager.uptime_seconds,
            requests_processed=model_manager.requests_processed,
        )


async def serve():
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", settings.GRPC_MAX_MESSAGE_SIZE),
            ("grpc.max_receive_message_length", settings.GRPC_MAX_MESSAGE_SIZE),
        ],
    )
    moderation_pb2_grpc.add_ModerationServiceServicer_to_server(ModerationServicer(), server)

    listen_addr = f"[::]:{settings.GRPC_PORT}"

    if settings.TLS_CERT_PATH and settings.TLS_KEY_PATH:
        cert = Path(settings.TLS_CERT_PATH).read_bytes()
        key = Path(settings.TLS_KEY_PATH).read_bytes()
        creds = grpc.ssl_server_credentials([(key, cert)])
        server.add_secure_port(listen_addr, creds)
        logger.info("gRPC server listening on %s (TLS)", listen_addr)
    else:
        server.add_insecure_port(listen_addr)
        logger.info("gRPC server listening on %s (plaintext)", listen_addr)

    # Enable gRPC reflection for grpcurl and monitoring tools
    from grpc_reflection.v1alpha import reflection
    SERVICE_NAMES = (
        moderation_pb2.DESCRIPTOR.services_by_name["ModerationService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    await server.start()

    async def shutdown(sig):
        logger.info("Received %s, shutting down...", sig.name)
        await model_manager.unload()
        await server.stop(grace=5)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
```

- [ ] **Step 2: Commit**

```bash
git add inference/server.py
git commit -m "feat: gRPC server with TLS support and graceful shutdown"
```

---

## Task 5: Docker and deployment files (trigger-inference)

**Files:**
- Create: `trigger-inference/Dockerfile`
- Create: `trigger-inference/compose.yml`
- Create: `trigger-inference/.env.example`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile
FROM nvidia/cuda:13.0.1-runtime-ubuntu24.04

# APT cache
RUN echo 'Acquire::http::Proxy "http://10.10.40.23:3142";' > /etc/apt/apt.conf.d/01proxy

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip3 install --break-system-packages uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# Copy application code
COPY proto/ proto/
COPY inference/ inference/
COPY generated/ generated/

EXPOSE 50051

CMD ["uv", "run", "python", "-m", "inference.server"]
```

- [ ] **Step 2: Create compose.yml**

```yaml
# compose.yml
services:
  inference:
    build: .
    # image: 10.10.40.8:5000/trigger-inference:${TAG:-latest}
    restart: unless-stopped
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
      - MODEL_NAME=${MODEL_NAME:-google/gemma-4-e4b-it}
      - MODEL_UNLOAD_TIMEOUT=${MODEL_UNLOAD_TIMEOUT:-300}
      - HF_TOKEN=${HF_TOKEN:-}
      - GRPC_PORT=${GRPC_PORT:-50051}
      - MAX_NEW_TOKENS=${MAX_NEW_TOKENS:-256}
      - IMAGE_SOFT_TOKENS=${IMAGE_SOFT_TOKENS:-280}
    ports:
      - "${GRPC_PORT:-50051}:${GRPC_PORT:-50051}"
    volumes:
      - model_cache:/root/.cache/huggingface
    logging:
      options:
        max-size: "10m"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  model_cache:
```

- [ ] **Step 3: Create .env.example**

```bash
# .env.example
HF_TOKEN=hf_your_token_here
MODEL_NAME=google/gemma-4-e4b-it
MODEL_UNLOAD_TIMEOUT=300
GRPC_PORT=50051
MAX_NEW_TOKENS=256
IMAGE_SOFT_TOKENS=280
# TLS_CERT_PATH=/path/to/cert.pem
# TLS_KEY_PATH=/path/to/key.pem
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile compose.yml .env.example
git commit -m "feat: Docker and compose for GPU deployment"
```

---

## Task 6: Bot — schemas and models update

**Files:**
- Modify: `app/schemas/moderation.py`
- Modify: `app/db/models/moderation_history.py`

- [ ] **Step 1: Update ModerationLLMResult categories in schemas/moderation.py**

Add `Violence` and `PersonalData` to both `ModerationLLMResult.category` and `ModerationAlert.category`. Remove `image_description` from `ModerationAlert`.

```python
# app/schemas/moderation.py — updated ModerationLLMResult
class ModerationLLMResult(BaseModel):
    category: Literal["Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return v


class ModerationAlert(BaseModel):
    trigger_id: int
    chat_id: int
    category: Literal["Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe", "Error"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str | None = None
```

- [ ] **Step 2: Update ModerationStep enum in moderation_history.py**

Replace vision/text steps with AI steps:

```python
class ModerationStep(StrEnum):
    CREATED = "created"
    QUEUED = "queued"

    PROCESSING_STARTED = "processing_started"
    MEDIA_PROCESSING = "media_processing"
    MEDIA_PROCESSED = "media_processed"
    AI_ANALYZING = "ai_analyzing"
    AI_COMPLETED = "ai_completed"

    AUTO_APPROVED = "auto_approved"
    AUTO_FLAGGED = "auto_flagged"
    AUTO_ERROR = "auto_error"

    ALERT_SENT = "alert_sent"
    MANUAL_APPROVED = "manual_approved"
    MANUAL_DELETED = "manual_deleted"
    MANUAL_BANNED = "manual_banned"
    REQUEUED = "requeued"
```

- [ ] **Step 3: Commit**

```bash
git add app/schemas/moderation.py app/db/models/moderation_history.py
git commit -m "feat: add Violence, PersonalData categories; replace vision/text steps with AI steps"
```

---

## Task 7: Bot — gRPC client (llm.py rewrite)

**Files:**
- Create: `proto/moderation.proto` (copy from trigger-inference)
- Generate: `generated/moderation_pb2.py`, `generated/moderation_pb2_grpc.py`
- Rewrite: `app/worker/llm.py`
- Modify: `app/core/config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add grpcio dependencies to pyproject.toml**

Add to `[project] dependencies`:
```
"grpcio>=1.70.0",
"grpcio-tools>=1.70.0",
```

- [ ] **Step 2: Copy proto and generate stubs**

```bash
mkdir -p proto generated
cp ~/myprojects/trigger-inference/proto/moderation.proto proto/
uv run python -m grpc_tools.protoc \
  -Iproto \
  --python_out=generated \
  --grpc_python_out=generated \
  proto/moderation.proto
touch generated/__init__.py
```

- [ ] **Step 3: Update config.py — remove Ollama, add gRPC settings**

Replace Ollama settings (lines 23-25) with:

```python
# gRPC inference server
GRPC_INFERENCE_URL: str = "10.10.40.24:50051"
GRPC_TIMEOUT: int = 120
GRPC_CA_CERT_PATH: str = ""
GRPC_STALE_ALERT_TIMEOUT: int = 300
```

- [ ] **Step 4: Rewrite app/worker/llm.py**

Complete replacement:

```python
# app/worker/llm.py
import logging
import uuid
from pathlib import Path

import grpc

from app.core.config import settings
from app.schemas.moderation import ModerationLLMResult
from generated import moderation_pb2, moderation_pb2_grpc

logger = logging.getLogger(__name__)


class InferenceUnavailableError(Exception):
    """Raised when GPU inference server is unreachable (retryable)."""


class InferenceClient:
    """gRPC client for GPU inference server."""

    def __init__(self):
        self._channel: grpc.aio.Channel | None = None
        self._stub: moderation_pb2_grpc.ModerationServiceStub | None = None

    async def moderate(
        self, text: str, caption: str, image: bytes | None
    ) -> ModerationLLMResult | None:
        """Classify content via GPU inference server.

        Returns ModerationLLMResult on success, None on model error.
        Raises InferenceUnavailableError on transient gRPC errors (for requeue).
        """
        stub = await self._get_stub()
        request = moderation_pb2.ModerationRequest(
            text=text or "",
            caption=caption or "",
            image=image or b"",
            request_id=str(uuid.uuid4()),
        )
        try:
            response = await stub.Moderate(
                request, timeout=settings.GRPC_TIMEOUT
            )
            return ModerationLLMResult(
                category=response.category,
                confidence=response.confidence,
                reasoning=response.reasoning,
            )
        except grpc.aio.AioRpcError as e:
            if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                logger.warning("gRPC server unavailable: code=%s details=%s", e.code(), e.details())
                raise InferenceUnavailableError(str(e)) from e
            logger.error("gRPC inference error: code=%s details=%s", e.code(), e.details())
            return None

    async def health_check(self) -> dict | None:
        """Check GPU server health."""
        stub = await self._get_stub()
        try:
            response = await stub.HealthCheck(
                moderation_pb2.Empty(), timeout=5
            )
            return {
                "model_loaded": response.model_loaded,
                "gpu_memory_used_mb": response.gpu_memory_used_mb,
                "gpu_memory_total_mb": response.gpu_memory_total_mb,
                "uptime_seconds": response.uptime_seconds,
                "requests_processed": response.requests_processed,
            }
        except grpc.aio.AioRpcError as e:
            logger.error("gRPC health check error: %s", e)
            return None

    async def _get_stub(self) -> moderation_pb2_grpc.ModerationServiceStub:
        """Lazy-init gRPC channel with optional TLS."""
        if self._stub is None:
            options = [
                ("grpc.max_send_message_length", 16_777_216),
                ("grpc.max_receive_message_length", 16_777_216),
            ]
            if settings.GRPC_CA_CERT_PATH:
                creds = grpc.ssl_channel_credentials(
                    root_certificates=Path(settings.GRPC_CA_CERT_PATH).read_bytes()
                )
                self._channel = grpc.aio.secure_channel(
                    settings.GRPC_INFERENCE_URL, creds, options=options
                )
            else:
                self._channel = grpc.aio.insecure_channel(
                    settings.GRPC_INFERENCE_URL, options=options
                )
            self._stub = moderation_pb2_grpc.ModerationServiceStub(self._channel)
        return self._stub

    async def close(self):
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None


inference_client = InferenceClient()
```

- [ ] **Step 5: Commit**

```bash
git add proto/ generated/ app/worker/llm.py app/core/config.py pyproject.toml
git commit -m "feat: gRPC inference client replacing Ollama calls"
```

---

## Task 8: Bot — service.py and main.py refactor

**Files:**
- Modify: `app/worker/service.py`
- Modify: `app/worker/main.py`

- [ ] **Step 1: Refactor service.py — process_media returns bytes**

Replace `process_media` function. Key change: returns `bytes | None` instead of `str`. Resize moved here from llm.py.

```python
# app/worker/service.py — updated imports and process_media
import logging
import tempfile
from pathlib import Path

from app.core.broker import broker
from app.core.valkey import valkey
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert, ModerationLLMResult, TriggerModerationTask
from app.services.moderation_history_service import add_history_step
from app.worker.image import extract_frame_from_video_path, resize_image
from app.worker.telegram import download_file, download_file_to_path, get_telegram_file_url
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VIDEO_TYPES = {"video", "video_note", "animation"}


async def process_media(task: TriggerModerationTask) -> bytes | None:
    """Download and prepare media as resized JPEG bytes for gRPC inference."""
    if not task.file_id or not task.file_type:
        return None

    if task.file_type not in ("photo", "sticker", *VIDEO_TYPES):
        return None

    file_url = await get_telegram_file_url(task.file_id)
    if not file_url:
        logger.warning("Failed to get file URL for trigger %d", task.trigger_id)
        return None

    if file_url.lower().endswith(".tgs"):
        logger.warning("Skipping TGS sticker for trigger %d", task.trigger_id)
        return None

    is_video = task.file_type in VIDEO_TYPES or (
        task.file_type == "sticker" and file_url.lower().endswith(".webm")
    )

    if is_video:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "video"
            if not await download_file_to_path(file_url, str(video_path)):
                logger.warning("Failed to download video for trigger %d", task.trigger_id)
                return None

            image_data = await extract_frame_from_video_path(video_path, position=0.5)
            if not image_data:
                logger.warning("Failed to extract frame for trigger %d", task.trigger_id)
                return None
    else:
        image_data = await download_file(file_url)
        if not image_data:
            logger.warning("Failed to download file for trigger %d", task.trigger_id)
            return None

    # Resize and ensure JPEG output (proto contract requires JPEG)
    return resize_image(image_data, ensure_jpeg=True)
```

**Note:** `resize_image()` in `app/worker/image.py` needs a patch — currently it only converts to JPEG
when resizing. Add `ensure_jpeg` parameter:

```python
# Patch to app/worker/image.py — resize_image()
def resize_image(image_data: bytes, max_size: int = 512, ensure_jpeg: bool = False) -> bytes:
    """Resize image and optionally force JPEG output."""
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
        logger.error(f"Failed to resize image: {e}")
        return image_data
```

- [ ] **Step 2: Update handle_moderation_result — remove image_description parameter**

```python
async def handle_moderation_result(
    session: AsyncSession,
    trigger: Trigger,
    result: ModerationLLMResult | None,
) -> None:
    """Update trigger status based on moderation result."""
    trigger_id = trigger.id
    chat_id = trigger.chat_id

    await valkey.delete(f"trigger_processing:{trigger_id}")

    if not result:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = "AI Error"
        await add_history_step(
            session, trigger_id, ModerationStep.AUTO_ERROR,
            details={"error": "AI failed to process"},
        )
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")

        if await session.get(Trigger, trigger_id):
            alert = ModerationAlert(
                trigger_id=trigger_id, chat_id=chat_id,
                category="Error", reasoning="AI failed to process",
            )
            await broker.publish(alert, "q.moderation.alerts")
            await add_history_step(session, trigger_id, ModerationStep.ALERT_SENT)
            await session.commit()
        else:
            logger.warning("Trigger %d deleted during moderation, skipping alert", trigger_id)
        return

    if result.category == "Safe":
        trigger.moderation_status = ModerationStatus.SAFE
        trigger.moderation_reason = result.reasoning
        await add_history_step(
            session, trigger_id, ModerationStep.AUTO_APPROVED,
            details={"reasoning": result.reasoning},
        )
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")
        logger.info("Trigger %d: Safe. %s", trigger_id, result.reasoning)
    else:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = f"{result.category}: {result.reasoning}"
        await add_history_step(
            session, trigger_id, ModerationStep.AUTO_FLAGGED,
            details={
                "category": result.category,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
            },
        )
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")

        if await session.get(Trigger, trigger_id):
            alert = ModerationAlert(
                trigger_id=trigger_id, chat_id=chat_id,
                category=result.category,
                confidence=result.confidence,
                reasoning=result.reasoning,
            )
            await broker.publish(alert, "q.moderation.alerts")
            await add_history_step(session, trigger_id, ModerationStep.ALERT_SENT)
            await session.commit()
            logger.info("Trigger %d: %s. %s", trigger_id, result.category, result.reasoning)
        else:
            logger.warning("Trigger %d deleted during moderation, skipping alert", trigger_id)
```

- [ ] **Step 3: Refactor main.py — simplify analyze_trigger**

Replace `analyze_trigger` function and imports:

```python
# Updated imports at top of main.py
from app.worker.llm import inference_client, InferenceUnavailableError
from app.worker.service import handle_moderation_result, process_media
# Remove: from app.worker.llm import call_moderation_model


@broker.subscriber("q.moderation.analyze")
async def analyze_trigger(task: TriggerModerationTask) -> None:
    logger.info("Analyzing trigger %d from chat %d", task.trigger_id, task.chat_id)

    async with async_session() as session:
        await add_history_step(session, task.trigger_id, ModerationStep.PROCESSING_STARTED)
        await session.commit()

        # 1. Process media (download, extract frame, resize to JPEG)
        image_bytes: bytes | None = None
        if task.file_id and task.file_type:
            await add_history_step(session, task.trigger_id, ModerationStep.MEDIA_PROCESSING)
            await session.commit()

            image_bytes = await process_media(task)

            await add_history_step(
                session, task.trigger_id, ModerationStep.MEDIA_PROCESSED,
                details={"has_image": image_bytes is not None},
            )
            await session.commit()

        # 2. Call AI inference (single gRPC call)
        await add_history_step(session, task.trigger_id, ModerationStep.AI_ANALYZING)
        await session.commit()

        try:
            result = await inference_client.moderate(
                text=task.text_content or "",
                caption=task.caption or "",
                image=image_bytes,
            )
        except InferenceUnavailableError:
            # GPU server unavailable — requeue for retry, send stale alert if needed
            logger.warning("GPU inference unavailable for trigger %d, requeueing", task.trigger_id)
            alert_key = "gpu_stale_alert_sent"
            if not await valkey.get(alert_key):
                await valkey.set(alert_key, "1", ex=settings.GRPC_STALE_ALERT_TIMEOUT)
                from app.bot.instance import bot
                try:
                    await bot.send_message(
                        settings.MODERATION_CHANNEL_ID,
                        "⚠️ GPU inference server недоступен. "
                        "Запросы модерации копятся в очереди.",
                    )
                except Exception as e:
                    logger.error("Failed to send GPU stale alert: %s", e)
            raise  # FastStream will nack + requeue the message

        await add_history_step(
            session, task.trigger_id, ModerationStep.AI_COMPLETED,
            details={
                "category": result.category if result else "error",
                "confidence": result.confidence if result else None,
                "reasoning": result.reasoning if result else None,
            },
        )
        await session.commit()

        # 3. Update database
        trigger = await session.get(Trigger, task.trigger_id)
        if not trigger:
            logger.warning("Trigger %d not found", task.trigger_id)
            return

        await handle_moderation_result(session, trigger, result)
```

- [ ] **Step 4: Commit**

```bash
git add app/worker/service.py app/worker/main.py
git commit -m "feat: simplified moderation pipeline — single gRPC call instead of vision+text"
```

---

## Task 9: Bot — compose and env updates

**Files:**
- Modify: `compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Update compose.yml ai_worker environment**

In the `ai_worker` service environment section, replace:
```yaml
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}
```

With:
```yaml
      GRPC_INFERENCE_URL: ${GRPC_INFERENCE_URL:-10.10.40.24:50051}
      GRPC_TIMEOUT: ${GRPC_TIMEOUT:-120}
      GRPC_CA_CERT_PATH: ${GRPC_CA_CERT_PATH:-}
      GRPC_STALE_ALERT_TIMEOUT: ${GRPC_STALE_ALERT_TIMEOUT:-300}
```

Keep Ollama env vars commented out for rollback.

- [ ] **Step 2: Update .env.example**

Add gRPC settings, comment out Ollama:

```bash
# AI Moderation (gRPC inference server)
GRPC_INFERENCE_URL=10.10.40.24:50051
GRPC_TIMEOUT=120
# GRPC_CA_CERT_PATH=/path/to/ca.pem
GRPC_STALE_ALERT_TIMEOUT=300

# Legacy Ollama (keep for rollback)
# OLLAMA_BASE_URL=http://localhost:11434
```

- [ ] **Step 3: Commit**

```bash
git add compose.yml .env.example
git commit -m "feat: replace Ollama env with gRPC inference settings in compose"
```

---

## Task 10: Frontend — ModerationTimeline update

**Files:**
- Modify: `frontend/src/components/ModerationTimeline.tsx`

- [ ] **Step 1: Update STEP_CONFIG — replace vision/text with AI steps**

Replace lines 34-37 in ModerationTimeline.tsx:

```typescript
// Remove these 4 lines:
vision_analyzing: { label: 'Vision анализирует', icon: Brain, colorClass: 'text-purple-500' },
vision_completed: { label: 'Vision завершил', icon: Brain, colorClass: 'text-green-500' },
text_analyzing: { label: 'Классификация', icon: Brain, colorClass: 'text-purple-500' },
text_completed: { label: 'Классификация завершена', icon: Brain, colorClass: 'text-green-500' },

// Add these 2 lines:
ai_analyzing: { label: 'AI анализирует', icon: Brain, colorClass: 'text-purple-500' },
ai_completed: { label: 'AI анализ завершён', icon: Brain, colorClass: 'text-green-500' },
```

- [ ] **Step 2: Improve detail rendering for AI steps**

Replace the details rendering block (lines 223-247) with an enhanced version that shows category badges, progress bars, and full reasoning text:

```typescript
{item.details && Object.keys(item.details).length > 0 && (
  <div className="mt-2 text-sm">
    {'category' in item.details && item.details.category != null && (
      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium mr-2 ${
        {
          Safe: 'bg-green-500/20 text-green-400',
          Drugs: 'bg-red-500/20 text-red-400',
          Porn: 'bg-red-500/20 text-red-400',
          Violence: 'bg-red-500/20 text-red-400',
          Scam: 'bg-orange-500/20 text-orange-400',
          PersonalData: 'bg-yellow-500/20 text-yellow-400',
          Error: 'bg-red-500/20 text-red-400',
        }[String(item.details.category)] || 'bg-hint/20 text-hint'
      }`}>
        {String(item.details.category)}
      </span>
    )}
    {'confidence' in item.details && item.details.confidence != null && (
      <div className="mt-1.5 flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-secondary-bg rounded-full overflow-hidden">
          <div
            className="h-full bg-link rounded-full transition-all"
            style={{ width: `${(Number(item.details.confidence) * 100).toFixed(0)}%` }}
          />
        </div>
        <span className="text-xs text-hint w-8">
          {(Number(item.details.confidence) * 100).toFixed(0)}%
        </span>
      </div>
    )}
    {showReasoning && 'reasoning' in item.details && item.details.reasoning != null && (
      <p className="mt-1.5 text-text leading-relaxed">
        {String(item.details.reasoning)}
      </p>
    )}
    {'marked_by' in item.details && item.details.marked_by != null && (
      <p className="text-xs text-hint">Модератор: {String(item.details.marked_by)}</p>
    )}
    {'deleted_by' in item.details && item.details.deleted_by != null && (
      <p className="text-xs text-hint">Удалил: {String(item.details.deleted_by)}</p>
    )}
    {'banned_by' in item.details && item.details.banned_by != null && (
      <p className="text-xs text-hint">Забанил: {String(item.details.banned_by)}</p>
    )}
    {'error' in item.details && item.details.error != null && (
      <p className="text-red-400">Ошибка: {String(item.details.error)}</p>
    )}
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ModerationTimeline.tsx
git commit -m "feat: update moderation timeline — AI steps and enhanced detail display"
```

---

## Task 11: Integration — deploy and verify

- [ ] **Step 1: Build and push inference image on aiserver**

```bash
ssh aiserver
cd ~/trigger-inference
docker build -t 10.10.40.8:5000/trigger-inference:v0.1.0 .
docker push 10.10.40.8:5000/trigger-inference:v0.1.0
```

- [ ] **Step 2: Create .env and start inference server**

```bash
cp .env.example .env
# Edit .env: set HF_TOKEN
docker compose up -d
docker compose logs -f inference
```

Wait for: `gRPC server listening on [::]:50051 (plaintext)`

- [ ] **Step 3: Test health check**

```bash
grpcurl -plaintext 10.10.40.24:50051 moderation.ModerationService/HealthCheck
```

Expected: JSON response with `model_loaded: false` (lazy load).

- [ ] **Step 4: Deploy updated bot on trigger server**

Tag new version, push, deploy as usual via GitLab CI.

- [ ] **Step 5: Verify end-to-end**

Create a test trigger with `/add test_moderation` in a non-trusted chat. Check:
1. ai_worker logs: `gRPC inference` calls
2. ModerationTimeline in webapp: shows `AI анализирует` → `AI анализ завершён`
3. Trigger gets `Safe` or `Flagged` status
4. On aiserver: `docker compose logs inference` shows model loading on first request

- [ ] **Step 6: Verify idle unload**

Wait 5 minutes after last request. Check:
```bash
nvidia-smi
```

Expected: 0 MiB GPU memory used (model unloaded).
