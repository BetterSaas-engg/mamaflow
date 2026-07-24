"""Pre-extraction gate (D36) — skip Claude for emails that cannot yield an item.

A deterministic, in-process regex check that runs BEFORE Presidio and BEFORE
the Claude call. An email is worth extracting only if it contains at least one
temporal token (date, time, month, weekday, relative-day word) OR one
family/action keyword. An email with neither cannot produce a valid FamilyItem
(events need a date/time context; standalone actions are asks like "register",
"complete the form", which the keyword list covers).

Both lists deliberately err toward PASSING: a false pass costs one cheap Claude
call; a false skip silently drops a real item. Common false-pass words ("may",
"sat", "game") are accepted for that reason.

Pure function on in-memory strings — no network, no persistence, and never any
content logging (audit rule: types/counts only). Firewall: the boolean feeds
the sync pipeline only, never the ad layer.
"""

import re

_TEMPORAL = re.compile(
    r"""\b(?:
        january|february|march|april|may|june|july|august|september|october
        |november|december
        |jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec
        |monday|tuesday|wednesday|thursday|friday|saturday|sunday
        |mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun
        |today|tomorrow|tonight|weekend
        |next\s+week
        |\d{1,2}/\d{1,2}          # 5/12, 05/12/2026
        |\d{4}-\d{2}-\d{2}        # ISO date
        |\d{1,2}:\d{2}            # clock time
        |\d{1,2}\s*(?:am|pm)      # 3 pm
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

_KEYWORD = re.compile(
    r"""\b(?:
        rsvp|register|registration|sign[\s-]?up
        |permission|forms?|field\s+trips?|deadline|due|confirm|volunteer
        |practice|rehearsal|recitals?|tryouts?|games?|match|tournament
        |appointment|reschedule|checkup|check-up|dentist|doctor|vaccin\w+
        |pediatric\w*|lessons?|schedule
        |playdate|play\s+date|camp|birthday|party
        |school|class|classroom|teacher|pickup|pick[\s-]?up|drop[\s-]?off
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)


def has_extractable_signal(subject: str, body: str) -> bool:
    """True if the email could plausibly contain a family event or action."""
    text = f"{subject}\n{body}"
    return bool(_TEMPORAL.search(text) or _KEYWORD.search(text))
