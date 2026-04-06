import logging

import aioboto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class S3Storage:
    def __init__(self) -> None:
        self.session = aioboto3.Session(
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY.get_secret_value(),
        )
        scheme = "https" if settings.S3_SECURE else "http"
        self.endpoint_url = f"{scheme}://{settings.S3_ENDPOINT}"
        self.bucket = settings.S3_BUCKET

    def _client(self) -> aioboto3.Session.client:
        return self.session.client("s3", endpoint_url=self.endpoint_url)

    async def ensure_bucket(self) -> None:
        """Ensure bucket exists and has lifecycle policy."""
        try:
            async with self._client() as s3:
                try:
                    await s3.head_bucket(Bucket=self.bucket)
                except ClientError:
                    await s3.create_bucket(Bucket=self.bucket)
                    logger.info("Created bucket %s", self.bucket)

                    await s3.put_bucket_lifecycle_configuration(
                        Bucket=self.bucket,
                        LifecycleConfiguration={
                            "Rules": [
                                {
                                    "ID": "expire-7-days",
                                    "Status": "Enabled",
                                    "Filter": {"Prefix": ""},
                                    "Expiration": {"Days": 7},
                                }
                            ]
                        },
                    )
                    logger.info("Set lifecycle policy for %s", self.bucket)
        except Exception as e:
            logger.error("Error ensuring bucket: %s", e)

    async def put_file(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Upload file to S3."""
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=object_name,
                    Body=data,
                    ContentType=content_type,
                )
        except Exception as e:
            logger.error("Error uploading %s: %s", object_name, e)
            raise

    async def get_file(self, object_name: str) -> tuple[bytes, str] | None:
        """Get file from S3. Returns (data, content_type) or None."""
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self.bucket, Key=object_name)
                data = await response["Body"].read()
                content_type = response.get("ContentType", "application/octet-stream")
                return data, content_type
        except ClientError:
            return None
        except Exception:
            return None

    async def delete_file(self, object_name: str) -> None:
        """Delete file from S3."""
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self.bucket, Key=object_name)
        except Exception as e:
            logger.error("Error deleting %s: %s", object_name, e)

    async def exists(self, object_name: str) -> bool:
        """Check if file exists."""
        try:
            async with self._client() as s3:
                await s3.head_object(Bucket=self.bucket, Key=object_name)
                return True
        except ClientError:
            return False


storage = S3Storage()
