"""The request pipeline: authorize -> validate -> query -> answer -> audit.

Day 3 version: the request arrives already structured (intent name + params),
as if the LLM had parsed the question. Day 5 adds the LLM parser in front of
this, and day 7 replaces the plain template answer with an LLM-written one.
Every security decision happens here, in code.
"""
import sqlite3
import time
from dataclasses import dataclass

from securebank.auth.auth import Session
from securebank.intents.catalog import (INTENTS, InvalidParams, QueryResult,
                                        UnknownIntent, get_intent, run_intent)
from securebank.security.audit import AuditLog
from securebank.security.rbac import authorize, help_text


@dataclass
class Response:
    status: str                      # ok / help / denied / invalid / unsupported / error
    message: str                     # what the user sees
    intent: str | None = None
    result: QueryResult | None = None


def format_result(result: QueryResult) -> str:
    """Plain template answer (no LLM). Shows exactly what the database returned."""
    period = f" for {result.period.label}" if result.period else ""
    if len(result.rows) == 1:
        values = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in result.rows[0].items())
        return f"According to the banking database{period}, {values}."
    if not result.rows:
        return f"The banking database has no matching records{period}."
    lines = [f"According to the banking database{period}:"]
    for row in result.rows:
        lines.append("- " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in row.items()))
    return "\n".join(lines)


def handle_request(session: Session | None, intent_name: str, raw_params: dict | None,
                   bank_conn: sqlite3.Connection, audit: AuditLog,
                   question: str | None = None) -> Response:
    started = time.perf_counter()

    def finish(response: Response, decision: str, reason: str, params=None, rows=None) -> Response:
        audit.record(session=session, intent=response.intent, params=params, decision=decision,
                     reason_code=reason, row_count=rows,
                     latency_ms=round((time.perf_counter() - started) * 1000), question=question)
        return response

    # 1. Which approved intent? Anything unknown is treated as out of scope.
    try:
        intent = get_intent(intent_name)
    except UnknownIntent:
        intent = INTENTS["out_of_scope"]

    # 2. Is this user allowed? (role comes from the session, never from the request)
    decision = authorize(session, intent)
    if not decision.allowed:
        status = "unsupported" if decision.code == "out_of_scope" else "denied"
        return finish(Response(status, decision.message, intent.name), status, decision.code)

    # 3. Help needs no database query
    if intent.name == "help":
        return finish(Response("help", help_text(session.role), intent.name), "allowed", "help")

    # 4. Validate parameters and run the approved query (read-only connection)
    try:
        result = run_intent(bank_conn, intent.name, raw_params,
                            customer_id=session.customer_id if intent.self_scoped else None)
    except InvalidParams as exc:
        return finish(Response("invalid", f"I couldn't run that request: {exc}", intent.name),
                      "invalid", "invalid_params")
    except sqlite3.Error:
        return finish(Response("error", "Something went wrong while reading the database.", intent.name),
                      "error", "database_error")

    # 5. Answer (plain template for now) and log
    return finish(Response("ok", format_result(result), intent.name, result),
                  "allowed", "allowed", params=result.params, rows=len(result.rows))
