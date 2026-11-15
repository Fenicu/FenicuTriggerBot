"""Regex-триггеры без учёта регистра сворачивают регистр так же, как exact/contains."""

from app.db.models.trigger import MatchType, Trigger
from app.services import trigger_service


def _trigger(pattern: str, *, case_sensitive: bool = False) -> Trigger:
    return Trigger(
        id=1,
        chat_id=-100,
        key_phrase=pattern,
        content={"text": "ok"},
        match_type=MatchType.REGEXP,
        is_case_sensitive=case_sensitive,
    )


async def test_case_insensitive_regex_ss_matches_sharp_s():
    trigger = _trigger(r"^strasse$")

    assert await trigger_service.find_matches([trigger], "STRAßE") == [trigger]


async def test_case_insensitive_regex_sharp_s_matches_ss():
    trigger = _trigger(r"stra(ß)e")

    assert await trigger_service.find_matches([trigger], "die STRASSE") == [trigger]


async def test_case_sensitive_regex_does_not_fold():
    trigger = _trigger(r"^strasse$", case_sensitive=True)

    assert await trigger_service.find_matches([trigger], "straße") == []
    assert await trigger_service.find_matches([trigger], "Strasse") == []
