import pytest

from app.api.v1.endpoints.auth import create_auth_token
from tests.factories import create_user


@pytest.mark.parametrize("kind,expected", [("anonymous", 401), ("user", 403), ("moderator", 200)])
async def test_stats_requires_admin(api_client, db_session, kind, expected):
    headers = {}
    if kind != "anonymous":
        user = await create_user(db_session, is_bot_moderator=kind == "moderator")
        await db_session.commit()
        headers["Authorization"] = f"Bearer {create_auth_token(user.id)}"
    response = await api_client.get("/api/v1/stats", headers=headers)
    assert response.status_code == expected
