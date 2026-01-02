import re


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
