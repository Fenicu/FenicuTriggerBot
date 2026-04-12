"""Integration tests for chat_variable_service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_variable_service import del_var, get_vars, set_var, validate_key
from tests.factories import create_chat


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


# ── set_var ──────────────────────────────────────────────────────────────────


async def test_set_var_creates_new(db_session, chat):
    await set_var(db_session, chat.id, "greeting", "Hello!")

    variables = await get_vars(db_session, chat.id)
    assert variables == {"greeting": "Hello!"}


async def test_set_var_upserts_existing(db_session, chat):
    await set_var(db_session, chat.id, "greeting", "Hello!")
    await set_var(db_session, chat.id, "greeting", "Hi there!")

    variables = await get_vars(db_session, chat.id)
    assert variables == {"greeting": "Hi there!"}


async def test_set_var_multiple_keys(db_session, chat):
    await set_var(db_session, chat.id, "key_a", "value_a")
    await set_var(db_session, chat.id, "key_b", "value_b")

    variables = await get_vars(db_session, chat.id)
    assert variables == {"key_a": "value_a", "key_b": "value_b"}


async def test_set_var_different_chats_isolated(db_session):
    chat_a = await create_chat(db_session, title="A")
    chat_b = await create_chat(db_session, title="B")

    await set_var(db_session, chat_a.id, "key", "val_a")
    await set_var(db_session, chat_b.id, "key", "val_b")

    vars_a = await get_vars(db_session, chat_a.id)
    vars_b = await get_vars(db_session, chat_b.id)
    assert vars_a == {"key": "val_a"}
    assert vars_b == {"key": "val_b"}


async def test_set_var_empty_string_value(db_session, chat):
    await set_var(db_session, chat.id, "empty", "")

    variables = await get_vars(db_session, chat.id)
    assert variables["empty"] == ""


# ── get_vars ─────────────────────────────────────────────────────────────────


async def test_get_vars_empty(db_session, chat):
    variables = await get_vars(db_session, chat.id)
    assert variables == {}


async def test_get_vars_returns_all(db_session, chat):
    await set_var(db_session, chat.id, "a", "1")
    await set_var(db_session, chat.id, "b", "2")
    await set_var(db_session, chat.id, "c", "3")

    variables = await get_vars(db_session, chat.id)
    assert len(variables) == 3
    assert variables["a"] == "1"
    assert variables["b"] == "2"
    assert variables["c"] == "3"


# ── del_var ──────────────────────────────────────────────────────────────────


async def test_del_var_existing(db_session, chat):
    await set_var(db_session, chat.id, "key", "value")
    deleted = await del_var(db_session, chat.id, "key")

    assert deleted is True
    variables = await get_vars(db_session, chat.id)
    assert "key" not in variables


async def test_del_var_nonexistent(db_session, chat):
    deleted = await del_var(db_session, chat.id, "no_such_key")
    assert deleted is False


async def test_del_var_only_deletes_specified_key(db_session, chat):
    await set_var(db_session, chat.id, "keep", "value_keep")
    await set_var(db_session, chat.id, "remove", "value_remove")

    await del_var(db_session, chat.id, "remove")

    variables = await get_vars(db_session, chat.id)
    assert variables == {"keep": "value_keep"}


async def test_del_var_isolated_between_chats(db_session):
    chat_a = await create_chat(db_session, title="A")
    chat_b = await create_chat(db_session, title="B")

    await set_var(db_session, chat_a.id, "shared", "a_val")
    await set_var(db_session, chat_b.id, "shared", "b_val")

    await del_var(db_session, chat_a.id, "shared")

    vars_a = await get_vars(db_session, chat_a.id)
    vars_b = await get_vars(db_session, chat_b.id)
    assert "shared" not in vars_a
    assert vars_b["shared"] == "b_val"


# ── validate_key ─────────────────────────────────────────────────────────────


def test_validate_key_valid_lowercase():
    assert validate_key("greeting") is True


def test_validate_key_valid_uppercase():
    assert validate_key("GREETING") is True


def test_validate_key_valid_with_underscore():
    assert validate_key("my_var") is True


def test_validate_key_valid_single_char():
    assert validate_key("x") is True


def test_validate_key_invalid_digits():
    assert validate_key("var1") is False


def test_validate_key_invalid_spaces():
    assert validate_key("my var") is False


def test_validate_key_invalid_dash():
    assert validate_key("my-var") is False


def test_validate_key_empty():
    assert validate_key("") is False


def test_validate_key_invalid_special_chars():
    assert validate_key("var$") is False


def test_validate_key_invalid_cyrillic():
    assert validate_key("переменная") is False
