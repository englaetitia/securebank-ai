"""SecureBank AI chat app (days 8-9).

    streamlit run app/streamlit_app.py

Works without the Qwen model: the "Fast" engine uses the embedding parser
and template answers. When Qwen is downloaded, the "AI model" engine is
offered too (LLM parser + LLM-written answers, embedding fallback).

The app is only a front end. Every security decision (login, roles, approved
queries, masking, output checks, audit) happens in the securebank package.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from securebank.config import AUDIT_DB_PATH, BANK_DB_PATH  # noqa: E402
from securebank.auth.auth import AccountLocked, LoginLimiter, authenticate  # noqa: E402
from securebank.db.connection import get_readonly_connection  # noqa: E402
from securebank.pipeline import ask  # noqa: E402
from securebank.security.audit import AuditLog  # noqa: E402
from securebank.security.output_guard import KnownPII  # noqa: E402
from securebank.security.rbac import allowed_intents  # noqa: E402

st.set_page_config(page_title="SecureBank AI", page_icon="🏦", layout="wide")

# The tests point these at a temporary database
BANK_DB = Path(os.environ.get("SECUREBANK_BANK_DB", BANK_DB_PATH))
AUDIT_DB = Path(os.environ.get("SECUREBANK_AUDIT_DB", AUDIT_DB_PATH))

ROLE_BADGES = {"manager": ("🟣", "Manager"), "employee": ("🔵", "Employee"), "customer": ("🟢", "Customer")}
STATUS_ICONS = {"ok": "✅", "help": "💡", "denied": "⛔", "invalid": "⚠️", "unsupported": "❔",
                "blocked": "🛡️", "error": "❌"}
ENGINE_FAST = "Fast (embedding parser + template answers, no model needed)"
ENGINE_AI = "AI model (Qwen parser + AI-written answers)"


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


@st.cache_resource(show_spinner="Loading the embedding model...")
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


# ---- login -------------------------------------------------------------------

def login_screen():
    st.title("🏦 SecureBank AI")
    st.caption("A secure banking assistant. Answers come only from approved, read-only queries.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        try:
            session = authenticate(bank_connection(), username, password, limiter=login_limiter())
        except AccountLocked as exc:
            audit_log().record(session=None, intent=None, params=None, decision="denied",
                               reason_code="account_locked")
            st.error(str(exc))
            return
        if session is None:
            audit_log().record(session=None, intent=None, params=None, decision="denied",
                               reason_code="login_failed")
            st.error("Wrong username or password.")
            return
        st.session_state.session = session
        st.session_state.messages = []
        st.rerun()
    with st.expander("Demo accounts"):
        st.markdown("- `manager1` / `Manager!2026`\n- `employee1` / `Employee!2026`\n"
                    "- `customer1` / `Customer!2026`")


# ---- chat --------------------------------------------------------------------

def sidebar(session):
    icon, label = ROLE_BADGES[session.role]
    st.sidebar.markdown(f"### {icon} {session.username}")
    st.sidebar.markdown(f"Role: **{label}**")
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()
    engines = [ENGINE_FAST] + ([ENGINE_AI] if qwen_downloaded() else [])
    engine = st.sidebar.radio("Engine", engines, key="engine")
    if len(engines) == 1:
        st.sidebar.caption("The Qwen model is not downloaded yet, so only the fast engine is available.")
    show_details = st.sidebar.toggle("Show query details (demo)", key="show_details")

    st.sidebar.divider()
    st.sidebar.markdown("**Try asking**")
    for intent in allowed_intents(session.role):
        if intent.examples and intent.name != "help":
            if st.sidebar.button(intent.examples[0], key=f"ex_{intent.name}"):
                st.session_state.pending = intent.examples[0]
    if session.role == "customer":
        st.sidebar.caption("Customers can only see their own accounts.")
    return engine, show_details


def render_details(msg):
    details = msg.get("details") or {}
    with st.expander("Query details"):
        st.markdown(f"- **Status:** `{msg['status']}`\n"
                    f"- **Parser:** {details.get('parser', '-')} "
                    f"({details.get('parse_ms', '-')} ms, attempts: {details.get('attempts', '-')})\n"
                    f"- **Intent:** `{msg.get('intent') or details.get('intent') or '-'}`\n"
                    f"- **Parameters:** `{msg.get('params') or details.get('params') or {}}`\n"
                    f"- **Answer written by:** {msg.get('answer_source') or '-'}")
        if details.get("guard"):
            st.markdown(f"- **Output guard problems:** {details['guard']}")
        if details.get("raw_output"):
            st.code(details["raw_output"], language=None)
        if msg.get("rows"):
            st.dataframe(msg["rows"], use_container_width=True)


def render_message(msg, show_details):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            text = f"{STATUS_ICONS.get(msg['status'], '')} {msg['content']}"
            if msg["status"] == "denied":
                st.error(text)
            elif msg["status"] == "blocked":
                st.warning(text)
            else:
                st.markdown(text)
            if show_details:
                render_details(msg)
        else:
            st.markdown(msg["content"])


def answer(session, question, engine):
    if engine == ENGINE_AI:
        parser, writer, _ = ai_engine()
    else:
        parser, writer = embedding_parser(), None
    r = ask(session, question, parser, bank_connection(), audit_log(),
            known_pii=known_pii(), write_answer=writer)
    return {"role": "assistant", "content": r.message, "status": r.status, "intent": r.intent,
            "params": r.result.params if r.result else None, "details": r.details,
            "answer_source": r.answer_source, "rows": r.result.rows if r.result else None}


def audit_panel():
    with st.expander("📋 Audit log (manager only, latest 20)"):
        rows = audit_log().recent(20)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.caption("No entries yet.")


def chat_screen(session):
    engine, show_details = sidebar(session)
    st.title("🏦 SecureBank AI")
    if session.role == "manager":
        audit_panel()

    for msg in st.session_state.messages:
        render_message(msg, show_details)

    question = st.chat_input("Ask a question about the bank (type \"help\" for ideas)")
    question = question or st.session_state.pop("pending", None)
    if question:
        user_msg = {"role": "user", "content": question}
        st.session_state.messages.append(user_msg)
        render_message(user_msg, show_details)
        with st.spinner("Thinking..."):
            reply = answer(session, question, engine)
        st.session_state.messages.append(reply)
        render_message(reply, show_details)


# Streamlit runs this file from top to bottom on every click
if "session" not in st.session_state:
    login_screen()
else:
    chat_screen(st.session_state.session)
