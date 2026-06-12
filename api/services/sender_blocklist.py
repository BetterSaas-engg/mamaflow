import json
import re
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "blocked_domains.json"

with open(_CONFIG_PATH) as f:
    _config = json.load(f)

# Pre-compile regex patterns per category
_compiled: dict[str, list[re.Pattern]] = {}
for category, rules in _config.items():
    _compiled[category] = [re.compile(p, re.IGNORECASE) for p in rules.get("patterns", [])]


def _extract_domain(sender: str) -> str:
    """Extract domain from 'Name <user@domain.com>' or 'user@domain.com'."""
    match = re.search(r"<([^>]+)>", sender)
    email = match.group(1) if match else sender.strip()

    if "@" in email:
        return email.split("@", 1)[1].lower()
    return email.lower()


def is_blocked_sender(sender: str) -> tuple[bool, str, str]:
    """Returns (is_blocked, reason, category). Category is '' if not blocked."""
    domain = _extract_domain(sender)

    for category, rules in _config.items():
        if domain in rules.get("exact_domains", []):
            return True, f"exact domain match: {domain}", category

        for pattern in _compiled[category]:
            if pattern.match(domain):
                return True, f"pattern match: {pattern.pattern} on {domain}", category

    return False, "", ""
