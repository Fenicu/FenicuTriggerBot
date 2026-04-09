# GPU Inference Refactoring: Gemma 4 via gRPC

**Дата:** 2026-04-10
**Статус:** Draft (rev.2 — после ревью Codex)

## Мотивация

Текущая AI-модерация через Ollama (qwen3-vl:8b + aya-expanse:8b) показала низкое качество.
Бот ранее чуть не был удалён Telegram из-за наркошопов, сохранявших прайсы и контакты через триггеры.
Цель — максимально надёжная защита от контента, нарушающего Telegram ToS.

## Решение

Миграция на единую мультимодальную модель **Gemma 4 e4b** (google/gemma-4-e4b-it, ~8B total params / ~4B effective)
на выделенном GPU-сервере, доступном по **gRPC**. Модель загружается с **INT4 квантизацией**
(~4GB веса + ~4-6GB KV-cache/активации = ~8-10GB на V100 16GB).

### Что даёт переход

- Одна модель вместо двух: видит оригинальное изображение + текст → сразу классифицирует
- Прямой контроль через torch + transformers вместо Ollama
- Выделенный GPU (Tesla V100 16GB) с автоматической выгрузкой модели по idle-таймауту
- INT4 квантизация — модель занимает ~8-10GB VRAM, оставляя запас для транскодирования
- Типизированный gRPC-контракт вместо свободного JSON по HTTP

---

## Инфраструктура

### GPU-сервер

- **Хост:** aiserver (10.10.40.24)
- **GPU:** Tesla V100-SXM2-16GB, CUDA 13.0, Driver 580.95
- **ОС:** Ubuntu 24.04
- **Docker:** 29.1.3 + nvidia-container-toolkit 1.18.1
- **Общий ресурс:** GPU также используется для транскодирования видео

### Бот-сервер

- **Хост:** trigger
- **Сервисы:** bot, ai_worker, postgres, valkey, rabbitmq, rustfs, traefik
- **Сеть:** 10.10.40.0/24 — прямая связность с aiserver, plaintext gRPC

---

## Архитектура

```
┌─────────────────────────────────────────┐     gRPC (plaintext/TLS)     ┌──────────────────────────┐
│ trigger server                          │ ◄──────────────────────────► │ aiserver (10.10.40.24)   │
│                                         │                              │                          │
│  ┌─────────────┐    ┌────────────────┐  │     ModerationRequest        │  ┌────────────────────┐  │
│  │   bot       │───►│  RabbitMQ      │  │     (text + caption +        │  │ trigger-inference  │  │
│  │ (aiogram)   │    │ q.moderation.  │  │      image bytes)            │  │                    │  │
│  └─────────────┘    │   analyze      │  │ ──────────────────────────►  │  │ model_manager:     │  │
│                     └───────┬────────┘  │                              │  │  load/unload       │  │
│                             │           │     ModerationResponse       │  │  idle timeout      │  │
│                     ┌───────▼────────┐  │     (category + confidence   │  │                    │  │
│                     │  ai_worker     │  │      + reasoning)            │  │ moderator:         │  │
│                     │  (FastStream)  │  │ ◄──────────────────────────  │  │  prompt + parse    │  │
│                     │                │  │                              │  │                    │  │
│                     │ 1. Download    │  │                              │  │ server:            │  │
│                     │    media       │  │                              │  │  gRPC endpoint     │  │
│                     │ 2. Resize/     │  │                              │  │  health check      │  │
│                     │    extract     │  │                              │  └────────────────────┘  │
│                     │ 3. gRPC call   │  │                              │                          │
│                     │ 4. Handle      │  │                              │  Gemma 4 e4b (INT4)      │
│                     │    result      │  │                              │  ~8-10GB VRAM loaded     │
│                     └────────────────┘  │                              │                          │
└─────────────────────────────────────────┘                              └──────────────────────────┘
```

**Принцип:** GPU-сервер — тупая inference-машина. Ничего не знает про Telegram, БД, RabbitMQ.
Вся бизнес-логика (скачивание файлов, модерация, алерты) остаётся на trigger-сервере.

---

## gRPC-контракт

```protobuf
syntax = "proto3";

package moderation;

service ModerationService {
  rpc Moderate (ModerationRequest) returns (ModerationResponse);
  rpc HealthCheck (Empty) returns (HealthStatus);
}

message Empty {}

message ModerationRequest {
  string text = 1;              // текст триггера (может быть пустым)
  string caption = 2;           // подпись к медиа (может быть пустой)
  bytes image = 3;              // JPEG, ≤512px, уже обработанное
  string request_id = 4;        // UUID для трейсинга
}

message ModerationResponse {
  string category = 1;          // Drugs|Porn|Scam|Violence|PersonalData|Safe
  float confidence = 2;         // 0.0–1.0
  string reasoning = 3;         // объяснение на русском
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

**Ограничения:**
- `GRPC_MAX_MESSAGE_SIZE = 16MB` (для больших изображений)
- Один unary RPC `Moderate` — без стриминга (запрос атомарный)

---

## GPU-сервер: trigger-inference

### Структура проекта

```
trigger-inference/
├── proto/
│   └── moderation.proto
├── inference/
│   ├── __init__.py
│   ├── server.py                 # gRPC сервер, точка входа
│   ├── model_manager.py          # загрузка/выгрузка модели
│   ├── moderator.py              # промпт, вызов модели, парсинг
│   └── config.py                 # pydantic-settings
├── generated/
│   └── moderation_pb2.py
│   └── moderation_pb2_grpc.py
├── Dockerfile
├── compose.yml
├── pyproject.toml
└── README.md
```

### model_manager.py

Управляет жизненным циклом модели в VRAM.

**Состояния:** `unloaded` → `loading` → `ready` → `unloaded`

**Загрузка (lazy, по первому запросу):**
```python
from transformers import TorchAoConfig, Gemma4ForConditionalGeneration, AutoProcessor

quantization_config = TorchAoConfig("int4_weight_only", group_size=128)
model = Gemma4ForConditionalGeneration.from_pretrained(
    "google/gemma-4-e4b-it",
    dtype=torch.float16,       # V100 НЕ поддерживает bfloat16
    device_map="auto",
    attn_implementation="sdpa",
    quantization_config=quantization_config,
)
processor = AutoProcessor.from_pretrained(
    "google/gemma-4-e4b-it",
    padding_side="left"
)
```

**VRAM-бюджет (V100 16GB):**
- INT4 веса: ~4GB
- KV-cache + активации: ~4-6GB
- CUDA context: ~0.5GB
- Итого при инференсе: ~8-10GB, остаётся ~6-8GB для транскодирования

**Выгрузка по таймауту:**
- После каждого запроса сбрасывается idle-таймер
- По истечении `MODEL_UNLOAD_TIMEOUT` (по умолчанию 300 секунд):
  - `del model` + `del processor`
  - `torch.cuda.empty_cache()`
  - `gc.collect()`
- Потокобезопасность: `asyncio.Lock` на load/unload

**Concurrency guard:**
- `asyncio.Semaphore(1)` — строго один inference-запрос одновременно
- Предотвращает OOM от параллельных KV-cache аллокаций на shared GPU
- Дополнительные запросы ждут в очереди (gRPC не отклоняет, просто задержка)

**Метрики:**
- `torch.cuda.memory_allocated()` / `torch.cuda.get_device_properties(0).total_memory`
- Счётчик обработанных запросов
- Время работы сервера

### moderator.py

Формирует промпт и парсит ответ модели.

**Вход:** text (str), caption (str), image (bytes | None)

**Формат сообщений для Gemma 4:**
```python
messages = [
    {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
    {"role": "user", "content": content_parts},  # image + text
]
```

Где `content_parts`:
- Если есть image: `[{"type": "image", "image": PIL.Image}, {"type": "text", "text": user_text}]`
- Если только текст: `[{"type": "text", "text": user_text}]`

**Visual token budget:**
- Настраивается через `IMAGE_SOFT_TOKENS` (по умолчанию 280)
- Для задачи модерации достаточно 280 (default) — баланс между качеством и VRAM
- Поддерживаемые значения: 70, 140, 280, 560, 1120

**Генерация:**
```python
inputs = processor.apply_chat_template(
    messages, tokenize=True, return_dict=True,
    return_tensors="pt", add_generation_prompt=True,
).to(model.device)

input_len = inputs["input_ids"].shape[-1]
output = model.generate(**inputs, max_new_tokens=256)
# Слайсим prompt-токены, декодируем только ответ модели
response = processor.decode(output[0][input_len:], skip_special_tokens=True)
```

**Парсинг ответа:**
- Извлечь JSON из ответа модели (regex для `{...}`)
- Валидировать: category ∈ {Drugs, Porn, Scam, Violence, PersonalData, Safe}
- Clamp confidence в [0.0, 1.0]
- При невалидном ответе — retry (до 2 попыток)
- При полном провале — вернуть gRPC error (INTERNAL)

### server.py

**gRPC сервер:**
- Порт: `GRPC_PORT` (по умолчанию 50051)
- TLS: если заданы `TLS_CERT_PATH` + `TLS_KEY_PATH` — secure channel, иначе plaintext
- `Moderate()`: ensure_loaded() → classify() → response
- `HealthCheck()`: статус модели, VRAM, uptime, счётчик
- Graceful shutdown: при SIGTERM/SIGINT — выгрузить модель, остановить сервер

### config.py

Переменные окружения:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `MODEL_NAME` | `google/gemma-4-e4b-it` | HuggingFace model ID |
| `MODEL_UNLOAD_TIMEOUT` | `300` | Секунды idle до выгрузки из VRAM |
| `GRPC_PORT` | `50051` | Порт gRPC сервера |
| `GRPC_MAX_MESSAGE_SIZE` | `16777216` | Максимальный размер сообщения (16MB) |
| `TLS_CERT_PATH` | `""` | Путь к TLS-сертификату (пусто = plaintext) |
| `TLS_KEY_PATH` | `""` | Путь к TLS-ключу |
| `HF_TOKEN` | `""` | Токен HuggingFace для скачивания модели |
| `MAX_NEW_TOKENS` | `256` | Максимум токенов генерации (JSON-ответ компактный) |
| `IMAGE_SOFT_TOKENS` | `280` | Visual token budget (70/140/280/560/1120) |

### Docker

**Dockerfile:**
- Базовый образ: `nvidia/cuda:13.0-runtime-ubuntu24.04`
- APT кеш: `http://10.10.40.23:3142`
- Установка: `uv` (через `pip install uv` или curl)
- Python-зависимости через `uv sync` с `--index-url http://10.10.40.8:3141/root/pypi/+simple/ --trusted-host 10.10.40.8`
- Зависимости: `torch`, `torchao`, `torchvision`, `transformers`, `grpcio`, `grpcio-tools`, `pydantic-settings`, `pillow`
- Entrypoint: `python -m inference.server`

**compose.yml:**
```yaml
services:
  inference:
    image: 10.10.40.8:5000/trigger-inference:${TAG:-latest}
    restart: unless-stopped
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
      - MODEL_UNLOAD_TIMEOUT=${MODEL_UNLOAD_TIMEOUT:-300}
      - HF_TOKEN=${HF_TOKEN:-}
    ports:
      - "50051:50051"
    volumes:
      - model_cache:/root/.cache/huggingface
    logging:
      options:
        max-size: "10m"

volumes:
  model_cache:
```

---

## Изменения в боте

### app/core/config.py

**Убрать:**
```python
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_VISION_MODEL: str = "qwen3-vl:8b"
OLLAMA_TEXT_MODEL: str = "aya-expanse:8b"
```

**Добавить:**
```python
GRPC_INFERENCE_URL: str = "10.10.40.24:50051"
GRPC_TIMEOUT: int = 120                    # таймаут вызова gRPC (секунды)
GRPC_CA_CERT_PATH: str = ""                # пусто = plaintext
GRPC_STALE_ALERT_TIMEOUT: int = 300        # секунды до алерта о недоступности GPU
```

### app/worker/llm.py — полная переписка

**Убрать:** все функции (`call_vision_model`, `call_moderation_model`, `unload_unknown_models`), aiohttp-вызовы к Ollama.

**Добавить:** gRPC-клиент.

```python
class InferenceClient:
    """gRPC-клиент для GPU inference сервера."""

    def __init__(self):
        self._channel = None
        self._stub = None

    async def moderate(
        self, text: str, caption: str, image: bytes | None
    ) -> ModerationLLMResult | None:
        """Классифицировать контент через GPU-сервер."""
        stub = await self._get_stub()
        request = ModerationRequest(
            text=text or "",
            caption=caption or "",
            image=image or b"",
            request_id=str(uuid.uuid4()),
        )
        try:
            response = await stub.Moderate(request, timeout=settings.GRPC_TIMEOUT)
            return ModerationLLMResult(
                category=response.category,
                confidence=response.confidence,
                reasoning=response.reasoning,
            )
        except grpc.aio.AioRpcError as e:
            logger.error("gRPC error: %s", e)
            return None

    async def health(self) -> HealthStatus | None:
        """Проверить состояние GPU-сервера."""
        ...

    async def _get_stub(self):
        """Lazy-init gRPC канала с опциональным TLS."""
        if self._stub is None:
            if settings.GRPC_CA_CERT_PATH:
                creds = grpc.ssl_channel_credentials(
                    root_certificates=Path(settings.GRPC_CA_CERT_PATH).read_bytes()
                )
                self._channel = grpc.aio.secure_channel(settings.GRPC_INFERENCE_URL, creds)
            else:
                self._channel = grpc.aio.insecure_channel(settings.GRPC_INFERENCE_URL)
            self._stub = ModerationServiceStub(self._channel)
        return self._stub

    async def close(self):
        if self._channel:
            await self._channel.close()
```

### app/worker/service.py — упрощение

**`process_media()`** — переписать: возвращает `bytes | None` (готовые JPEG-байты) вместо `str` (описание).

Текущий код: ресайз изображения выполняется внутри `call_vision_model()` в `llm.py`.
Нужно вынести ресайз (`resize_image()` из `image.py`) в `process_media()`, чтобы gRPC получал
готовый JPEG ≤512px. Функция `process_media()` становится единственным местом подготовки медиа:
1. Скачать файл с Telegram API
2. Для видео: извлечь кадр через ffmpeg
3. Ресайзить до ≤512px
4. Вернуть JPEG-байты

Убрать двухстадийный pipeline (vision описание → text классификация).

**`handle_moderation_result()`** — адаптировать:
- Поле `image_description` в `ModerationAlert` заменяется на `reasoning` из ответа модели.
  Модель объясняет что увидела прямо в reasoning — отдельное описание изображения не нужно.
- `ModerationAlert.image_description` → удалить поле (или оставить пустым для обратной совместимости).

### app/worker/main.py — analyze_trigger()

**Текущий pipeline:**
```
PROCESSING_STARTED → MEDIA_PROCESSING → MEDIA_PROCESSED →
VISION_ANALYZING → VISION_COMPLETED → TEXT_ANALYZING → TEXT_COMPLETED →
AUTO_APPROVED / AUTO_FLAGGED / AUTO_ERROR
```

**Новый pipeline:**
```
PROCESSING_STARTED → MEDIA_PROCESSING → MEDIA_PROCESSED →
AI_ANALYZING → AI_COMPLETED →
AUTO_APPROVED / AUTO_FLAGGED / AUTO_ERROR
```

Один вызов `inference_client.moderate(text, caption, image_bytes)` вместо двух.

**Алерт о недоступности GPU:**
- Если gRPC-вызов падает с `UNAVAILABLE` / `DEADLINE_EXCEEDED`:
  - НЕ записывать `AUTO_ERROR` (триггер остаётся `PENDING`)
  - Вернуть сообщение в очередь RabbitMQ (raise exception → FastStream retry/requeue)
  - Если триггер в `PENDING` дольше `GRPC_STALE_ALERT_TIMEOUT`:
    - Отправить одноразовый алерт в `MODERATION_CHANNEL_ID`
    - Флаг `gpu_stale_alert_sent` в Valkey (TTL = GRPC_STALE_ALERT_TIMEOUT)
    - Флаг автоматически сбрасывается по TTL — при следующем цикле алерт пошлётся снова если GPU всё ещё недоступен

### app/schemas/moderation.py

**ModerationLLMResult** — расширить категории:
```python
category: Literal["Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe"]
```

**ModerationAlert** — аналогично:
```python
category: Literal["Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe", "Error"]
```

### app/db/models/moderation_history.py

**ModerationStep** — обновить:
- Убрать: `VISION_ANALYZING`, `VISION_COMPLETED`, `TEXT_ANALYZING`, `TEXT_COMPLETED`
- Добавить: `AI_ANALYZING`, `AI_COMPLETED`

Старые записи в БД не ломаются — step хранится как string, фронтенд показывает fallback.

### compose.yml (trigger server)

Сервис `ai_worker` — замена env:
```yaml
# Убрать:
OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}

# Добавить:
GRPC_INFERENCE_URL: ${GRPC_INFERENCE_URL:-10.10.40.24:50051}
GRPC_TIMEOUT: ${GRPC_TIMEOUT:-120}
GRPC_CA_CERT_PATH: ${GRPC_CA_CERT_PATH:-}
GRPC_STALE_ALERT_TIMEOUT: ${GRPC_STALE_ALERT_TIMEOUT:-300}
```

### pyproject.toml (trigger bot)

- Убрать: (ничего, aiohttp используется и для Telegram API)
- Добавить: `grpcio>=1.70.0`, `grpcio-tools>=1.70.0`

---

## Фронтенд

### frontend/src/components/ModerationTimeline.tsx

**STEP_CONFIG** — обновить:

Убрать:
```typescript
vision_analyzing: { label: 'Vision анализирует', icon: Brain, colorClass: 'text-purple-500' },
vision_completed: { label: 'Vision завершил', icon: Brain, colorClass: 'text-green-500' },
text_analyzing:   { label: 'Классификация', icon: Brain, colorClass: 'text-purple-500' },
text_completed:   { label: 'Классификация завершена', icon: Brain, colorClass: 'text-green-500' },
```

Добавить:
```typescript
ai_analyzing: { label: 'AI анализирует', icon: Brain, colorClass: 'text-purple-500' },
ai_completed: { label: 'AI анализ завершён', icon: Brain, colorClass: 'text-green-500' },
```

**Улучшение отображения деталей AI:**

Для шагов `ai_completed` и `auto_flagged` — развёрнутый блок вместо обрезанных строк:
- Категория: цветной бейдж (Safe=зелёный, Drugs=красный, Porn=красный, Scam=оранжевый, Violence=красный, PersonalData=жёлтый)
- Уверенность: прогресс-бар с процентами
- Reasoning: полный текст, нормальный размер шрифта, без truncate

---

## Промпт модерации

Единый system prompt для Gemma 4:

```
You are a Telegram content moderation system. Your task is to classify
user-submitted content (text and/or image) that will be stored as an
automated reply trigger in a Telegram bot.

Classify into EXACTLY ONE category:

- "Drugs" — Sale, advertising, or distribution of illegal substances.
  Signs: price lists, shop contacts, bot links selling drugs, substance
  photos with intent to sell, coded language (❄️ 🍬 🌿 💎), stash/dead-drop
  instructions ("клад", "закладка"), graffiti with contacts (@username, URLs).
  Russian slang: "мефедрон", "скорость", "шишки", "гашиш", "амфетамин",
  "закладки", "кристаллы". Obfuscated: "м3ф", "ск", "a-pvp".

- "Porn" — Explicit sexual content: genitalia, sexual acts, masturbation,
  pornographic links/previews. ESPECIALLY flag any content that may involve
  or depict minors (CSAM) — this is the highest-priority violation.
  Does NOT include: artistic nudity, medical illustrations, memes without
  explicit content.

- "Scam" — Recruitment for illegal activities or financial fraud.
  Signs: "easy money no experience", courier/delivery jobs with suspicious
  pay, pyramid schemes, fake giveaways, phishing links.
  Russian: "работа курьером", "высокий доход без опыта", "лёгкие деньги",
  "прогулки по городу", "вакансия кладмен".

- "Violence" — Threats, extremist content, terrorism propaganda, weapon
  sales/trading, graphic violence, calls for violence against individuals
  or groups. Signs: weapon photos with price tags, extremist symbols,
  beheading/torture imagery, death threats.
  Russian: "купить ствол", "заказать", "убью", propaganda channels.

- "PersonalData" — Leaked personal data: passport scans, ID documents,
  database dumps with personal info, doxxing (publishing private addresses,
  phone numbers to harass). Signs: photos of documents, spreadsheets with
  names+phones+addresses, "слив базы", "пробив по номеру".

- "Safe" — Everything else. News, discussions, memes, educational content,
  opinions, general media, entertainment.

IMPORTANT RULES:
- If an image is provided, analyze BOTH the image and any visible text in it.
- Transcribe ALL visible text in images, especially Russian text and slang.
- Focus on INTENT: news about drugs ≠ selling drugs. A joke about money ≠ scam.
- When uncertain between categories, choose the more dangerous one.
- When uncertain between Safe and any violation, lean toward the violation.
  False positives go to human review. False negatives risk the bot being deleted.

Respond in JSON:
{"category": "...", "confidence": 0.0-1.0, "reasoning": "explanation in Russian"}
```

User message: `[image if present] + "Classify this trigger content:\n\nText: {text}\nCaption: {caption}"`

---

## Файлы без изменений

- `app/worker/image.py` — ресайз и ffmpeg-экстракция (используется из обновлённого `service.py`)
- `app/worker/telegram.py` — скачивание файлов с Telegram API
- `app/bot/handlers/moderation.py` — обработка алертов и inline-кнопки
- `app/services/moderation_history_service.py` — запись шагов
- `app/api/v1/endpoints/triggers.py` — API эндпоинты + SSE
- Все остальные хендлеры, миддлвари, сервисы бота

---

## Порядок деплоя

1. Задеплоить `trigger-inference` на aiserver → модель скачивается, gRPC слушает :50051
2. Проверить health: `grpcurl -plaintext 10.10.40.24:50051 moderation.ModerationService/HealthCheck`
3. Задеплоить обновлённого бота (новый тег) → ai_worker подключается к gRPC
4. Проверить: создать тестовый триггер, убедиться что pipeline работает
5. Старые env Ollama **НЕ удалять** до подтверждения стабильности (минимум 1 неделя)

## Откат

**Важно:** при деплое старые Ollama-переменные остаются в `.env`, просто не используются.
Это позволяет откатиться без восстановления конфигурации.

Если что-то пошло не так:
1. Откатить тег бота на предыдущую версию (Ollama-based)
2. ai_worker подхватит старый код и начнёт работать с Ollama как раньше
3. Запросы, накопившиеся в RabbitMQ, обработаются старым кодом
4. inference-сервер на aiserver можно остановить (`docker compose down`)

**Частичный откат** (если проблема только в inference-сервере):
- Запросы копятся в RabbitMQ (PENDING), бот работает в штатном режиме
- Починить/перезапустить inference → запросы обработаются автоматически
