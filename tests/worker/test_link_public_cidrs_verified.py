from ipaddress import ip_network
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.worker.links import _is_public_host


@pytest.mark.parametrize("ip", ["198.18.0.0", "198.18.1.2", "198.19.255.255"])
async def test_default_transparent_proxy_cidr_is_allowed(ip):
    with patch("app.worker.links._resolve_ips", AsyncMock(return_value=[ip])):
        assert await _is_public_host("blocked.example") is True


async def test_public_cidr_allowance_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LINK_FETCH_PUBLIC_CIDRS", [])
    with patch("app.worker.links._resolve_ips", AsyncMock(return_value=["198.18.1.2"])):
        assert await _is_public_host("blocked.example") is False


async def test_custom_cidr_is_allowed(monkeypatch):
    monkeypatch.setattr(settings, "LINK_FETCH_PUBLIC_CIDRS", [ip_network("203.0.113.0/24")])
    with patch("app.worker.links._resolve_ips", AsyncMock(return_value=["203.0.113.10"])):
        assert await _is_public_host("proxy.example") is True


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "::1", "224.0.0.1"])
async def test_proxy_allowance_does_not_allow_other_non_public_answers(ip):
    with patch("app.worker.links._resolve_ips", AsyncMock(return_value=["198.18.1.2", ip])):
        assert await _is_public_host("blocked.example") is False


def test_invalid_cidr_configuration_is_rejected():
    with pytest.raises(ValidationError):
        type(settings)(_env_file=None, **(settings.model_dump() | {"LINK_FETCH_PUBLIC_CIDRS": ["bad-cidr"]}))
