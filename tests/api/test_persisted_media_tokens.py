from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app.api.v1.endpoints.media import verify_media_token
from app.services.rich_html import _media_url


def test_persisted_media_url_has_long_lived_file_bound_signature():
    file_id = "long+telegram/file=id"
    with patch("time.time", return_value=1000000):
        url = _media_url("https://example.com/api/v1/", file_id)
    query = parse_qs(urlsplit(url).query)
    assert query["file_id"] == [file_id]
    assert "token" in query
    with patch("time.time", return_value=1000000 + 365 * 24 * 3600):
        assert verify_media_token(file_id, query["token"][0])
        assert not verify_media_token("another-file", query["token"][0])
