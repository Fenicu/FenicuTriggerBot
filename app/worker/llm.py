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
