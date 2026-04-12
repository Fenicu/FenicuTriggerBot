"""Tests for app/worker/image.py — image processing utilities."""

import io

import pytest
from PIL import Image
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    """Create a real JPEG image in memory."""
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_png(width: int = 100, height: int = 100, mode: str = "RGB") -> bytes:
    """Create a real PNG image in memory."""
    img = Image.new(mode, (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgba_png(width: int = 100, height: int = 100) -> bytes:
    """Create an RGBA PNG to test alpha conversion."""
    return _make_png(width, height, mode="RGBA")


# ── _detect_format ──────────────────────────────────────────────────────────


def test_detect_format_jpeg():
    from app.worker.image import _detect_format

    data = _make_jpeg()
    assert _detect_format(data) == "JPEG"


def test_detect_format_png():
    from app.worker.image import _detect_format

    data = _make_png()
    assert _detect_format(data) == "PNG"


def test_detect_format_webp():
    from app.worker.image import _detect_format

    # WebP magic: RIFF....WEBP
    data = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 50
    assert _detect_format(data) == "WebP"


def test_detect_format_riff_not_webp():
    from app.worker.image import _detect_format

    # RIFF but not WebP (e.g., AVI)
    data = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 50
    assert _detect_format(data) == "RIFF/WebP"


def test_detect_format_gif():
    from app.worker.image import _detect_format

    data = b"GIF89a" + b"\x00" * 50
    assert _detect_format(data) == "GIF"


def test_detect_format_bmp():
    from app.worker.image import _detect_format

    data = b"BM" + b"\x00" * 50
    assert _detect_format(data) == "BMP"


def test_detect_format_unknown():
    from app.worker.image import _detect_format

    data = b"\x01\x02\x03\x04\x05\x06\x07\x08" + b"\x00" * 50
    result = _detect_format(data)
    assert "unknown" in result


def test_detect_format_mp4_heic():
    from app.worker.image import _detect_format

    data = b"\x00\x00\x00" + b"\x00" * 50
    assert _detect_format(data) == "MP4/HEIC"


# ── resize_image ────────────────────────────────────────────────────────────


async def test_resize_image_small_jpeg_passthrough():
    """Small JPEG without ensure_jpeg should return original data."""
    from app.worker.image import resize_image

    data = _make_jpeg(50, 50)
    result = await resize_image(data, max_size=512, ensure_jpeg=False)

    assert result == data  # No resize needed, no format change


async def test_resize_image_ensure_jpeg_converts():
    """ensure_jpeg=True should always return JPEG even for small images."""
    from app.worker.image import resize_image

    data = _make_jpeg(50, 50)
    result = await resize_image(data, max_size=512, ensure_jpeg=True)

    assert result is not None
    # Result should be valid JPEG
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


async def test_resize_image_oversized():
    """Large image should be resized to max_size."""
    from app.worker.image import resize_image

    data = _make_jpeg(1000, 1000)
    result = await resize_image(data, max_size=256, ensure_jpeg=True)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert max(img.size) <= 256


async def test_resize_image_rgba_conversion():
    """RGBA image should be converted to RGB for JPEG output."""
    from app.worker.image import resize_image

    data = _make_rgba_png()
    result = await resize_image(data, max_size=512, ensure_jpeg=True)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.mode == "RGB"
    assert img.format == "JPEG"


async def test_resize_image_png_to_jpeg():
    """PNG should be convertible to JPEG with ensure_jpeg."""
    from app.worker.image import resize_image

    data = _make_png()
    result = await resize_image(data, max_size=512, ensure_jpeg=True)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


async def test_resize_image_invalid_data_falls_back_to_ffmpeg():
    """Invalid image data should trigger ffmpeg fallback."""
    from app.worker.image import resize_image

    data = b"this is not an image at all" * 10

    with patch("app.worker.image._convert_with_ffmpeg", new_callable=AsyncMock) as mock_ffmpeg:
        mock_ffmpeg.return_value = b"ffmpeg_output"
        result = await resize_image(data, ensure_jpeg=True)

    assert result == b"ffmpeg_output"
    mock_ffmpeg.assert_awaited_once()


async def test_resize_image_invalid_data_ffmpeg_also_fails():
    """If both PIL and ffmpeg fail, should return None."""
    from app.worker.image import resize_image

    data = b"garbage data"

    with patch("app.worker.image._convert_with_ffmpeg", new_callable=AsyncMock) as mock_ffmpeg:
        mock_ffmpeg.return_value = None
        result = await resize_image(data, ensure_jpeg=True)

    assert result is None


async def test_resize_image_preserves_aspect_ratio():
    """Thumbnail should preserve aspect ratio."""
    from app.worker.image import resize_image

    data = _make_jpeg(800, 400)  # 2:1 ratio
    result = await resize_image(data, max_size=200, ensure_jpeg=True)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    # With thumbnail, the long side should be at most 200
    assert max(img.size) <= 200
    # Aspect ratio should be approximately preserved
    w, h = img.size
    assert abs(w / h - 2.0) < 0.1


async def test_resize_image_palette_mode_converted():
    """P-mode (palette) PNG should be converted to RGB."""
    from app.worker.image import resize_image

    img = Image.new("P", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    result = await resize_image(data, max_size=512, ensure_jpeg=True)

    assert result is not None
    out = Image.open(io.BytesIO(result))
    assert out.mode == "RGB"


# ── combine_frames_horizontal ──────────────────────────────────────────────


def test_combine_frames_empty():
    from app.worker.image import combine_frames_horizontal

    result = combine_frames_horizontal([])
    assert result is None


def test_combine_frames_single():
    from app.worker.image import combine_frames_horizontal

    frame = _make_jpeg(100, 100)
    result = combine_frames_horizontal([frame])
    assert result == frame  # Single frame returned as-is


def test_combine_frames_multiple():
    from app.worker.image import combine_frames_horizontal

    frames = [_make_jpeg(100, 100), _make_jpeg(100, 100), _make_jpeg(100, 100)]
    result = combine_frames_horizontal(frames, max_height=256)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.height == 256
    # Combined width should be roughly 3x of each resized frame
    assert img.width > 256


def test_combine_frames_different_sizes():
    from app.worker.image import combine_frames_horizontal

    frames = [_make_jpeg(200, 100), _make_jpeg(100, 200), _make_jpeg(150, 150)]
    result = combine_frames_horizontal(frames, max_height=128)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.height == 128


def test_combine_frames_invalid_frame_skipped():
    """Invalid frame data should be skipped, valid frames still combined."""
    from app.worker.image import combine_frames_horizontal

    frames = [_make_jpeg(100, 100), b"not_an_image", _make_jpeg(100, 100)]
    result = combine_frames_horizontal(frames, max_height=256)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.height == 256


def test_combine_frames_all_invalid():
    """If all frames are invalid, should return None."""
    from app.worker.image import combine_frames_horizontal

    frames = [b"garbage1", b"garbage2"]
    result = combine_frames_horizontal(frames)

    assert result is None


def test_combine_frames_output_is_jpeg():
    from app.worker.image import combine_frames_horizontal

    frames = [_make_jpeg(100, 100), _make_jpeg(100, 100)]
    result = combine_frames_horizontal(frames, max_height=128)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


def test_combine_frames_rgba_converted():
    """RGBA frames should be converted to RGB for JPEG output."""
    from app.worker.image import combine_frames_horizontal

    frames = [_make_rgba_png(100, 100), _make_rgba_png(100, 100)]
    result = combine_frames_horizontal(frames, max_height=128)

    assert result is not None
    img = Image.open(io.BytesIO(result))
    assert img.mode == "RGB"


# ── extract_frame_from_video_path (mocked ffmpeg) ──────────────────────────


@patch("app.worker.image._extract_single_frame", new_callable=AsyncMock)
@patch("app.worker.image._get_video_duration", new_callable=AsyncMock)
async def test_extract_frame_from_video_path(mock_duration, mock_extract):
    from app.worker.image import extract_frame_from_video_path

    mock_duration.return_value = 10.0
    mock_extract.return_value = b"frame_data"

    result = await extract_frame_from_video_path("/tmp/test.mp4", position=0.5)

    assert result == b"frame_data"
    mock_duration.assert_awaited_once()
    # Seek time should be 10.0 * 0.5 = 5.0
    call_args = mock_extract.call_args
    assert abs(call_args.args[1] - 5.0) < 0.01


@patch("app.worker.image._extract_single_frame", new_callable=AsyncMock)
@patch("app.worker.image._get_video_duration", new_callable=AsyncMock)
async def test_extract_frame_custom_position(mock_duration, mock_extract):
    from app.worker.image import extract_frame_from_video_path

    mock_duration.return_value = 20.0
    mock_extract.return_value = b"frame_at_start"

    result = await extract_frame_from_video_path("/tmp/test.mp4", position=0.1)

    assert result == b"frame_at_start"
    call_args = mock_extract.call_args
    assert abs(call_args.args[1] - 2.0) < 0.01


# ── extract_frames_from_video_path (mocked ffmpeg) ─────────────────────────


@patch("app.worker.image._extract_single_frame", new_callable=AsyncMock)
@patch("app.worker.image._get_video_duration", new_callable=AsyncMock)
async def test_extract_frames_default_positions(mock_duration, mock_extract):
    from app.worker.image import extract_frames_from_video_path

    mock_duration.return_value = 30.0
    mock_extract.side_effect = [b"frame_0", b"frame_1", b"frame_2"]

    result = await extract_frames_from_video_path("/tmp/test.mp4")

    assert len(result) == 3
    assert mock_extract.await_count == 3


@patch("app.worker.image._extract_single_frame", new_callable=AsyncMock)
@patch("app.worker.image._get_video_duration", new_callable=AsyncMock)
async def test_extract_frames_partial_failure(mock_duration, mock_extract):
    """If some frames fail, return only successful ones."""
    from app.worker.image import extract_frames_from_video_path

    mock_duration.return_value = 30.0
    mock_extract.side_effect = [b"frame_0", None, b"frame_2"]

    result = await extract_frames_from_video_path("/tmp/test.mp4")

    assert len(result) == 2
    assert result == [b"frame_0", b"frame_2"]


@patch("app.worker.image._extract_single_frame", new_callable=AsyncMock)
@patch("app.worker.image._get_video_duration", new_callable=AsyncMock)
async def test_extract_frames_all_fail(mock_duration, mock_extract):
    from app.worker.image import extract_frames_from_video_path

    mock_duration.return_value = 30.0
    mock_extract.return_value = None

    result = await extract_frames_from_video_path("/tmp/test.mp4")

    assert result == []


@patch("app.worker.image._extract_single_frame", new_callable=AsyncMock)
@patch("app.worker.image._get_video_duration", new_callable=AsyncMock)
async def test_extract_frames_custom_positions(mock_duration, mock_extract):
    from app.worker.image import extract_frames_from_video_path

    mock_duration.return_value = 100.0
    mock_extract.side_effect = [b"f0", b"f1"]

    result = await extract_frames_from_video_path("/tmp/test.mp4", positions=[0.25, 0.75])

    assert len(result) == 2
    assert mock_extract.await_count == 2
