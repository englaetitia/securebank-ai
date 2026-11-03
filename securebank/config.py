"""Central settings for SecureBank AI."""
from datetime import date
from pathlib import Path

# Project root = the folder that contains the "securebank" package
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

BANK_DB_PATH = DATA_DIR / "bank.db"    # synthetic banking data (opened read-only by the app)
AUDIT_DB_PATH = DATA_DIR / "audit.db"  # audit log (the only database the app writes to)

# Fixed "today" so that "this month" / "today" give the same answers in every test run
DEMO_TODAY = date(2026, 11, 3)

# Seed for the synthetic data generator: same seed = same database every time
RANDOM_SEED = 42

# LLM settings (used from day 5)
MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
