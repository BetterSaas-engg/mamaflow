"""Step 8 — Claude API extraction.

Takes a PII-redacted email, wraps it in nonce-tagged injection
defenses, sends it to Claude, and parses the response into
structured FamilyEvent objects.
"""

import json
import logging

import anthropic

from api.config.settings import settings
from api.schemas.family_event import ExtractionResponse
from api.services.content_wrapper import build_extraction_prompt, wrap_untrusted_content

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
_log = logging.getLogger(__name__)


_GMAIL_LINK_TEMPLATE = "https://mail.google.com/mail/u/0/#inbox/{message_id}"


def extract_events(
    email_body: str,
    email_subject: str,
    sender: str,
    message_id: str = "",
) -> ExtractionResponse:
    """Run the full extraction pipeline on a single email.

    1. Wrap in nonce-tagged boundaries (injection defense)
    2. Build extraction prompt with locked JSON schema
    3. Call Claude API
    4. Parse JSON response into ExtractionResponse
    5. Stamp source_email_link on each item (built from message_id)
    """
    wrapped, nonce = wrap_untrusted_content(email_body, email_subject, sender)
    prompt = build_extraction_prompt(wrapped, nonce)

    message = _client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = message.content[0].text

    try:
        data = json.loads(raw_text)
        result = ExtractionResponse.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        _log.warning("Failed to parse Claude response: %s — raw: %s", e, raw_text[:200])
        return ExtractionResponse(events=[])

    # Stamp the Gmail deep link — built server-side, never from Claude output
    if message_id:
        link = _GMAIL_LINK_TEMPLATE.format(message_id=message_id)
        for item in result.events:
            item.source_email_link = link

    return result
