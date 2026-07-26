"""Pure-function tests for the shared body/ICS helpers (refactor safety net —
the same behaviors are also covered through the Gmail reader's payload tests)."""

from api.services.email_body import calendar_summary_from_ics, compose_body

_ICS = (
    "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
    "SUMMARY:Dentist\r\n"
    "DTSTART;TZID=America/Toronto:20260806T140000\r\n"
    "LOCATION:12 Main St\\, Toronto\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


def test_summary_extracts_fields_and_unescapes():
    out = calendar_summary_from_ics(_ICS)
    assert "Dentist" in out
    assert "2026-08-06 14:00" in out
    assert "12 Main St, Toronto" in out


def test_utc_time_converts_to_app_timezone():
    ics = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
        "SUMMARY:Checkup\r\nDTSTART:20260806T180000Z\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    out = calendar_summary_from_ics(ics)
    assert "14:00" in out  # 18:00Z == 14:00 America/Toronto (EDT)


def test_garbage_ics_degrades_to_empty():
    assert calendar_summary_from_ics("") == ""
    assert calendar_summary_from_ics("not ics") == ""
    assert calendar_summary_from_ics("BEGIN:VEVENT\nEND:VEVENT") == ""  # no fields


def test_compose_orders_invite_before_prose():
    out = compose_body("See you there!", "Calendar invite details:\nEvent: X")
    assert out.index("Event: X") < out.index("See you there!")


def test_compose_handles_either_side_missing():
    assert compose_body("prose only", "") == "prose only"
    assert compose_body("", "invite only") == "invite only"
    assert compose_body("", "") == ""
