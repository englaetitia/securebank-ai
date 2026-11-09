"""The approved intents: the ONLY database operations SecureBank AI can run.

Each intent has one fixed, parameterized SQL query. Nothing from the user's
question is ever pasted into SQL text; values are passed as :named parameters.
The LLM (day 5) can only choose an intent name from this list and fill its
parameters; everything is validated here before any query runs.

Roles are recorded here and enforced by the security layer (day 3).
"""
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from securebank.config import DEMO_TODAY
from securebank.intents.dates import DateParseError, DateRange, parse_period

MANAGER, EMPLOYEE, CUSTOMER = "manager", "employee", "customer"
STAFF = (MANAGER, EMPLOYEE)


class InvalidParams(ValueError):
    """Parameters missing, unknown, or outside the allowed values."""


class UnknownIntent(ValueError):
    """The intent name is not in the catalog."""


@dataclass(frozen=True)
class Param:
    kind: str                       # "period", "choice" or "int"
    default: object = None
    choices: tuple = ()
    min: int | None = None
    max: int | None = None


@dataclass(frozen=True)
class Intent:
    name: str
    description: str
    sql: str | None                 # None = answered without the database
    allowed_roles: tuple
    params: dict = field(default_factory=dict)
    self_scoped: bool = False       # True = filtered on the logged-in customer
    examples: tuple = ()            # sample questions (prompt + embedding baseline)


ACCOUNT_TYPE = Param("choice", choices=("savings", "checking"))
TRANSACTION_TYPE = Param("choice", choices=("deposit", "withdrawal"))
LOAN_STATUS = Param("choice", choices=("active", "closed"))

INTENTS = {i.name: i for i in [
    Intent(
        "count_new_accounts", "Number of accounts opened in a period, optionally by type",
        """SELECT COUNT(*) AS new_accounts
           FROM accounts
           WHERE opening_date BETWEEN :start AND :end
             AND (:account_type IS NULL OR account_type = :account_type)""",
        STAFF, {"period": Param("period", default="all time"), "account_type": ACCOUNT_TYPE},
        examples=("How many savings accounts were opened in October?",
                  "How many new accounts were opened this month?"),
    ),
    Intent(
        "total_deposits", "Total value and number of deposits in a period",
        """SELECT COUNT(*) AS deposit_count, ROUND(COALESCE(SUM(amount), 0), 2) AS total_deposits
           FROM transactions
           WHERE transaction_type = 'deposit' AND transaction_date BETWEEN :start AND :end""",
        STAFF, {"period": Param("period", default="all time")},
        examples=("What is the total value of deposits made this week?",
                  "How much money was deposited in October?"),
    ),
    Intent(
        "total_withdrawals", "Total value and number of withdrawals in a period",
        """SELECT COUNT(*) AS withdrawal_count, ROUND(COALESCE(SUM(amount), 0), 2) AS total_withdrawals
           FROM transactions
           WHERE transaction_type = 'withdrawal' AND transaction_date BETWEEN :start AND :end""",
        STAFF, {"period": Param("period", default="all time")},
        examples=("How much was withdrawn today?", "Total withdrawals last month?"),
    ),
    Intent(
        "transaction_count", "Number and total value of transactions in a period",
        """SELECT COUNT(*) AS transaction_count, ROUND(COALESCE(SUM(amount), 0), 2) AS total_amount
           FROM transactions
           WHERE transaction_date BETWEEN :start AND :end
             AND (:transaction_type IS NULL OR transaction_type = :transaction_type)""",
        STAFF, {"period": Param("period", default="all time"), "transaction_type": TRANSACTION_TYPE},
        examples=("How many transactions were processed today?",
                  "What is the total amount of transactions processed today?"),
    ),
    Intent(
        "count_active_loans", "Number of active loans and of customers who hold them",
        """SELECT COUNT(*) AS active_loans, COUNT(DISTINCT customer_id) AS customers_with_active_loans
           FROM loans WHERE loan_status = 'active'""",
        STAFF,
        examples=("How many customers have active loans?", "How many loans are currently active?"),
    ),
    Intent(
        "count_customers", "Total number of customers",
        "SELECT COUNT(*) AS customers FROM customers",
        STAFF,
        examples=("How many customers does the bank have?", "What is our total number of clients?"),
    ),
    Intent(
        "avg_loan_amount", "Average loan amount, optionally by loan status",
        """SELECT ROUND(AVG(loan_amount), 2) AS avg_loan_amount, COUNT(*) AS loan_count
           FROM loans WHERE (:loan_status IS NULL OR loan_status = :loan_status)""",
        (MANAGER,), {"loan_status": LOAN_STATUS},
        examples=("What is the average loan amount for customers?",
                  "What is the average size of active loans?"),
    ),
    Intent(
        "total_loan_portfolio", "Total value of all active loans",
        """SELECT ROUND(COALESCE(SUM(loan_amount), 0), 2) AS total_active_loan_amount, COUNT(*) AS active_loans
           FROM loans WHERE loan_status = 'active'""",
        (MANAGER,),
        examples=("What is the total value of active loans?", "How big is our loan portfolio?"),
    ),
    Intent(
        "total_balance_by_type", "Total balance held, per account type",
        """SELECT account_type, COUNT(*) AS accounts, ROUND(SUM(balance), 2) AS total_balance
           FROM accounts
           WHERE (:account_type IS NULL OR account_type = :account_type)
           GROUP BY account_type ORDER BY account_type""",
        (MANAGER,), {"account_type": ACCOUNT_TYPE},
        examples=("What is the total balance held in checking accounts?",
                  "How much money is in all savings accounts combined?"),
    ),
    Intent(
        "avg_account_balance", "Average account balance, per account type",
        """SELECT account_type, COUNT(*) AS accounts, ROUND(AVG(balance), 2) AS avg_balance
           FROM accounts
           WHERE (:account_type IS NULL OR account_type = :account_type)
           GROUP BY account_type ORDER BY account_type""",
        (MANAGER,), {"account_type": ACCOUNT_TYPE},
        examples=("What is the average savings balance?", "Average balance per account type?"),
    ),
    Intent(
        "new_accounts_trend", "Accounts opened per month over the last N months",
        """SELECT substr(opening_date, 1, 7) AS month, COUNT(*) AS new_accounts
           FROM accounts
           WHERE opening_date BETWEEN :start AND :end
           GROUP BY month ORDER BY month""",
        (MANAGER,), {"months": Param("int", default=6, min=1, max=12)},
        examples=("How did account openings change over the last 6 months?",
                  "Show the monthly trend of new accounts this year."),
    ),
    Intent(
        "largest_transactions", "The largest transactions in a period (account numbers masked)",
        """SELECT t.transaction_id, '****' || substr(a.account_number, -4) AS account,
                  t.transaction_type, t.amount, t.transaction_date
           FROM transactions t JOIN accounts a USING (account_id)
           WHERE t.transaction_date BETWEEN :start AND :end
           ORDER BY t.amount DESC, t.transaction_id
           LIMIT :limit""",
        (MANAGER,), {"period": Param("period", default="this month"),
                     "limit": Param("int", default=5, min=1, max=10)},
        examples=("What were the 5 largest transactions this month?",
                  "Show the biggest transactions in October."),
    ),
    # Added with the multilingual work: bank-wide figures only, for managers.
    Intent(
        "spending_by_category", "Withdrawals per spending category in a period",
        """SELECT category, COUNT(*) AS transaction_count, ROUND(SUM(amount), 2) AS total_spent
           FROM transactions
           WHERE transaction_type = 'withdrawal' AND transaction_date BETWEEN :start AND :end
           GROUP BY category ORDER BY total_spent DESC, category""",
        (MANAGER,), {"period": Param("period", default="this month")},
        examples=("What is the monthly spending by category?",
                  "Show spending by category for October."),
    ),
    Intent(
        "loan_repayment_schedule", "Expected loan repayments per month over the next N months",
        """SELECT substr(due_month, 1, 7) AS month, COUNT(*) AS installments,
                  ROUND(SUM(monthly_payment), 2) AS expected_repayments
           FROM (
               WITH RECURSIVE n(k) AS (SELECT 1 UNION ALL SELECT k + 1 FROM n WHERE k < :months)
               SELECT l.monthly_payment,
                      date(:today, 'start of month', '+' || n.k || ' months') AS due_month
               FROM loans l JOIN n
               WHERE l.loan_status = 'active'
                 AND date(l.start_date, 'start of month', '+' || l.term_months || ' months')
                     >= date(:today, 'start of month', '+' || n.k || ' months')
           )
           GROUP BY month ORDER BY month""",
        (MANAGER,), {"months": Param("int", default=6, min=1, max=12)},
        examples=("What is the loan repayment schedule for the next 6 months?",
                  "How much do we expect in loan repayments per month?"),
    ),
    Intent(
        "balance_trend", "Total balance at the end of each of the last N months",
        """SELECT month, ROUND(
                  (SELECT COALESCE(SUM(balance), 0) FROM accounts WHERE opening_date <= month_end)
                  - (SELECT COALESCE(SUM(CASE WHEN t.transaction_type = 'deposit' THEN t.amount
                                              ELSE -t.amount END), 0)
                     FROM transactions t JOIN accounts a USING (account_id)
                     WHERE t.transaction_date > month_end AND a.opening_date <= month_end), 2)
                  AS end_of_month_balance
           FROM (
               WITH RECURSIVE n(k) AS (SELECT 0 UNION ALL SELECT k + 1 FROM n WHERE k + 1 < :months)
               SELECT substr(date(:today, 'start of month', '-' || k || ' months'), 1, 7) AS month,
                      min(date(:today, 'start of month', '-' || k || ' months', '+1 month', '-1 day'),
                          :today) AS month_end
               FROM n
           )
           ORDER BY month""",
        (MANAGER,), {"months": Param("int", default=6, min=1, max=12)},
        examples=("How did the total balance change over the last 6 months?",
                  "Show the balance trend for this year."),
    ),
    Intent(
        "my_balance", "The logged-in customer's own account balances",
        """SELECT '****' || substr(account_number, -4) AS account, account_type, ROUND(balance, 2) AS balance
           FROM accounts WHERE customer_id = :customer_id ORDER BY account_id""",
        (CUSTOMER,), self_scoped=True,
        examples=("What is my current account balance?", "How much money do I have?"),
    ),
    Intent(
        "my_recent_transactions", "The logged-in customer's own latest transactions",
        """SELECT '****' || substr(a.account_number, -4) AS account, t.transaction_type,
                  t.amount, t.transaction_date
           FROM transactions t JOIN accounts a USING (account_id)
           WHERE a.customer_id = :customer_id
           ORDER BY t.transaction_date DESC, t.transaction_id DESC
           LIMIT :limit""",
        (CUSTOMER,), {"limit": Param("int", default=5, min=1, max=20)}, self_scoped=True,
        examples=("Show my last 5 transactions.", "What are my recent transactions?"),
    ),
    Intent(
        "help", "List what the assistant can answer for this user", None,
        (MANAGER, EMPLOYEE, CUSTOMER),
        examples=("What can you do?", "What questions can I ask?"),
    ),
    # Not real operations: labels the parser uses so the request can be refused.
    Intent(
        "restricted_request", "Asks for individual customer data (always denied to staff)", None, (),
        examples=("Show me the account balances of all customers.",
                  "Give me the email and phone of customer 42."),
    ),
    Intent(
        "out_of_scope", "Anything the assistant does not support", None, (),
        examples=("Transfer 100 euros to account 42.", "What is the weather today?"),
    ),
]}


@dataclass
class QueryResult:
    intent: str
    params: dict                    # the validated parameters actually used
    period: DateRange | None        # the resolved date range, if any
    columns: list
    rows: list                      # list of dicts

    def to_dict(self) -> dict:
        return {"intent": self.intent, "params": self.params,
                "period": self.period.label if self.period else None, "rows": self.rows}


def get_intent(name: str) -> Intent:
    try:
        return INTENTS[name]
    except KeyError:
        raise UnknownIntent(f"Unknown intent: {name!r}") from None


def validate_params(intent: Intent, raw: dict | None, today: date = DEMO_TODAY) -> tuple[dict, DateRange | None]:
    """Check raw params against the intent's spec. Returns (clean params, date range)."""
    raw = dict(raw or {})
    unknown = set(raw) - set(intent.params)
    if unknown:  # also blocks attempts to pass customer_id, start, end, sql, ...
        raise InvalidParams(f"Unknown parameter(s) for {intent.name}: {sorted(unknown)}")

    clean, period = {}, None
    for name, spec in intent.params.items():
        value = raw.get(name)
        if value is None or value == "":
            value = spec.default
        if spec.kind == "period":
            try:
                period = parse_period(value, today=today)
            except DateParseError as exc:
                raise InvalidParams(str(exc)) from None
            clean[name] = value
        elif spec.kind == "choice":
            if value is not None:
                value = str(value).strip().lower()
                if value not in spec.choices:
                    raise InvalidParams(f"{name} must be one of {spec.choices}, got {value!r}")
            clean[name] = value
        elif spec.kind == "int":
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise InvalidParams(f"{name} must be a whole number, got {value!r}") from None
            if not spec.min <= value <= spec.max:
                raise InvalidParams(f"{name} must be between {spec.min} and {spec.max}, got {value}")
            clean[name] = value
    return clean, period


def run_intent(conn: sqlite3.Connection, name: str, raw_params: dict | None = None,
               customer_id: int | None = None, today: date = DEMO_TODAY) -> QueryResult:
    """Validate and run one approved intent on a read-only connection.

    customer_id comes from the login session, never from the question.
    """
    intent = get_intent(name)
    if intent.sql is None:
        raise InvalidParams(f"{name} has no database query")
    params, period = validate_params(intent, raw_params, today)

    sql_params = dict(params)
    sql_params["today"] = today.isoformat()     # extra named parameters are ignored by sqlite3
    sql_params.pop("period", None)
    if period:
        sql_params.update(period.as_sql_params())
    if intent.name == "new_accounts_trend":
        period = parse_period(f"last {params['months']} months", today=today)
        sql_params.update(period.as_sql_params())
        sql_params.pop("months")
    if intent.self_scoped:
        if customer_id is None:
            raise InvalidParams(f"{name} needs a logged-in customer")
        sql_params["customer_id"] = customer_id

    cursor = conn.execute(intent.sql, sql_params)
    columns = [c[0] for c in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return QueryResult(intent.name, params, period, columns, rows)
