"""Run one approved intent by hand, without the LLM.

Examples (from the project root):
    python scripts/try_query.py count_new_accounts period=October account_type=savings
    python scripts/try_query.py total_deposits "period=this month"
    python scripts/try_query.py my_balance --customer 1
    python scripts/try_query.py --list
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from securebank.db.connection import get_readonly_connection  # noqa: E402
from securebank.intents.catalog import (INTENTS, InvalidParams,  # noqa: E402
                                        UnknownIntent, run_intent)

parser = argparse.ArgumentParser()
parser.add_argument("intent", nargs="?")
parser.add_argument("params", nargs="*", help="name=value pairs")
parser.add_argument("--customer", type=int, help="customer_id (for my_* intents)")
parser.add_argument("--list", action="store_true", help="list all intents")
args = parser.parse_args()

if args.list or not args.intent:
    for intent in INTENTS.values():
        print(f"{intent.name:<24} roles={','.join(intent.allowed_roles) or '-':<25} "
              f"params={','.join(intent.params) or '-'}")
    sys.exit(0)

params = dict(p.split("=", 1) for p in args.params)
try:
    result = run_intent(get_readonly_connection(), args.intent, params, customer_id=args.customer)
except (InvalidParams, UnknownIntent) as exc:
    print(f"REJECTED: {exc}")
    sys.exit(1)
print(json.dumps(result.to_dict(), indent=2))
