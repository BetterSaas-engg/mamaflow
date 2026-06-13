"""Layer 2 — Presidio PII redaction.

Strips account numbers, card numbers, and government IDs from email
bodies before Claude or any downstream consumer sees the content.
Entity scope is intentionally strict: phone numbers and dates of birth
are NOT redacted because they carry useful info in school/doctor emails.
"""

from pydantic import BaseModel
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# Strict entity types — financial and government IDs only
_ENTITY_TYPES = [
    "CREDIT_CARD",
    "US_BANK_NUMBER",
    "IBAN_CODE",
    "US_SSN",
    "CA_SOCIAL_INSURANCE_NUMBER",
]

# Custom recognizer for generic "Account #: 12345678" patterns
_account_number_pattern = Pattern(
    name="account_number_pattern",
    regex=r"(?i)\baccount\s*(?:#|number|no\.?)\s*:?\s*(\d{6,17})\b",
    score=0.7,
)
_account_recognizer = PatternRecognizer(
    supported_entity="US_BANK_NUMBER",
    patterns=[_account_number_pattern],
)

# Presidio's built-in SSN recognizer scores too low without NLP context boost.
# Add a stronger recognizer that fires on XXX-XX-XXXX with nearby keywords.
_ssn_pattern = Pattern(
    name="ssn_with_context",
    regex=r"\b\d{3}-\d{2}-\d{4}\b",
    score=0.85,
)
_ssn_recognizer = PatternRecognizer(
    supported_entity="US_SSN",
    patterns=[_ssn_pattern],
    context=["social", "security", "ssn", "sin", "tax"],
)

# Canadian SIN: XXX-XXX-XXX
_sin_pattern = Pattern(
    name="canadian_sin",
    regex=r"\b\d{3}-\d{3}-\d{3}\b",
    score=0.4,
)
_sin_recognizer = PatternRecognizer(
    supported_entity="CA_SOCIAL_INSURANCE_NUMBER",
    patterns=[_sin_pattern],
    context=["sin", "social", "insurance", "canada", "cra"],
)

# Module-level singletons — expensive to construct, reused across requests
_analyzer = AnalyzerEngine()
_analyzer.registry.add_recognizer(_account_recognizer)
_analyzer.registry.add_recognizer(_ssn_recognizer)
_analyzer.registry.add_recognizer(_sin_recognizer)
_anonymizer = AnonymizerEngine()

# Replace PII with readable tags so Claude can still parse the email structure
_OPERATORS = {
    entity: OperatorConfig("replace", {"new_value": f"<{entity}>"})
    for entity in _ENTITY_TYPES
}


class RedactionResult(BaseModel):
    redacted_text: str
    entities_found: int
    entity_types: list[str]


def redact_pii(text: str) -> RedactionResult:
    """Run Presidio on text and replace PII with placeholder tags.

    Returns the redacted text plus metadata about what was found.
    """
    if not text or not text.strip():
        return RedactionResult(redacted_text=text, entities_found=0, entity_types=[])

    results = _analyzer.analyze(
        text=text,
        entities=_ENTITY_TYPES,
        language="en",
    )

    if not results:
        return RedactionResult(redacted_text=text, entities_found=0, entity_types=[])

    anonymized = _anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=_OPERATORS,
    )

    found_types = sorted(set(r.entity_type for r in results))

    return RedactionResult(
        redacted_text=anonymized.text,
        entities_found=len(results),
        entity_types=found_types,
    )
