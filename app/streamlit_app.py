"""SecureBank AI chat app (days 8-9, multilingual update).

    streamlit run app/streamlit_app.py

Works without the Qwen model: the "Fast" engine uses the embedding parser
and template answers. When Qwen is downloaded, the "AI model" engine is
offered too (LLM parser + LLM-written answers, embedding fallback).

The look is a chatbot template: a login card, a navy sidebar with New chat,
Search and Recents, suggestion chips on an empty chat, and a language switcher
(English, French, Arabic with right-to-left layout) and light/dark button at
the top right of every screen.

The app is only a front end. Every security decision (login, roles, approved
queries, masking, output checks, audit) happens in the securebank package.
The role is shown but cannot be changed here: it comes from the login session.
Past conversations live in this browser session only and are forgotten at log-out.
"""
import html
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from securebank import i18n  # noqa: E402
from securebank.config import AUDIT_DB_PATH, BANK_DB_PATH  # noqa: E402
from securebank.auth.auth import AccountLocked, LoginLimiter, authenticate  # noqa: E402
from securebank.conversation import ConversationContext  # noqa: E402
from securebank.db.connection import get_readonly_connection  # noqa: E402
from securebank.intents.examples import example_in  # noqa: E402
from securebank.pipeline import ask  # noqa: E402
from securebank.security.audit import AuditLog  # noqa: E402
from securebank.security.output_guard import KnownPII  # noqa: E402
from securebank.security.rbac import allowed_intents  # noqa: E402

st.set_page_config(page_title="SecureBank AI", page_icon="🏦", layout="wide")

# The tests point these at a temporary database
BANK_DB = Path(os.environ.get("SECUREBANK_BANK_DB", BANK_DB_PATH))
AUDIT_DB = Path(os.environ.get("SECUREBANK_AUDIT_DB", AUDIT_DB_PATH))

STATUS_ICONS = {"ok": "✅", "help": "💡", "denied": "⛔", "invalid": "⚠️", "unsupported": "❔",
                "blocked": "🛡️", "error": "❌", "clarify": "🤔"}
ENGINE_FAST, ENGINE_AI = "fast", "ai"
LANGUAGE_BUTTONS = {"en": "EN", "fr": "FR", "ar": "ع"}
MAX_CHIPS = 4
TITLE_LENGTH = 42
THEMES = {
    "light": {"bg": "#ffffff", "page": "#eef1f7", "card": "#ffffff", "field": "#f6f7fa", "text": "#1b1e23",
              "muted": "#5d6470", "border": "#d8dce4", "bubble": "#f4f5f8", "navy": "#1b2259", "navy_soft": "#2a3273", "active": "#1b2259"},
    "dark": {"bg": "#0f1216", "page": "#0b0e12", "card": "#171b22", "field": "#1f242c", "text": "#e9ebee",
             "muted": "#a3aab5", "border": "#30363f", "bubble": "#1a1f27", "navy": "#141a44", "navy_soft": "#232a63", "active": "#4a56b8"},
}
ORANGE = "#f28c28"


def ui_lang() -> str:
    return st.session_state.setdefault("ui_lang", "en")


def labels() -> dict:
    return i18n.UI[ui_lang()]


def apply_look() -> None:
    """Colors for the chosen theme, and right-to-left layout for Arabic."""
    c = THEMES[st.session_state.setdefault("ui_theme", "light")]
    direction = "rtl" if ui_lang() == "ar" else "ltr"
    logged_in = "session" in st.session_state
    page = c["bg"] if logged_in else c["page"]
    st.markdown(f"""<style>
/* Page and text */
.stApp, [data-testid="stHeader"], [data-testid="stBottom"], [data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] {{ background: {page}; }}
.stApp :is(p, li, span, label, h1, h2, h3, small, summary) {{ color: {c['text']}; }}
[data-testid="stCaptionContainer"] p {{ color: {c['muted']}; }}
[data-testid="stAppViewContainer"], [data-testid="stSidebar"] {{ direction: {direction}; }}
/* Fields */
.stApp :is(input, textarea), [data-baseweb="input"], [data-baseweb="base-input"] {{
    background: {c['field']}; color: {c['text']}; caret-color: {c['text']}; }}
[data-baseweb="input"] {{ border-radius: 10px; border-color: {c['border']}; }}
[data-baseweb="input"]:focus-within {{ border-color: {ORANGE}; }}
.stApp textarea::placeholder, .stApp input::placeholder {{ color: {c['muted']}; opacity: 1; }}
/* Buttons */
.stApp button[kind="secondary"], .stApp button[kind="secondaryFormSubmit"] {{
    background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; }}
.stApp button[kind="secondary"] p, .stApp button[kind="secondaryFormSubmit"] p {{ color: {c['text']}; }}
[data-testid="stToolbar"], [data-testid="stDecoration"] {{ visibility: hidden; }}
[data-testid="stSidebar"] .stButton button > div {{ justify-content: flex-start; width: 100%; }}
.st-key-new_chat button {{ border: 1px solid #5a63a8 !important; }}
.st-key-user_footer .stButton button > div {{ justify-content: center; }}
/* Language switcher and theme button, top right on every screen */
.st-key-topbar {{ position: fixed; top: 10px; right: 16px; z-index: 1000000; width: max-content !important;
    flex-wrap: nowrap; }}
.st-key-language_pill {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 999px;
    padding: 3px; width: max-content !important; flex: none; flex-wrap: nowrap; }}
.st-key-topbar [data-testid="stElementContainer"], .st-key-topbar .stButton {{ width: max-content !important; }}
.st-key-language_pill button {{ border: 0 !important; border-radius: 999px !important; min-height: 30px;
    padding: 0 12px; background: transparent !important; }}
.st-key-language_pill button[kind="primary"] {{ background: {c['active']} !important; }}
.st-key-language_pill button[kind="primary"] p {{ color: #ffffff !important; }}
.st-key-theme_toggle button {{ border-radius: 50% !important; width: 38px; height: 38px; min-height: 38px; padding: 0; }}
/* Login card */
.st-key-login_card {{ background: {c['card']}; border-radius: 16px; overflow: hidden; gap: 0;
    box-shadow: 0 10px 30px rgba(20, 30, 70, .14); margin-top: 7vh; }}
.login-header {{ background: {c['navy']}; padding: 28px 24px; text-align: center; }}
.login-header .logo {{ font-size: 34px; }}
.stApp .login-header h2, .stApp .login-header h2 * {{ color: #ffffff; }}
.stApp .login-header h2 {{ margin: 4px 0 2px; padding: 0; font-size: 24px; font-weight: 700; }}
.stApp .login-header p {{ color: #c9cfea; margin: 0; }}
.st-key-login_card [data-testid="stForm"] {{ border: 0; padding: 20px 24px 8px; }}
.st-key-login_card [data-testid="stExpander"] {{ margin: 0 24px 20px; width: auto; }}
.st-key-login_card [data-testid="stExpander"] details {{ border-color: {c['border']}; }}
.st-key-login_card button[kind="secondaryFormSubmit"] {{ width: 100%; background: {c['navy']}; border: 0; }}
.st-key-login_card button[kind="secondaryFormSubmit"] p {{ color: #ffffff; font-weight: 600; }}
/* Sidebar: navy in both themes */
[data-testid="stSidebar"], [data-testid="stSidebarContent"] {{ background: {c['navy']}; }}
[data-testid="stSidebar"] :is(p, li, span, label, h1, h2, h3, summary) {{ color: #eef0fa; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color: #b8bfdf; }}
[data-testid="stSidebar"] button[kind="secondary"] {{ background: transparent; border: 0; justify-content: flex-start; }}
[data-testid="stSidebar"] button[kind="secondary"]:hover {{ background: {c['navy_soft']}; }}
[data-testid="stSidebar"] button[kind="secondary"] p {{ color: #eef0fa; }}
[data-testid="stSidebar"] button[kind="primary"] {{ background: {c['navy_soft']}; border: 0;
    border-inline-start: 3px solid {ORANGE}; border-radius: 10px; justify-content: flex-start; }}
[data-testid="stSidebar"] button[kind="primary"] p {{ color: #ffffff; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ border-color: {c['navy_soft']}; }}
[data-testid="stSidebar"] [data-baseweb="input"], [data-testid="stSidebar"] [data-baseweb="base-input"],
[data-testid="stSidebar"] input {{ background: {c['navy_soft']}; border-color: {c['navy_soft']}; color: #ffffff; }}
[data-testid="stSidebar"] input::placeholder {{ color: #b8bfdf; }}
.brand {{ font-size: 20px; font-weight: 700; color: #ffffff; padding: 2px 0 8px; }}
.user-card {{ display: flex; align-items: center; gap: 10px; }}
.user-card .avatar {{ width: 36px; height: 36px; border-radius: 50%; background: {ORANGE}; color: #1b2259;
    display: flex; align-items: center; justify-content: center; font-weight: 700; flex: none; }}
.user-card .name {{ color: #ffffff; font-weight: 600; line-height: 1.2; }}
.user-card .role {{ color: #b8bfdf; font-size: 13px; line-height: 1.2; }}
.st-key-user_footer {{ position: sticky; bottom: 0; background: {c['navy']}; padding: 10px 0 6px;
    border-top: 1px solid {c['navy_soft']}; }}
/* Chat area */
.role-badge {{ display: inline-block; background: {c['bubble']}; border: 1px solid {c['border']}; border-radius: 999px;
    padding: 5px 14px; font-size: 14px; color: {c['muted']}; }}
.role-badge b {{ color: {c['text']}; }}
.begin {{ text-align: center; font-size: 36px; font-weight: 600; color: {c['text']}; margin: 16vh 0 24px; }}
.st-key-chips button {{ border-radius: 999px !important; min-height: 44px; }}
[data-testid="stChatMessage"] {{ background: {c['bubble']}; border-radius: 14px; }}
[data-testid="stChatInput"], [data-testid="stChatInput"] > div {{ background: {c['field']}; border-color: {c['border']};
    border-radius: 24px; }}
[data-testid="stChatInput"]:focus-within {{ border-color: {ORANGE}; }}
[data-testid="stChatInputSubmitButton"] {{ border-radius: 50%; background: {c['active']}; }}
[data-testid="stChatInputSubmitButton"] svg {{ fill: #ffffff; color: #ffffff; }}
[data-testid="stBottomBlockContainer"] {{ padding-bottom: 38px; }}
.disclaimer {{ position: fixed; bottom: 10px; left: {'calc(50% - 150px)' if direction == 'rtl' else 'calc(50% + 150px)'};
    transform: translateX(-50%); width: max-content; max-width: 60%; text-align: center; font-size: 12px; color: {c['muted']}; z-index: 1000; pointer-events: none; }}
/* Each paragraph follows its own text, so a mixed conversation stays readable */
[data-testid="stChatMessage"] :is(p, li), [data-testid="stAlert"] p, [data-testid="stChatInput"] textarea,
[data-testid="stSidebar"] button p, .st-key-chips button p {{ unicode-bidi: plaintext; text-align: start; }}
</style>""", unsafe_allow_html=True)


def set_language(code: str) -> None:
    st.session_state.ui_lang = code


def toggle_theme() -> None:
    st.session_state.ui_theme = "dark" if st.session_state.ui_theme == "light" else "light"


def look_controls() -> None:
    """The language switcher and the light/dark button. CSS pins them to the top right."""
    is_light = st.session_state.ui_theme == "light"
    with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="small"):
        with st.container(key="language_pill", horizontal=True, gap=None):
            for code, name in LANGUAGE_BUTTONS.items():
                st.button(name, key=f"lang_{code}", on_click=set_language, args=(code,),
                          type="primary" if ui_lang() == code else "secondary")
        st.button("🌙" if is_light else "☀️", key="theme_toggle", on_click=toggle_theme)


# ---- shared resources (loaded once per server) ---------------------------------

@st.cache_resource
def bank_connection():
    return get_readonly_connection(BANK_DB, check_same_thread=False)


@st.cache_resource
def audit_log():
    return AuditLog(AUDIT_DB, check_same_thread=False)


@st.cache_resource
def known_pii():
    return KnownPII(bank_connection())


@st.cache_resource
def login_limiter():
    return LoginLimiter()   # shared, so locking works across browser tabs


@st.cache_resource(show_spinner="Loading the embedding model (the first time takes a minute or two)...")
def embedding_parser():
    from securebank.intents.parser_embed import EmbeddingParser
    return EmbeddingParser()


@st.cache_resource(show_spinner="Loading Qwen (first time takes a minute)...")
def ai_engine():
    from securebank.intents.parser import HybridParser
    from securebank.intents.parser_llm import LLMParser
    from securebank.llm.answer import make_answer_writer
    from securebank.llm.model import get_llm
    llm = get_llm()
    return HybridParser(LLMParser(llm), embedding_parser()), make_answer_writer(llm), llm.description


def qwen_downloaded() -> bool:
    from securebank.llm.model import model_available
    return model_available()


# ---- conversations (kept in this browser session only) ----------------------------

def new_conversation() -> dict:
    st.session_state.chat_counter = st.session_state.get("chat_counter", 0) + 1
    return {"id": st.session_state.chat_counter, "title": None, "messages": [], "context": ConversationContext()}


def start_chat() -> None:
    if current_chat()["messages"]:            # an empty chat is simply reused
        chat = new_conversation()
        st.session_state.chats.insert(0, chat)
        st.session_state.current_chat = chat["id"]


def open_chat(chat_id: int) -> None:
    st.session_state.current_chat = chat_id


def current_chat() -> dict:
    return next(c for c in st.session_state.chats if c["id"] == st.session_state.current_chat)


# ---- login -------------------------------------------------------------------

def login_screen():
    text = labels()
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle, st.container(key="login_card"):
        st.markdown(f'<div class="login-header"><div class="logo">🏦</div><h2>SecureBank AI</h2>'
                    f'<p>{html.escape(text["sign_in"])}</p></div>', unsafe_allow_html=True)
        with st.form("login", border=False):
            username = st.text_input(text["username"])
            password = st.text_input(text["password"], type="password")
            submitted = st.form_submit_button(text["login"], use_container_width=True)
        if submitted:
            try:
                session = authenticate(bank_connection(), username, password, limiter=login_limiter())
            except AccountLocked:
                audit_log().record(session=None, intent=None, params=None, decision="denied",
                                   reason_code="account_locked")
                st.error(text["locked"])
                return
            if session is None:
                audit_log().record(session=None, intent=None, params=None, decision="denied",
                                   reason_code="login_failed")
                st.error(text["wrong_login"])
                return
            st.session_state.session = session
            first = new_conversation()
            st.session_state.chats = [first]
            st.session_state.current_chat = first["id"]
            st.rerun()
        with st.expander(text["demo"]):
            st.markdown("- `manager1` / `Manager!2026`\n- `employee1` / `Employee!2026`\n"
                        "- `customer1` / `Customer!2026`")


# ---- chat --------------------------------------------------------------------

def log_out():
    keep = {k: st.session_state[k] for k in ("ui_lang", "ui_theme") if k in st.session_state}
    st.session_state.clear()
    st.session_state.update(keep)


def recents(text):
    st.sidebar.markdown(f"**{text['recents']}**")
    wanted = (st.session_state.get("chat_search") or "").strip().lower()
    chats = [c for c in st.session_state.chats if c["title"] and wanted in c["title"].lower()]
    if not chats:
        st.sidebar.caption(text["no_conversations"])
    for chat in chats:
        active = chat["id"] == st.session_state.current_chat
        st.sidebar.button(chat["title"], key=f"open_{chat['id']}", on_click=open_chat, args=(chat["id"],),
                          type="primary" if active else "secondary", use_container_width=True)


def sidebar(session):
    text = labels()
    st.sidebar.markdown('<div class="brand">🏦 SecureBank AI</div>', unsafe_allow_html=True)
    st.sidebar.button(f"＋  {text['new_chat']}", key="new_chat", on_click=start_chat, use_container_width=True)
    st.sidebar.text_input(text["search"], key="chat_search", placeholder=text["search"], label_visibility="collapsed")
    recents(text)

    with st.sidebar.expander(text["settings"]):
        engines = [ENGINE_FAST] + ([ENGINE_AI] if qwen_downloaded() else [])
        engine = st.radio(text["engine"], engines, key="engine", format_func=lambda e: text[f"engine_{e}"])
        if len(engines) == 1:
            st.caption(text["no_model"])
        show_details = st.toggle(text["details_toggle"], key="show_details")
        if session.role == "customer":
            st.caption(text["own_only"])

    with st.sidebar.container(key="user_footer"):
        st.markdown(f'<div class="user-card"><div class="avatar">{html.escape(session.username[:2].upper())}</div>'
                    f'<div><div class="name">{html.escape(session.username)}</div>'
                    f'<div class="role">{html.escape(text[session.role])}</div></div></div>', unsafe_allow_html=True)
        if st.button(text["logout"], use_container_width=True):
            log_out()
            st.rerun()
    return engine, show_details


def render_details(msg):
    text = labels()
    details = msg.get("details") or {}
    with st.expander(text["details"]):
        st.markdown(f"- **{text['status']}:** `{msg['status']}`\n"
                    f"- **{text['parser']}:** {details.get('parser', '-')} "
                    f"({details.get('parse_ms', '-')} ms, {text['attempts']}: {details.get('attempts', '-')})\n"
                    f"- **{text['intent']}:** `{msg.get('intent') or details.get('intent') or '-'}`\n"
                    f"- **{text['params']}:** `{msg.get('params') or details.get('params') or {}}`\n"
                    f"- **{text['written_by']}:** {msg.get('answer_source') or '-'}\n"
                    f"- **{text['answer_language']}:** {msg.get('lang') or '-'}")
        if details.get("typos_fixed"):
            st.markdown(f"- **{text['typos']}:** {details['typos_fixed']}")
        if details.get("guard"):
            st.markdown(f"- **{text['guard']}:** {details['guard']}")
        if details.get("raw_output"):
            st.code(details["raw_output"], language=None)
        if msg.get("rows"):
            st.dataframe(msg["rows"], use_container_width=True)


def render_suggestions(msg, index):
    """The "Did you mean...?" buttons. A click asks that question for real."""
    for number, suggestion in enumerate(msg.get("suggestions") or []):
        if st.button(suggestion, key=f"suggest_{index}_{number}"):
            st.session_state.pending = suggestion
            st.rerun()


def render_message(msg, show_details, index=0):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            text = f"{STATUS_ICONS.get(msg['status'], '')} {msg['content']}"
            if msg["status"] == "denied":
                st.error(text)
            elif msg["status"] == "blocked":
                st.warning(text)
            else:
                st.markdown(text)
            render_suggestions(msg, index)
            if show_details:
                render_details(msg)
        else:
            st.markdown(msg["content"])


def answer(session, question, engine, chat):
    if engine == ENGINE_AI:
        parser, writer, _ = ai_engine()
    else:
        parser, writer = embedding_parser(), None
    r = ask(session, question, parser, bank_connection(), audit_log(),
            known_pii=known_pii(), write_answer=writer, context=chat["context"])
    return {"role": "assistant", "content": r.message, "status": r.status, "intent": r.intent,
            "params": r.result.params if r.result else None, "details": r.details,
            "answer_source": r.answer_source, "rows": r.result.rows if r.result else None,
            "lang": r.lang, "suggestions": r.suggestions}


def audit_panel():
    text = labels()
    with st.expander(text["audit"]):
        rows = audit_log().recent(20)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.caption(text["no_entries"])


def empty_chat(session, text):
    """The welcome heading and suggestion chips, from what this role may ask."""
    st.markdown(f'<div class="begin">{html.escape(text["begin"])}</div>', unsafe_allow_html=True)
    intents = [i for i in allowed_intents(session.role) if i.examples][:MAX_CHIPS]
    with st.container(key="chips"):
        for row_start in range(0, len(intents), 2):
            columns = st.columns(2)
            for column, intent in zip(columns, intents[row_start:row_start + 2]):
                example = example_in(intent.name, ui_lang())
                if column.button(example, key=f"chip_{intent.name}", use_container_width=True):
                    st.session_state.pending = example
                    st.rerun()


def chat_screen(session):
    engine, show_details = sidebar(session)
    text = labels()
    chat = current_chat()
    st.markdown(f'<span class="role-badge">{html.escape(text["chatting_as"])} '
                f'<b>{html.escape(text[session.role])}</b></span>', unsafe_allow_html=True)
    if session.role == "manager":
        audit_panel()

    question = st.chat_input(text["ask"])
    question = question or st.session_state.pop("pending", None)
    st.markdown(f'<div class="disclaimer">{html.escape(text["disclaimer"])}</div>', unsafe_allow_html=True)

    if not chat["messages"] and not question:
        empty_chat(session, text)
    for index, msg in enumerate(chat["messages"]):
        render_message(msg, show_details, index)

    if question:
        if chat["title"] is None:
            chat["title"] = question if len(question) <= TITLE_LENGTH else question[:TITLE_LENGTH - 1] + "…"
        user_msg = {"role": "user", "content": question}
        chat["messages"].append(user_msg)
        render_message(user_msg, show_details, len(chat["messages"]) - 1)
        with st.spinner(text["thinking"]):
            reply = answer(session, question, engine, chat)
        chat["messages"].append(reply)
        render_message(reply, show_details, len(chat["messages"]) - 1)
        st.rerun()                                  # so the new title appears in Recents


# Streamlit runs this file from top to bottom on every click
ui_lang()
apply_look()
if "session" not in st.session_state:
    login_screen()
else:
    chat_screen(st.session_state.session)
look_controls()     # drawn last so the screen's own controls come first; CSS pins it to the top right
