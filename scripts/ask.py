"""Ask questions in plain English through the full pipeline, with the real LLM.

    python scripts/ask.py manager1 'Manager!2026'
    python scripts/ask.py employee1 'Employee!2026' --question "How many customers do we have?"

Type a question at the prompt; an empty line or "quit" exits.
Add --parser embedding (day 6) to use the embedding classifier instead.
Day 7: --answers llm (default with the llm/hybrid parser) lets the LLM phrase
the answer; --answers template uses the plain template (no model needed).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from securebank.auth.auth import authenticate  # noqa: E402
from securebank.db.connection import get_readonly_connection  # noqa: E402
from securebank.pipeline import ask  # noqa: E402
from securebank.security.audit import AuditLog  # noqa: E402
from securebank.security.output_guard import KnownPII  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("username")
parser.add_argument("password")
parser.add_argument("--question", help="ask one question and exit")
parser.add_argument("--parser", default="llm", choices=["llm", "embedding", "hybrid"])
parser.add_argument("--answers", choices=["llm", "template"],
                    help="who writes the answer (default: llm, or template with --parser embedding)")
args = parser.parse_args()
args.answers = args.answers or ("template" if args.parser == "embedding" else "llm")

conn = get_readonly_connection()
session = authenticate(conn, args.username, args.password)
if session is None:
    sys.exit("Login failed: wrong username or password.")


def build_parser(kind):
    if kind == "llm":
        from securebank.intents.parser_llm import LLMParser
        from securebank.llm.model import get_llm
        llm = get_llm()
        print(f"Model: {llm.description}")
        return LLMParser(llm)
    from securebank.intents.parser import build_parser as build  # day 6
    return build(kind)


print("Loading...")
t0 = time.time()
question_parser = build_parser(args.parser)
writer = None
if args.answers == "llm":
    from securebank.llm.answer import make_answer_writer  # day 7
    writer = make_answer_writer()
print(f"Ready in {time.time() - t0:.1f} s. Logged in as {session.username} ({session.role}).\n")
audit, pii = AuditLog(), KnownPII(conn)


def answer(question):
    t = time.time()
    r = ask(session, question, question_parser, conn, audit, known_pii=pii, write_answer=writer)
    print(f"\n[{r.status}] {r.message}")
    if r.answer_source:
        print(f"   answer written by: {r.answer_source}")
    if r.details:
        d = r.details
        print(f"   parsed by {d['parser']} in {d['parse_ms']} ms (attempts: {d['attempts']}): "
              f"intent={d.get('intent')} params={d.get('params')}")
        if d.get("guard"):
            print(f"   output guard problems: {d['guard']}")
        if d.get("error"):
            print(f"   parser error: {d['error']}  raw: {d['raw_output']!r}")
    print(f"   total {time.time() - t:.1f} s\n")


if args.question:
    answer(args.question)
else:
    while True:
        q = input("Question> ").strip()
        if q.lower() in ("", "quit", "exit"):
            break
        answer(q)
