import json

MAX_MESSAGE_PAYLOAD_BYTES = 64 * 1024


def validate_message_payload(value: dict | None) -> dict | None:
    if value is None:
        return value
    try:
        serialized = json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as e:
        raise ValueError("Invalid message payload") from e
    if len(serialized) > MAX_MESSAGE_PAYLOAD_BYTES:
        raise ValueError("Message payload must not exceed 64 KiB")
    for field in ("text", "caption"):
        text = value.get(field)
        if text is not None and (not isinstance(text, str) or len(text) > 32768):
            raise ValueError(f"{field} must be a string of at most 32768 characters")
    return value
