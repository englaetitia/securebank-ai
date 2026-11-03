import pytest

from securebank.db.seed import build


@pytest.fixture(scope="session")
def bank_db(tmp_path_factory):
    """Build a fresh test database once per test run."""
    return build(tmp_path_factory.mktemp("data") / "bank.db")
