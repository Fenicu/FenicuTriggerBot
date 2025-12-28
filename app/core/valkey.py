from redis.asyncio import Redis

from app.core.config import settings

valkey = Redis.from_url(str(settings.VALKEY_URL), decode_responses=True)
