from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from yarl import URL

from app.worker import links


async def _chunks():
    yield b"<title>Checked</title>"


def _response(location=None):
    response = MagicMock()
    response.status = 302 if location else 200
    response.headers = {"Location": location} if location else {"Content-Type": "text/html"}
    response.content.iter_chunked.return_value = _chunks()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


@pytest.mark.parametrize("start_url", ["https://start.example/path", "https://пример.рф/path", "https://faß.de/path"])
@pytest.mark.parametrize("redirect", [False, True])
async def test_request_connector_uses_only_checked_dns_answers(redirect, start_url):
    session = MagicMock()
    session.get.side_effect = [_response("https://next.example/path"), _response()] if redirect else [_response()]
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    clients = []

    def make_client(**kwargs):
        clients.append(kwargs)
        return session

    checked = ["93.184.216.34", "2606:4700::1111"]
    with (
        patch.object(links, "_resolve_ips", AsyncMock(return_value=checked)) as dns,
        patch.object(links.aiohttp, "ClientSession", side_effect=make_client),
    ):
        result = await links.safe_fetch(start_url)
        assert result and "Checked" in result.summary
        assert len(clients) == (2 if redirect else 1)
        for index, client in enumerate(clients):
            connector = client["connector"]
            host = URL(start_url).raw_host if index == 0 else "next.example"
            # Даже после смены DNS ответ коннектора остаётся проверенным.
            dns.return_value = ["127.0.0.1"]
            answers = await connector._resolve_host(host, 443)
            assert [answer["host"] for answer in answers] == checked
            assert all(answer["hostname"] == host for answer in answers)
            await connector.close()
    assert dns.await_count == (2 if redirect else 1)
    assert session.get.call_args.args[0] == ("https://next.example/path" if redirect else start_url)


@pytest.mark.parametrize("ips", [["93.184.216.34", "127.0.0.1"], ["::1"], [], ["invalid"]])
async def test_unsafe_dns_never_creates_a_client(ips):
    with (
        patch.object(links, "_resolve_ips", AsyncMock(return_value=ips)),
        patch.object(links.aiohttp, "ClientSession") as client,
    ):
        assert await links.safe_fetch("https://start.example") is None
    client.assert_not_called()
