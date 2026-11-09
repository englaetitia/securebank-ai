"""The request pipeline: authorize -> validate -> query -> answer -> audit.

handle_request() takes a structured request (intent name + params).
ask() (day 5) puts the LLM question parser in front of it. Day 7 passes an
LLM answer writer as write_answer; the plain template stays as the fallback.
Every security decision happens here, in code.

Multilingual update: ask() detects the question's language and fixes typos,
remembers the previous question for follow-ups, and asks "Did you mean...?"
when a match is borderline. French and Arabic answers use translated templates.
"""
import sqlite3
import time
from dataclasses import dataclass

from securebank import i18n
from securebank.auth.auth import Session
from securebank.conversation import ConversationContext, resolve_followup
from securebank.intents.catalog import (INTENTS, InvalidParams, QueryResult,
                                        UnknownIntent, get_intent, run_intent)
from securebank.intents.examples import example_in
from securebank.intents.lang import detect_language
from securebank.intents.rules import forced_intent
from securebank.intents.typos import correct_typos
from securebank.security.audit import AuditLog
from securebank.security.input_guard import InputRejected, clean_question
from securebank.security.masking import sanitize_result
from securebank.security.output_guard import KnownPII, check_answer
from securebank.security.request_guard import asks_about_a_person
from securebank.security.rbac import authorize, help_text

SAFE_FALLBACK = ("I found the information, but I can't show this answer because it did not "
                 "pass the privacy and accuracy checks. Please rephrase your question.")


@dataclass
class Response:
    status: str                      # ok / help / denied / invalid / unsupported / blocked / error / clarify
    message: str                     # what the user sees
    intent: str | None = None
    result: QueryResult | None = None
    details: dict | None = None      # how the question was parsed (shown in the demo panel)
    answer_source: str | None = None  # template / llm / fallback_template (day 7)
    lang: str = "en"
    suggestions: list | None = None  # example questions to offer when status is "clarify"


def format_result(result: QueryResult, lang: str = "en") -> str:
    """Plain template answer (no LLM). Shows exactly what the database returned."""
    if lang != "en":
        return i18n.format_result(result, lang)
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
                   question: str | None = None, known_pii: KnownPII | None = None,
                   write_answer=None, lang: str = "en") -> Response:
    """Run one structured request through every check.

    write_answer: optional function(result) -> str that phrases the answer
    (the LLM from day 7). Without it, the plain template is used. Its prompt is
    English-only and untested in other languages, so French and Arabic answers
    always use the translated template.
    """
    started = time.perf_counter()
    if lang != "en":
        write_answer = None

    def finish(response: Response, decision: str, reason: str, params=None, rows=None) -> Response:
        response.lang = lang
        audit.record(session=session, intent=response.intent, params=params, decision=decision,
                     reason_code=reason, row_count=rows,
                     latency_ms=round((time.perf_counter() - started) * 1000), question=question)
        return response

    def text(key: str, english: str, **fields) -> str:
        return english if lang == "en" else i18n.message(key, lang, **fields)

    # 1. Which approved intent? Anything unknown is treated as out of scope.
    try:
        intent = get_intent(intent_name)
    except UnknownIntent:
        intent = INTENTS["out_of_scope"]

    # 2. Is this user allowed? (role comes from the session, never from the request)
    decision = authorize(session, intent)
    if not decision.allowed:
        status = "unsupported" if decision.code == "out_of_scope" else "denied"
        shown = i18n.decision_message(decision.code, lang, decision.message,
                                      role=session.role if session else None, intent=intent.name)
        return finish(Response(status, shown, intent.name), status, decision.code)

    # 3. Help needs no database query
    if intent.name == "help":
        return finish(Response("help", help_text(session.role, lang), intent.name), "allowed", "help")

    # 4. Validate parameters and run the approved query (read-only connection)
    try:
        result = run_intent(bank_conn, intent.name, raw_params,
                            customer_id=session.customer_id if intent.self_scoped else None)
    except InvalidParams as exc:
        return finish(Response("invalid", text("invalid", f"I couldn't run that request: {exc}", detail=exc),
                               intent.name), "invalid", "invalid_params")
    except sqlite3.Error:
        return finish(Response("error", text("database_error", "Something went wrong while reading the database."),
                               intent.name), "error", "database_error")

    # 5. Privacy layer 2: drop forbidden columns, mask personal data
    result = sanitize_result(result)

    # 6. Write the answer, then check it for leaks and invented numbers
    answer = write_answer(result) if write_answer else format_result(result, lang)
    guard = check_answer(answer, result, known_pii)
    if not guard.ok:
        template = format_result(result, lang)
        if write_answer and check_answer(template, result, known_pii).ok:
            # the LLM's wording failed, the plain template is safe: use it
            return finish(Response("ok", template, intent.name, result, details={"guard": guard.problems},
                                   answer_source="fallback_template"),
                          "allowed", "fallback_template", params=result.params, rows=len(result.rows))
        return finish(Response("blocked", text("blocked", SAFE_FALLBACK), intent.name,
                               details={"guard": guard.problems}),
                      "blocked", "output_guard", params=result.params, rows=len(result.rows))

    source = getattr(write_answer, "last_source", "llm") if write_answer else "template"
    return finish(Response("ok", answer, intent.name, result, answer_source=source),
                  "allowed", "allowed", params=result.params, rows=len(result.rows))


NOT_UNDERSTOOD = ("Sorry, I didn't understand that question. Type \"help\" to see the "
                  "questions I can answer.")


def _clarifying_response(session: Session, candidates: list, lang: str, audit: AuditLog,
                         question: str, details: dict) -> Response | None:
    """Offer the near matches this user may ask about. Nothing is queried."""
    allowed = [name for name in candidates if session.role in INTENTS[name].allowed_roles]
    if not allowed:
        return None
    suggestions = [example_in(name, lang) for name in allowed]
    lines = [i18n.message("clarify", lang)] + [f"- {s}" for s in suggestions]
    audit.record(session=session, intent=None, params=None, decision="clarify",
                 reason_code="borderline_match", question=question)
    return Response("clarify", "\n".join(lines), details={**details, "candidates": allowed},
                    lang=lang, suggestions=suggestions)


def ask(session: Session | None, question: str, parser, bank_conn: sqlite3.Connection,
        audit: AuditLog, known_pii: KnownPII | None = None, write_answer=None,
        context: ConversationContext | None = None) -> Response:
    """Natural-language entry point: question -> parser -> handle_request().

    The parser (LLM, embedding or hybrid) only proposes an intent and params.
    Every check in handle_request() still applies to whatever it proposes.
    `context` (optional) lets a question follow on from the previous answer.
    """
    try:
        question = clean_question(question)
    except InputRejected as exc:
        audit.record(session=session, intent=None, params=None, decision="invalid",
                     reason_code="input_rejected")
        return Response("invalid", str(exc))

    lang = detect_language(question, default=context.last_lang if context else "en")
    if session is None:  # do not spend LLM time on users who are not logged in
        return handle_request(None, "help", {}, bank_conn, audit, question=question, lang=lang)

    corrected, fixes = correct_typos(question)
    typo_details = {"typos_fixed": fixes} if fixes else {}

    # Questions about specific people are refused before any parser runs (day 12).
    # Both spellings are checked, so correcting a typo can never hide anything.
    reason = asks_about_a_person(question, known_pii) or asks_about_a_person(corrected, known_pii)
    if reason:
        response = handle_request(session, "restricted_request", {}, bank_conn, audit,
                                  question=question, lang=lang)
        response.details = {"parser": "request_guard", "attempts": 0, "parse_ms": 0,
                            "raw_output": None, "error": None, "guard_reason": reason,
                            "intent": "restricted_request", "params": {}}
        return response

    def remember(response: Response) -> Response:
        if context is not None and response.status == "ok" and response.result is not None:
            context.remember(response.intent, response.result.params, lang)
        return response

    # A follow-up reuses the last intent; a refusal rule always wins over it
    followup = resolve_followup(corrected, context) if not forced_intent(corrected) else None
    if followup:
        intent, params = followup
        details = {"parser": "follow_up", "attempts": 0, "parse_ms": 0, "raw_output": None,
                   "error": None, "intent": intent, "params": params, **typo_details}
        response = handle_request(session, intent, params, bank_conn, audit, question=question,
                                  known_pii=known_pii, write_answer=write_answer, lang=lang)
        response.details = {**details, **(response.details or {})}
        return remember(response)

    outcome = parser.parse(corrected)
    details = {"parser": outcome.source, "attempts": outcome.attempts,
               "parse_ms": outcome.latency_ms, "raw_output": outcome.raw, "error": outcome.error,
               **typo_details}
    if outcome.request is None:
        audit.record(session=session, intent=None, params=None, decision="unsupported",
                     reason_code="parse_failed", latency_ms=outcome.latency_ms, question=question)
        message = NOT_UNDERSTOOD if lang == "en" else i18n.message("not_understood", lang)
        return Response("unsupported", message, details=details, lang=lang)

    if outcome.candidates:
        clarifying = _clarifying_response(session, outcome.candidates, lang, audit, question, details)
        if clarifying:
            return clarifying

    details.update(intent=outcome.request.intent, params=outcome.request.params)
    response = handle_request(session, outcome.request.intent, outcome.request.params,
                              bank_conn, audit, question=question, known_pii=known_pii,
                              write_answer=write_answer, lang=lang)
    response.details = {**details, **(response.details or {})}
    return remember(response)
