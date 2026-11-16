import pytest
from pydantic import ValidationError

from app.schemas.chat_settings import UpdateChatFullSettingsRequest


@pytest.mark.parametrize("limit", [1, 2, 10, 15, 100])
def test_accepts_frontend_and_existing_warning_limits(limit):
    request = UpdateChatFullSettingsRequest(warn_limit=limit)
    assert request.warn_limit == limit


@pytest.mark.parametrize("limit", [-1, 0, 101, 2**31])
def test_rejects_warning_limits_outside_supported_range(limit):
    with pytest.raises(ValidationError):
        UpdateChatFullSettingsRequest(warn_limit=limit)


@pytest.mark.parametrize(
    "field,values",
    [
        ("captcha_timeout", [60, 120, 300, 600]),
        ("captcha_max_attempts", list(range(1, 11))),
        ("captcha_ban_duration", [3600, 86400, 259200, 604800]),
        ("warn_duration", [0, 600, 3600, 86400, 604800]),
        ("tags_weight_reactions", [0, 3, 2147483647]),
        ("tags_weight_replies", [0, 2, 2147483647]),
        ("tags_weight_messages", [0, 1, 2147483647]),
        ("tags_daily_message_limit", [1, 50, 2147483647]),
        ("tags_daily_reaction_limit", [1, 3, 2147483647]),
        ("tags_custom", [None, {str(level): "x" * 16 for level in range(1, 6)}]),
        ("tags_thresholds", [[50, 200, 500, 1500, 5000], [1, 2, 3, 4, 2147483647]]),
    ],
)
def test_accepts_frontend_settings_choices_and_boundaries(field, values):
    for value in values:
        request = UpdateChatFullSettingsRequest(**{field: value})
        assert getattr(request, field) == value
