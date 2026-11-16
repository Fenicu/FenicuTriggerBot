import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker import image


@pytest.mark.parametrize("operation", ["probe", "frame", "convert"])
async def test_timeout_kills_and_reaps_media_process(operation):
    proc = MagicMock()
    proc.returncode = None
    proc.communicate = AsyncMock(side_effect=[TimeoutError, (b"", b"")])
    proc.wait = AsyncMock()
    with patch.object(image.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)):
        if operation == "probe":
            assert await image._get_video_duration(Path("missing-video")) == 1.0
        elif operation == "frame":
            assert await image._extract_single_frame(Path("missing-video"), 0.0, Path("missing-frame")) is None
        else:
            assert await image._convert_with_ffmpeg(b"invalid-image") is None
    proc.kill.assert_called_once_with()
    # communicate после kill дочитывает PIPE и ждёт завершения процесса.
    assert proc.communicate.await_count == 2


@pytest.mark.parametrize("operation", ["probe", "frame", "convert"])
async def test_cancellation_also_kills_media_process(operation):
    proc = MagicMock()
    proc.returncode = None
    proc.communicate = AsyncMock(side_effect=[asyncio.CancelledError, (b"", b"")])
    with patch.object(image.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(asyncio.CancelledError):
            if operation == "probe":
                await image._get_video_duration(Path("missing-video"))
            elif operation == "frame":
                await image._extract_single_frame(Path("missing-video"), 0.0, Path("missing-frame"))
            else:
                await image._convert_with_ffmpeg(b"invalid-image")
    proc.kill.assert_called_once_with()
    assert proc.communicate.await_count == 2


async def test_timeout_reaps_a_real_child_process():
    proc = await asyncio.create_subprocess_exec(
        "sleep", "60", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    wait_for = asyncio.wait_for

    async def short_wait(future, timeout):
        return await wait_for(future, 0.01)

    try:
        with (
            patch.object(image.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)),
            patch.object(image.asyncio, "wait_for", new=short_wait),
        ):
            assert await image._get_video_duration(Path("missing-video")) == 1.0
        assert proc.returncode is not None
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
