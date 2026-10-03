"""
Runtime patch for aiogram 3.31.0: exponential validation of nested rich text.

``RichTextUnion`` is a recursive smart-mode union (``str | list | 26 RichText* models``)
without a discriminator, so pydantic tries every member at every nesting level, and each
failed member still validates its own nested ``text`` field. An incoming message with five
levels of formatting (spoiler -> bold -> subscript -> italic -> underline) blocks the event
loop for ~10 s at 100% CPU, each extra level multiplies that by ~22.

The patch makes ``TelegramObject.remove_unset`` (the ``mode="before"`` model validator that
every aiogram type already runs) reject input whose ``type`` doesn't match the model's
``Literal`` before the other fields are validated, so validation becomes linear in depth.

aiogram builds every model schema at import time and those schemas keep a reference to the
original ``remove_unset`` function, so the function body is swapped in place (``__code__``)
instead of replacing the attribute. That relies on 3.31.0 internals, hence the strict
version pin: remove this module once the bot runs an aiogram release with the upstream fix.
"""

import sys
from enum import Enum
from importlib.metadata import version
from typing import Any, Literal, get_args, get_origin

from aiogram.types import base
from pydantic_core import PydanticCustomError

EXPECTED_AIOGRAM_VERSION = "3.31.0"
_PATCHED_MARKER = "__trigger_rich_text_patch__"
_GLOBAL_NAME = "__trigger_remove_unset__"

_LITERAL_ERROR = "literal_error"
_LITERAL_MESSAGE = "Input should be {expected}"

_TYPE_LITERALS: dict[type, tuple[Any, ...] | None] = {}


def _fail(reason: str) -> None:
    sys.stderr.write(
        f"FATAL: {reason}\n"
        f"  aiogram rich text patch: {__file__}\n"
        f"  applied from: patch_aiogram() in app/main.py\n"
        f"  installed aiogram: {base.__file__.removesuffix('/types/base.py')}\n"
        "This patch targets aiogram internals of exactly "
        f"{EXPECTED_AIOGRAM_VERSION}. Check whether the new aiogram version already fixes "
        "exponential validation of nested RichText and remove or update the patch.\n",
    )
    sys.exit(1)


def _get_type_literal(cls: type) -> tuple[Any, ...] | None:
    field = cls.model_fields.get("type")
    if field is None or get_origin(field.annotation) is not Literal:
        return None
    return tuple(item.value if isinstance(item, Enum) else item for item in get_args(field.annotation))


def _remove_unset(cls: type, values: Any) -> Any:
    # Same as aiogram 3.31.0 `TelegramObject.remove_unset` plus the early `type` check
    if not isinstance(values, dict):
        return values
    if "type" in values:
        try:
            allowed = _TYPE_LITERALS[cls]
        except KeyError:
            allowed = _TYPE_LITERALS[cls] = _get_type_literal(cls)
        if allowed is not None:
            value = values["type"]
            if isinstance(value, Enum):
                value = value.value
            if value not in allowed:
                expected = " or ".join(repr(item) for item in allowed)
                raise PydanticCustomError(_LITERAL_ERROR, _LITERAL_MESSAGE, {"expected": expected})
    return {k: v for k, v in values.items() if not isinstance(v, base.UNSET_TYPE)}


def _trampoline(cls: type, values: Any) -> Any:
    # Executed with aiogram.types.base globals after the `__code__` swap
    return __trigger_remove_unset__(cls, values)  # type: ignore[name-defined] # noqa: F821


def patch_aiogram() -> None:
    installed = version("aiogram")
    if installed != EXPECTED_AIOGRAM_VERSION:
        _fail(
            f"aiogram {EXPECTED_AIOGRAM_VERSION} is required, but {installed} is installed.",
        )

    func = base.TelegramObject.remove_unset.__func__
    if getattr(func, _PATCHED_MARKER, False):
        return

    code = func.__code__
    if code.co_argcount != _trampoline.__code__.co_argcount or code.co_freevars:
        _fail("aiogram.types.base.TelegramObject.remove_unset has an unexpected signature.")

    setattr(base, _GLOBAL_NAME, _remove_unset)
    func.__code__ = _trampoline.__code__
    setattr(func, _PATCHED_MARKER, True)
