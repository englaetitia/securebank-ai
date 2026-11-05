"""Send a structured request through the full pipeline as a logged-in user.

Examples (from the project root):
    python scripts/try_pipeline.py manager1 Manager!2026 total_deposits "period=this month"
    python scripts/try_pipeline.py employee1 Employee!2026 avg_loan_amount
    python scripts/try_pipeline.py customer1 Customer!2026 my_balance
    python scripts/try_pipeline.py employee1 Employee!2026 help
    python scripts/try_pipeline.py --audit        (show the last audit log entries)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from securebank.auth.auth import authenticate  # noqa: E402
from securebank.db.connection import get_readonly_connection  # noqa: E402
from securebank.pipeline import handle_request  # noqa: E402
from securebank.security.audit import AuditLog  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("username", nargs="?")
parser.add_argument("password", nargs="?")
parser.add_argument("intent", nargs="?")
parser.add_argument("params", nargs="*", help="name=value pairs")
parser.add_argument("--audit", action="store_true")
args = parser.parse_args()

audit = AuditLog()
if args.audit:
    for row in audit.recent(10):
        print(f"{row['timestamp']}  {row['username'] or '-':<10} {row['role'] or '-':<9} "
              f"{row['intent'] or '-':<22} {row['decision']:<11} {row['reason_code']:<20} "
              f"rows={row['row_count']}  {row['latency_ms']} ms")
    sys.exit(0)

conn = get_readonly_connection()
session = authenticate(conn, args.username, args.password)
if session is None:
    print("Login failed: wrong username or password.")
    sys.exit(1)
print(f"Logged in as {session.username} (role: {session.role})\n")

params = dict(p.split("=", 1) for p in args.params)
response = handle_request(session, args.intent, params, conn, audit)
print(f"[{response.status}] {response.message}")
