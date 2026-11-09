"""Turn a period phrase ("this month", "October", "last 7 days") into exact dates.

This is plain Python on purpose: dates are the most common source of wrong
numbers, so they are never left to the LLM. The LLM (day 5) only copies the
period phrase from the question; this module decides what it means.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta

from securebank.config import DEMO_TODAY
from securebank.intents.lang import ARABIC_LETTERS, normalize_for_rules

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
MONTH_ABBREVIATIONS = {name[:3]: number for name, number in MONTHS.items()}
ALL_TIME_START = date(1900, 1, 1)

# ---- French and Arabic period phrases -> the English phrases parsed below --------
# Everything here is matched on normalize_for_rules() text: no accents, أ/إ/آ -> ا, ة -> ه.

_FRENCH_MONTHS = {
    "janvier": "january", "janv": "january", "fevrier": "february", "fevr": "february",
    "mars": "march", "avril": "april", "avr": "april", "mai": "may", "juin": "june",
    "juillet": "july", "juil": "july", "aout": "august", "septembre": "september",
    "octobre": "october", "novembre": "november", "decembre": "december",
}
_ARABIC_MONTHS = {
    # Standard names
    "يناير": "january", "فبراير": "february", "مارس": "march", "ابريل": "april", "مايو": "may",
    "يونيو": "june", "يوليو": "july", "اغسطس": "august", "سبتمبر": "september",
    "اكتوبر": "october", "نوفمبر": "november", "ديسمبر": "december",
    # Maghreb names
    "جانفي": "january", "فيفري": "february", "افريل": "april", "ماي": "may", "جوان": "june",
    "جويليه": "july", "اوت": "august",
    # Levant and Iraq names
    "كانون الثاني": "january", "شباط": "february", "اذار": "march", "نيسان": "april",
    "ايار": "may", "حزيران": "june", "تموز": "july", "شهر اب": "august", "ايلول": "september",
    "تشرين الاول": "october", "تشرين الثاني": "november", "كانون الاول": "december",
}
_NUMBER_WORDS = {
    "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "douze": 12, "quinze": 15, "vingt": 20, "trente": 30,
    "ثلاثه": 3, "ثلاث": 3, "اربعه": 4, "اربع": 4, "خمسه": 5, "خمس": 5, "سته": 6, "ست": 6,
    "سبعه": 7, "سبع": 7, "ثمانيه": 8, "ثماني": 8, "تسعه": 9, "تسع": 9, "عشره": 10, "عشر": 10,
}
_AR_WORD_START = f"(?<![{ARABIC_LETTERS}])[وبلف]?"      # "و" / "ب" / "ل" / "ف" glued to the word
_AR_WORD_END = f"(?![{ARABIC_LETTERS}])"


def _alternatives(words) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


_NUMBER = _alternatives(_NUMBER_WORDS)
_FR_PAST = r"(?:derniers?|dernieres?|passes?|passees?|precedents?|precedentes?)"
_AR_PAST = r"(?:الماضيه|الماضي|الماضيين|السابقه|السابق|الفائته|الفائت|الاخيره|الاخير|الاخيرين)"
_AR_DAYS = r"(?:ايام|يوما|يوم)"
_AR_MONTHS = r"(?:اشهر|شهور|شهرا|شهر)"
_ISO = r"\d{4}-\d{2}-\d{2}"

_PERIOD_REWRITES = [(re.compile(pattern), replacement) for pattern, replacement in [
    # Exact date ranges
    (rf"\b(?:du|de) ({_ISO}) (?:au|a|jusqu'au) ({_ISO})\b", r"\1 to \2"),
    (rf"من ({_ISO}) (?:الي|حتي) ({_ISO})", r"\1 to \2"),
    # Number words -> digits, only next to a period word
    (rf"\b({_NUMBER}) (?={_FR_PAST} (?:jours?|mois)\b)", lambda m: f"{_NUMBER_WORDS[m[1]]} "),
    (rf"\b{_FR_PAST} ({_NUMBER}) (?=(?:jours?|mois)\b)", lambda m: f"derniers {_NUMBER_WORDS[m[1]]} "),
    (rf"اخر ({_NUMBER}) (?={_AR_DAYS}|{_AR_MONTHS})", lambda m: f"اخر {_NUMBER_WORDS[m[1]]} "),
    (rf"(?<!\S)(?:ال)?({_NUMBER}) (?={_AR_DAYS}|{_AR_MONTHS})", lambda m: f"{_NUMBER_WORDS[m[1]]} "),
    # French: last N days / months, in both word orders
    (rf"\b(\d{{1,3}}) {_FR_PAST} jours?\b", r"last \1 days"),
    (rf"\b{_FR_PAST} (\d{{1,3}}) jours?\b", r"last \1 days"),
    (rf"\b(\d{{1,2}}) {_FR_PAST} mois\b", r"last \1 months"),
    (rf"\b{_FR_PAST} (\d{{1,2}}) mois\b", r"last \1 months"),
    (r"\b(\d{1,3}) jours? (?:derniers|passes|precedents)\b", r"last \1 days"),
    (r"\b(\d{1,2}) mois (?:derniers|passes|precedents)\b", r"last \1 months"),
    # Arabic: last N days / months, and the dual forms
    (rf"اخر (\d{{1,3}}) {_AR_DAYS}{_AR_WORD_END}", r"last \1 days"),
    (rf"اخر (\d{{1,2}}) {_AR_MONTHS}{_AR_WORD_END}", r"last \1 months"),
    (rf"(?:ال)?(\d{{1,3}}) {_AR_DAYS} {_AR_PAST}", r"last \1 days"),
    (rf"(?:ال)?(\d{{1,2}}) {_AR_MONTHS} {_AR_PAST}", r"last \1 months"),
    (r"(?:اخر يومين|اليومين الماضيين|يومين الماضيين)", "last 2 days"),
    (r"(?:اخر شهرين|الشهرين الماضيين|شهرين الماضيين)", "last 2 months"),
    # French fixed phrases
    (r"\baujourd'? ?hui\b|\bce jour\b", "today"),
    (r"(?<!avant-)(?<!avant )\bhier\b", "yesterday"),
    (r"\bcette semaine\b|\bsemaine en cours\b", "this week"),
    (rf"\b(?:la )?semaine {_FR_PAST}\b", "last week"),
    (r"\bdepuis le debut du mois\b|\bce mois(?:[- ]ci)?\b|\bmois en cours\b|\bmois courant\b", "this month"),
    (rf"\b(?:le )?mois {_FR_PAST}\b", "last month"),
    (r"\bdepuis le debut de l'annee\b|\bcette annee\b|\bannee en cours\b", "this year"),
    (rf"\b(?:l')?annee {_FR_PAST}\b|\b(?:l')?an {_FR_PAST}\b", "last year"),
    # Arabic fixed phrases
    (rf"{_AR_WORD_START}اليوم{_AR_WORD_END}", "today"),
    (rf"{_AR_WORD_START}(?:يوم )?امس{_AR_WORD_END}|{_AR_WORD_START}البارحه{_AR_WORD_END}", "yesterday"),
    (r"هذا الاسبوع|الاسبوع الحالي|الاسبوع الجاري", "this week"),
    (rf"الاسبوع {_AR_PAST}", "last week"),
    (r"منذ بدايه الشهر|هذا الشهر|الشهر الحالي|الشهر الجاري", "this month"),
    (rf"الشهر {_AR_PAST}", "last month"),
    (r"منذ بدايه (?:السنه|العام)|هذه السنه|هذا العام|السنه الحاليه|العام الحالي|السنه الجاريه|العام الجاري",
     "this year"),
    (rf"(?:السنه|العام) {_AR_PAST}", "last year"),
    # Month names (longest first, so "تشرين الاول" is tried before anything shorter)
    (rf"\b({_alternatives(_FRENCH_MONTHS)})\b", lambda m: _FRENCH_MONTHS[m[1]]),
    (rf"{_AR_WORD_START}(?:شهر )?({_alternatives(_ARABIC_MONTHS)}){_AR_WORD_END}",
     lambda m: _ARABIC_MONTHS[m[1]]),
]]


def english_period(text: str) -> str:
    """Normalise a phrase or question and rewrite French/Arabic periods in English."""
    text = normalize_for_rules(text or "")
    for pattern, replacement in _PERIOD_REWRITES:
        text = pattern.sub(replacement, text)
    return text


class DateParseError(ValueError):
    """The period phrase is not one we support."""


@dataclass(frozen=True)
class DateRange:
    start: date   # inclusive
    end: date     # inclusive
    label: str    # human-readable, used in answers: "October 2026"

    def as_sql_params(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _last_of_month(year: int, month: int) -> date:
    next_month = date(year + month // 12, month % 12 + 1, 1)
    return next_month - timedelta(days=1)


def _months_back(d: date, n: int) -> date:
    """First day of the month n months before d's month."""
    index = d.year * 12 + (d.month - 1) - n
    return date(index // 12, index % 12 + 1, 1)


def parse_period(phrase: str | None, today: date = DEMO_TODAY) -> DateRange:
    """Parse a period phrase. Raises DateParseError if it is not supported."""
    text = english_period(phrase).strip()
    text = re.sub(r"^(?:(?:in|during|for|of|over|from|the|en|durant|pendant|pour|au|sur|les?|la|في|خلال)\s+)+", "", text)
    text = re.sub(r"\s+", " ", text).rstrip("?.!؟")

    if text in ("", "all time", "ever", "overall", "total", "in total"):
        return DateRange(ALL_TIME_START, today, "all time")
    if text == "today":
        return DateRange(today, today, f"today ({today.isoformat()})")
    if text == "yesterday":
        d = today - timedelta(days=1)
        return DateRange(d, d, f"yesterday ({d.isoformat()})")
    if text == "this week":
        monday = today - timedelta(days=today.weekday())
        return DateRange(monday, today, f"this week ({monday.isoformat()} to {today.isoformat()})")
    if text in ("last week", "previous week"):
        monday = today - timedelta(days=today.weekday() + 7)
        sunday = monday + timedelta(days=6)
        return DateRange(monday, sunday, f"last week ({monday.isoformat()} to {sunday.isoformat()})")
    if text == "this month":
        start = _first_of_month(today)
        return DateRange(start, today, f"this month ({start:%B %Y}, up to {today.isoformat()})")
    if text in ("last month", "previous month"):
        start = _months_back(today, 1)
        return DateRange(start, _last_of_month(start.year, start.month), f"{start:%B %Y}")
    if text == "this year":
        start = date(today.year, 1, 1)
        return DateRange(start, today, f"{today.year} so far")
    if text in ("last year", "previous year"):
        y = today.year - 1
        return DateRange(date(y, 1, 1), date(y, 12, 31), str(y))

    m = re.fullmatch(r"(?:the )?(?:last|past) (\d{1,3}) days?", text)
    if m:
        n = int(m.group(1))
        if n < 1:
            raise DateParseError(f"Unsupported period: {phrase!r}")
        start = today - timedelta(days=n - 1)
        return DateRange(start, today, f"the last {n} days ({start.isoformat()} to {today.isoformat()})")

    m = re.fullmatch(r"(?:the )?(?:last|past) (\d{1,2}) months?", text)
    if m:
        n = int(m.group(1))
        if not 1 <= n <= 24:
            raise DateParseError(f"Unsupported period: {phrase!r}")
        start = _months_back(today, n - 1)
        return DateRange(start, today, f"the last {n} months ({start.isoformat()} to {today.isoformat()})")

    m = re.fullmatch(r"([a-z]+)(?:,? (\d{4}))?", text)
    if m and (m.group(1) in MONTHS or m.group(1) in MONTH_ABBREVIATIONS):
        month = MONTHS.get(m.group(1)) or MONTH_ABBREVIATIONS[m.group(1)]
        if m.group(2):
            year = int(m.group(2))
        else:  # no year given: the most recent such month, never the future
            year = today.year if month <= today.month else today.year - 1
        start = date(year, month, 1)
        if start > today:
            raise DateParseError(f"{phrase!r} is in the future")
        end = min(_last_of_month(year, month), today)
        return DateRange(start, end, f"{start:%B %Y}")

    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?: (?:to|-|until) (\d{4}-\d{2}-\d{2}))?", text)
    if m:
        try:
            start = date.fromisoformat(m.group(1))
            end = date.fromisoformat(m.group(2)) if m.group(2) else start
        except ValueError as exc:
            raise DateParseError(f"Invalid date in {phrase!r}") from exc
        if end < start:
            raise DateParseError(f"End date before start date in {phrase!r}")
        end = min(end, today)
        label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
        return DateRange(start, end, label)

    raise DateParseError(f"Unsupported period: {phrase!r}")
