import logging
from collections.abc import AsyncGenerator
from io import BytesIO

from aiohttp import ClientResponse
from miniopy_async import Minio
from miniopy_async.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinioStorage:
    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_USER,
            secret_key=settings.MINIO_PASSWORD.get_secret_value(),
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET

    async def ensure_bucket(self) -> None:
        """Ensure bucket exists and has lifecycle policy."""
        try:
            if not await self.client.bucket_exists(self.bucket):
                await self.client.make_bucket(self.bucket)
                logger.info(f"Created bucket {self.bucket}")

                lifecycle_config = {
                    "Rules": [
                        {
                            "ID": "expire-7-days",
                            "Status": "Enabled",
                            "Filter": {"Prefix": ""},
                            "Expiration": {"Days": 7},
                        }
                    ]
                }
                await self.client.set_bucket_lifecycle(self.bucket, lifecycle_config)
                logger.info(f"Set lifecycle policy for {self.bucket}")
        except S3Error as e:
            logger.error(f"MinIO error ensuring bucket: {e}")
        except Exception as e:
            logger.error(f"Error ensuring bucket: {e}")

    async def put_file(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Upload file to MinIO."""
        try:
            await self.client.put_object(
                self.bucket,
                object_name,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )
        except Exception as e:
            logger.error(f"Error uploading {object_name}: {e}")
            raise

    async def get_file(self, object_name: str) -> ClientResponse | None:
        """Get file from MinIO."""
        try:
            return await self.client.get_object(self.bucket, object_name)
        except Exception:
            return None

    async def delete_file(self, object_name: str) -> None:
        """Delete file from MinIO."""
        try:
            await self.client.remove_object(self.bucket, object_name)
        except Exception as e:
            logger.error(f"Error deleting {object_name}: {e}")

    async def exists(self, object_name: str) -> bool:
        """Check if file exists."""
        try:
            await self.client.stat_object(self.bucket, object_name)
            return True
        except Exception:
            return False

    async def stream_content(self, response: ClientResponse) -> AsyncGenerator[bytes]:
        """Stream content from MinIO response."""
        try:
            async for chunk in response.content.iter_chunked(8192):
                yield chunk
        finally:
            response.close()


storage = MinioStorage()
