"""Role-based access control: may this logged-in user run this intent?

The decision uses only the Session (from login) and the catalog's
allowed_roles. The question text and the LLM have no say in it.
"""
from dataclasses import dataclass

from securebank.auth.auth import Session
from securebank.intents.catalog import INTENTS, Intent


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str        # short machine-readable reason, stored in the audit log
    message: str     # shown to the user when denied


ALLOW = Decision(True, "allowed", "")


def authorize(session: Session | None, intent: Intent) -> Decision:
    if session is None:
        return Decision(False, "not_authenticated", "Please log in first.")
    if intent.name == "restricted_request":
        return Decision(False, "restricted_data",
                        "Access denied. You do not have permission to view individual "
                        "customer records, contact details or balances.")
    if intent.name == "out_of_scope":
        return Decision(False, "out_of_scope",
                        "Sorry, I can't help with that. I can only answer approved, read-only "
                        "banking questions. Type \"help\" to see what you can ask.")
    if session.role not in intent.allowed_roles:
        return Decision(False, "role_not_permitted",
                        f"Access denied. Your role ({session.role}) does not have permission to "
                        f"view: {intent.description.lower()}.")
    if intent.self_scoped and session.customer_id is None:
        return Decision(False, "no_linked_customer",
                        "Access denied. This account is not linked to a customer.")
    return ALLOW


def allowed_intents(role: str) -> list[Intent]:
    return [i for i in INTENTS.values() if role in i.allowed_roles and i.name != "help"]


def help_text(role: str, lang: str = "en") -> str:
    from securebank import i18n
    from securebank.intents.examples import example_in
    if lang != "en":
        lines = [i18n.message("help_intro", lang, role=i18n.role_name(role, lang))]
        for intent in allowed_intents(role):
            lines.append(f"- {i18n.intent_text(intent.name, lang)} (« {example_in(intent.name, lang)} »)")
        return "\n".join(lines)
    lines = [f"As a {role}, you can ask about:"]
    for intent in allowed_intents(role):
        lines.append(f"- {intent.description} (e.g. \"{intent.examples[0]}\")")
    return "\n".join(lines)
