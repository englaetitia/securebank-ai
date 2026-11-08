"""Days 8-9: the Streamlit app, driven with Streamlit's own test runner.

The embedding model is replaced by the bag-of-words fake, so no download is
needed. Each test starts a fresh app (fresh browser session).
"""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import securebank.intents.parser_embed as parser_embed  # noqa: E402
from tests.fakes import BagOfWordsEncoder  # noqa: E402

from pathlib import Path  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


@pytest.fixture()
def app(bank_db, tmp_path, monkeypatch):
    monkeypatch.setenv("SECUREBANK_BANK_DB", str(bank_db))
    monkeypatch.setenv("SECUREBANK_AUDIT_DB", str(tmp_path / "audit.db"))
    monkeypatch.setattr(parser_embed, "SentenceEncoder", BagOfWordsEncoder)
    import streamlit as st
    st.cache_resource.clear()          # new databases for every test
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def login(at, username, password):
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    at.button[0].click()
    at.run()
    return at


def ask(at, question):
    at.chat_input[0].set_value(question)
    at.run()
    return at


def assistant_texts(at):
    return [m.markdown[0].value if m.markdown else "" for m in at.chat_message if m.name == "assistant"] \
        + [e.value for e in at.error] + [w.value for w in at.warning]


def test_login_page_shows_first(app):
    assert not app.exception
    assert len(app.text_input) == 2 and not app.chat_input


def test_wrong_password_is_refused(app):
    login(app, "manager1", "wrong")
    assert any("Wrong username or password" in e.value for e in app.error)
    assert not app.chat_input


def test_lockout_after_failed_logins(app):
    for _ in range(5):
        login(app, "employee2", "nope")
    login(app, "employee2", "Employee2!2026")   # even the right password is refused now
    assert any("Too many failed attempts" in e.value for e in app.error)


def test_manager_can_chat(app):
    login(app, "manager1", "Manager!2026")
    assert not app.exception and app.chat_input
    assert any("Manager" in m.value for m in app.sidebar.markdown)
    ask(app, "How many customers does the bank have?")
    assert not app.exception
    assert any("500" in t for t in assistant_texts(app))


def test_employee_is_denied_manager_question(app):
    login(app, "employee1", "Employee!2026")
    ask(app, "What were the 5 largest transactions this month?")
    assert any("Access denied" in e.value for e in app.error)


def test_restricted_question_is_refused(app):
    login(app, "manager1", "Manager!2026")
    ask(app, "Give me the phone number of Osgood Marrowbeck")
    texts = " ".join(assistant_texts(app))
    assert "Osgood" not in texts.replace("Give me the phone number of Osgood Marrowbeck", "")
    assert app.error   # shown as a refusal


def test_customer_sees_only_own_balance(app):
    login(app, "customer1", "Customer!2026")
    ask(app, "How much money do I have?")
    assert not app.exception
    assert any("****" in t or "balance" in t.lower() for t in assistant_texts(app))


def test_details_panel_and_audit_log(app):
    login(app, "manager1", "Manager!2026")
    app.toggle(key="show_details").set_value(True)
    app.run()
    ask(app, "How many customers does the bank have?")
    labels = [e.label for e in app.expander]
    assert "Query details" in labels
    assert any("Audit log" in label for label in labels)


def test_logout(app):
    login(app, "manager1", "Manager!2026")
    next(b for b in app.sidebar.button if b.label == "Log out").click()
    app.run()
    assert not app.chat_input and len(app.text_input) == 2
