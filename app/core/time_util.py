import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def get_timezone() -> ZoneInfo:
    """Returns the configured timezone."""
    return ZoneInfo(settings.BOT_TIMEZONE)


def format_dt(dt: datetime, format: str | None = None) -> str:
    """
    Converts the input UTC datetime to the configured timezone and formats it.
    Defaults to "%d.%m.%Y %H:%M" if format is not specified.
    """
    if format is None:
        format = "%d.%m.%Y %H:%M"

    local_dt = dt.astimezone(get_timezone())
    return local_dt.strftime(format)


def parse_time_string(time_str: str) -> int | None:
    """
    Parses a time string like "10m", "2h", "1d", "1w" into seconds.
    Returns None if the format is invalid.
    """
    if not time_str:
        return None

    match = re.match(r"^(\d+)([mhdw])$", time_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    if unit == "w":
        return value * 604800

    return None
