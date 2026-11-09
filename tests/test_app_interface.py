"""The language and light/dark buttons of the Streamlit app."""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import securebank.intents.parser_embed as parser_embed  # noqa: E402
from securebank import i18n  # noqa: E402
from tests.fakes import BagOfWordsEncoder  # noqa: E402

from pathlib import Path  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


@pytest.fixture()
def app(bank_db, tmp_path, monkeypatch):
    monkeypatch.setenv("SECUREBANK_BANK_DB", str(bank_db))
    monkeypatch.setenv("SECUREBANK_AUDIT_DB", str(tmp_path / "audit.db"))
    monkeypatch.setattr(parser_embed, "SentenceEncoder", BagOfWordsEncoder)
    import streamlit as st
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def click(at, key):
    at.button(key=key).click()
    at.run()
    return at


def styles(at):
    return " ".join(m.value for m in at.markdown)


def login(at):
    at.text_input[0].input("manager1")
    at.text_input[1].input("Manager!2026")
    at.button[0].click()
    at.run()
    return at


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_login_screen_follows_the_language_button(app, lang):
    click(app, f"lang_{lang}")
    text = i18n.UI[lang]
    assert not app.exception
    assert app.text_input[0].label == text["username"] and app.text_input[1].label == text["password"]
    assert text["sign_in"] in styles(app)


def test_arabic_is_right_to_left_and_others_are_not(app):
    assert "direction: ltr" in styles(app)
    click(app, "lang_ar")
    assert "direction: rtl" in styles(app)
    click(app, "lang_fr")
    assert "direction: ltr" in styles(app)


def test_active_language_button_is_highlighted(app):
    click(app, "lang_fr")
    assert app.button(key="lang_fr").proto.type == "primary"
    assert app.button(key="lang_en").proto.type == "secondary"


def test_theme_button_switches_both_ways(app):
    assert app.button(key="theme_toggle").label == "🌙" and "#eef1f7" in styles(app)
    click(app, "theme_toggle")
    assert app.button(key="theme_toggle").label == "☀️" and "#0b0e12" in styles(app)
    click(app, "theme_toggle")
    assert app.button(key="theme_toggle").label == "🌙"


def test_chat_screen_is_translated(app):
    login(app)
    click(app, "lang_ar")
    text = i18n.UI["ar"]
    assert not app.exception
    assert app.chat_input[0].placeholder == text["ask"]
    assert any(b.label == text["logout"] for b in app.sidebar.button)
    assert any(text["manager"] in m.value for m in app.sidebar.markdown)


def test_language_and_theme_survive_logout(app):
    login(app)
    click(app, "lang_fr")
    click(app, "theme_toggle")
    next(b for b in app.sidebar.button if b.label == i18n.UI["fr"]["logout"]).click()
    app.run()
    assert app.text_input[0].label == i18n.UI["fr"]["username"]
    assert "#0b0e12" in styles(app)


def ask(at, question):
    at.chat_input[0].set_value(question)
    at.run()
    return at


def test_empty_chat_shows_heading_and_suggestion_chips(app):
    login(app)
    assert i18n.UI["en"]["begin"] in styles(app)
    assert [b for b in app.button if b.key and b.key.startswith("chip_")]
    assert i18n.UI["en"]["no_conversations"] in " ".join(c.value for c in app.sidebar.caption)


def test_chip_asks_the_question(app):
    login(app)
    next(b for b in app.button if b.key and b.key.startswith("chip_")).click()
    app.run()
    assert not app.exception
    assert len([m for m in app.chat_message if m.name == "assistant"]) == 1
    assert i18n.UI["en"]["begin"] not in styles(app)


def test_new_chat_keeps_the_old_one_in_recents(app):
    login(app)
    ask(app, "How many customers does the bank have?")
    assert any(b.key and b.key.startswith("open_") for b in app.sidebar.button)
    click(app, "new_chat")
    assert not app.chat_message and i18n.UI["en"]["begin"] in styles(app)
    opener = next(b for b in app.sidebar.button if b.key and b.key.startswith("open_"))
    assert "customers" in opener.label
    opener.click()
    app.run()
    assert len(app.chat_message) == 2


def test_search_filters_recents(app):
    login(app)
    ask(app, "How many customers does the bank have?")
    app.text_input(key="chat_search").input("zzz")
    app.run()
    assert not any(b.key and b.key.startswith("open_") for b in app.sidebar.button)


def test_role_is_shown_but_cannot_be_changed(app):
    login(app)
    assert i18n.UI["en"]["chatting_as"] in styles(app) and "Manager" in styles(app)
    assert not app.selectbox


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_every_interface_label_is_translated(lang):
    assert set(i18n.UI[lang]) == set(i18n.UI["en"])
    assert all(i18n.UI[lang][k] != i18n.UI["en"][k] or k == "language" for k in i18n.UI["en"] if k != "language")
