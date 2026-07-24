"""Tests for the pre-extraction gate (D36) — cost control, quality-safe.

The gate must err toward PASSING: a false pass costs one cheap Claude call,
a false skip drops a real item. So the negatives here are emails with
genuinely zero temporal or family/action signal.
"""

from api.services.extraction_gate import has_extractable_signal


# --- must PASS (anything that could hold an event or action) ---

def test_month_name_passes():
    assert has_extractable_signal("Newsletter", "The trip is in May.")


def test_weekday_passes():
    assert has_extractable_signal("Reminder", "See you Thursday!")


def test_clock_time_passes():
    assert has_extractable_signal("Note", "Doors open at 3:30 in the gym")


def test_numeric_date_passes():
    assert has_extractable_signal("Note", "Closing on 05/18 for the holiday")


def test_iso_date_passes():
    assert has_extractable_signal("Note", "Deadline 2026-08-01")


def test_relative_day_passes():
    assert has_extractable_signal("Heads up", "Spirit assembly tomorrow!")


def test_action_keyword_passes_without_any_date():
    # The dateless-action case: must reach Claude even with zero temporal tokens.
    assert has_extractable_signal(
        "Action needed", "Please register using the online portal link below."
    )


def test_permission_form_passes():
    assert has_extractable_signal("Note", "Return the signed permission form.")


def test_subject_alone_can_pass():
    assert has_extractable_signal("Soccer practice update", "")


# --- must SKIP (no signal at all) ---

def test_security_alert_skips():
    assert not has_extractable_signal(
        "Security alert",
        "Your password was changed. If this wasn't you, review your account.",
    )


def test_shipping_notice_skips():
    assert not has_extractable_signal(
        "Your order has shipped",
        "Great news! Your package is on its way. Track it anytime with the link.",
    )


def test_generic_marketing_skips():
    assert not has_extractable_signal(
        "You'll love this",
        "Discover our newest arrivals and enjoy free shipping on your order.",
    )


def test_empty_email_skips():
    assert not has_extractable_signal("", "")


# --- keyword false-positive guards (word boundaries) ---

def test_embedded_words_do_not_trip_boundaries():
    # "information" contains "form", "classic" contains "class" — neither
    # should match with word boundaries; no temporal token either.
    assert not has_extractable_signal(
        "Update", "For more information view our classic collection online."
    )
