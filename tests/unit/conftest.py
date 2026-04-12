"""Unit-test conftest — override DB-dependent fixtures from root conftest."""

import pytest


@pytest.fixture(scope="session")
def engine():
    """Stub out the DB engine — unit tests don't need a database."""
    return None


@pytest.fixture
def db_session():
    """Stub out the DB session."""
    return None


@pytest.fixture(autouse=True)
def _clean_tables():
    """No-op — nothing to clean in unit tests."""
    yield
