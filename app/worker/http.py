"""Shared aiohttp session for worker with stall detection.

sock_read=30 means: if no data arrives for 30 seconds, the request is aborted.
This doesn't limit total download time — large files on slow connections keep
flowing as long as data keeps arriving.
"""

import aiohttp

STALL_TIMEOUT = aiohttp.ClientTimeout(sock_read=30)


class _SessionHolder:
    """Module-level HTTP session singleton."""

    _instance: aiohttp.ClientSession | None = None

    @classmethod
    async def get(cls) -> aiohttp.ClientSession:
        if cls._instance is None or cls._instance.closed:
            cls._instance = aiohttp.ClientSession(timeout=STALL_TIMEOUT)
        return cls._instance

    @classmethod
    async def close(cls) -> None:
        if cls._instance and not cls._instance.closed:
            await cls._instance.close()
            cls._instance = None


get_session = _SessionHolder.get
close_session = _SessionHolder.close
