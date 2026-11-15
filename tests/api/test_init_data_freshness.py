import hashlib
import hmac
from urllib.parse import urlencode
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.deps import validate_init_data, validate_init_data_from_query
from app.core.config import settings


def signed_init_data(auth_date):
    data = {"user": '{"id":123,"first_name":"Test"}'}
    if auth_date is not None:
        data["auth_date"] = str(auth_date)
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    payload = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    data["hash"] = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


@pytest.mark.parametrize("query", [False, True])
@pytest.mark.parametrize("auth_date", [None, "bad", -1, 1000000 - 86401, 1000000 + 301])
async def test_rejects_invalid_or_stale_init_data(query, auth_date):
    data = signed_init_data(auth_date)
    with patch("time.time", return_value=1000000, create=True):
        with pytest.raises(HTTPException) as exc:
            if query:
                await validate_init_data_from_query(auth=data, auth_type="twa")
            else:
                await validate_init_data(authorization=f"twa-init-data {data}")
    assert exc.value.status_code == 401


@pytest.mark.parametrize("query", [False, True])
@pytest.mark.parametrize("offset", [-86400, 0, 300])
async def test_accepts_fresh_signed_init_data(query, offset):
    data = signed_init_data(1000000 + offset)
    with patch("time.time", return_value=1000000, create=True):
        result = (
            await validate_init_data_from_query(auth=data, auth_type="twa")
            if query
            else await validate_init_data(authorization=f"twa-init-data {data}")
        )
    assert result == {"type": "webapp", "data": data}


async def test_configurable_max_age(monkeypatch):
    monkeypatch.setattr(settings, "INIT_DATA_MAX_AGE_SECONDS", 60, raising=False)
    with patch("time.time", return_value=1000000, create=True):
        with pytest.raises(HTTPException):
            await validate_init_data(authorization=f"twa-init-data {signed_init_data(999939)}")


def test_compose_exposes_configurable_init_data_age():
    from pathlib import Path

    import yaml

    services = yaml.safe_load(Path("compose.yml").read_text())["services"]
    assert services["bot"]["environment"]["INIT_DATA_MAX_AGE_SECONDS"] == "${INIT_DATA_MAX_AGE_SECONDS:-86400}"
