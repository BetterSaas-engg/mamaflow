"""imap_reader tests — FakeIMAP only, never a live connection.

Load-bearing invariants proven here:
  - metadata pass fetches HEADERS ONLY (metadata-first — executable assert)
  - readonly SELECT + BODY.PEEK everywhere (mailbox never mutated)
  - RFC 2047 headers decoded before they reach the caller (blocklist sees
    real text), defensive degradation on malformed input
  - Message-ID normalization + stable fallback hash
"""

import imaplib

import pytest

from api.auth.token_store import store_token
from api.services import imap_reader
from api.services.reader_errors import ReauthRequired

EMAIL = "parent@rogers.com"


def _rfc822(headers: str, body: str = "") -> bytes:
    return (headers.replace("\n", "\r\n") + "\r\n\r\n" + body.replace("\n", "\r\n")).encode()


PLAIN_MSG = _rfc822(
    "From: School <office@school.org>\n"
    "Subject: Practice Thursday\n"
    "Date: Fri, 24 Jul 2026 09:00:00 -0400\n"
    "Message-ID: <abc123@school.org>\n"
    "Content-Type: text/plain; charset=utf-8",
    "Soccer practice moves to Thursday 3:30 PM.",
)

ENCODED_MSG = _rfc822(
    "From: =?UTF-8?Q?=C3=89cole_Rivi=C3=A8re?= <info@ecole.qc.ca>\n"
    "Subject: =?UTF-8?B?UsOpdW5pb24gZGVzIHBhcmVudHM=?=\n"
    "Date: Sat, 25 Jul 2026 10:00:00 -0400\n"
    "Message-ID: <enc1@ecole.qc.ca>\n"
    "Content-Type: text/plain; charset=utf-8",
    "Bonjour",
)

NO_MSGID_MSG = _rfc822(
    "From: a@b.com\nSubject: Hi\nDate: Sun, 26 Jul 2026 08:00:00 -0400\n"
    "Content-Type: text/plain; charset=utf-8",
    "x",
)

ICS_INVITE_MSG = _rfc822(
    "From: Bookings <no-reply@bookings.example>\n"
    "Subject: Discovery Session\n"
    "Date: Fri, 24 Jul 2026 14:59:00 -0400\n"
    "Message-ID: <invite1@bookings.example>\n"
    'Content-Type: multipart/mixed; boundary="B1"',
    '--B1\nContent-Type: text/plain; charset=utf-8\n\n'
    "This meeting was scheduled from the bookings page.\n"
    "--B1\nContent-Type: text/calendar; method=REQUEST\n\n"
    "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
    "SUMMARY:Discovery Session\n"
    "DTSTART;TZID=America/Toronto:20260806T140000\n"
    "LOCATION:Microsoft Teams meeting\n"
    "END:VEVENT\nEND:VCALENDAR\n"
    "--B1--\n",
)

QP_MSG = _rfc822(
    "From: c@d.com\nSubject: QP\nDate: Mon, 27 Jul 2026 08:00:00 -0400\n"
    "Message-ID: <qp1@d.com>\n"
    "Content-Type: text/plain; charset=utf-8\n"
    "Content-Transfer-Encoding: quoted-printable",
    "R=C3=A9union demain 9:00",
)


def _headers_only(raw: bytes) -> bytes:
    head = raw.split(b"\r\n\r\n", 1)[0]
    keep = []
    for line in head.split(b"\r\n"):
        lowered = line.lower()
        if lowered.startswith((b"from:", b"subject:", b"date:", b"message-id:")) or (
            keep and line[:1] in (b" ", b"\t")
        ):
            keep.append(line)
    return b"\r\n".join(keep) + b"\r\n\r\n"


class FakeIMAP:
    """Scripted imaplib.IMAP4_SSL stand-in. Messages: {uid(bytes): rfc822}."""

    instances: list["FakeIMAP"] = []

    messages: dict[bytes, bytes] = {}
    fail_login = False
    fail_select = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.commands: list[str] = []
        self.selected_readonly = None
        self.logged_out = False
        FakeIMAP.instances.append(self)

    def login(self, user, password):
        self.commands.append("LOGIN")
        if FakeIMAP.fail_login:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] LOGIN failed")
        return "OK", [b"LOGIN completed"]

    def select(self, mailbox, readonly=False):
        self.commands.append(f"SELECT readonly={readonly}")
        self.selected_readonly = readonly
        if FakeIMAP.fail_select:
            return "NO", [b"cannot select"]
        return "OK", [b"1"]

    def uid(self, command, *args):
        rendered = " ".join(str(a) for a in args if a is not None)
        self.commands.append(f"UID {command} {rendered}")
        if command == "SEARCH":
            return "OK", [b" ".join(sorted(FakeIMAP.messages))]
        if command == "FETCH":
            uid_set, spec = args[0], args[1]
            wanted = [u.encode() for u in str(uid_set).split(",")]
            out = []
            for uid in wanted:
                raw = FakeIMAP.messages.get(uid)
                if raw is None:
                    continue
                payload = raw if "BODY.PEEK[]" in spec else _headers_only(raw)
                out.append((b"%s (UID %s BODY[] {%d}" % (uid, uid, len(payload)), payload))
                out.append(b")")
            return "OK", out
        return "NO", [b""]

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]


@pytest.fixture(autouse=True)
def fake_imap(monkeypatch):
    FakeIMAP.instances = []
    FakeIMAP.messages = {}
    FakeIMAP.fail_login = False
    FakeIMAP.fail_select = False
    monkeypatch.setattr(imap_reader.imaplib, "IMAP4_SSL", FakeIMAP)
    store_token(
        EMAIL,
        {"kind": "imap_app_password", "provider": "yahoo",
         "username": EMAIL, "app_password": "abcd efgh ijkl mnop"},
        provider="yahoo",
    )
    yield


def test_metadata_returns_decoded_headers_and_message_ids():
    FakeIMAP.messages = {b"1": PLAIN_MSG, b"2": ENCODED_MSG}

    meta = imap_reader.fetch_recent_metadata(EMAIL, "yahoo")

    by_id = {m["message_id"]: m for m in meta}
    assert by_id["abc123@school.org"]["subject"] == "Practice Thursday"
    # RFC 2047 decoded — the blocklist and extractor see real text
    assert by_id["enc1@ecole.qc.ca"]["subject"] == "Réunion des parents"
    assert "École Rivière" in by_id["enc1@ecole.qc.ca"]["sender"]


def test_metadata_pass_never_fetches_bodies():
    """Executable metadata-first invariant: header pass = zero full-body FETCH."""
    FakeIMAP.messages = {b"1": PLAIN_MSG}

    imap_reader.fetch_recent_metadata(EMAIL, "yahoo")

    conn = FakeIMAP.instances[0]
    assert not any("BODY.PEEK[]" in c for c in conn.commands)
    assert any("HEADER.FIELDS" in c and "PEEK" in c for c in conn.commands)


def test_mailbox_is_never_mutated():
    FakeIMAP.messages = {b"1": PLAIN_MSG}

    imap_reader.fetch_recent_metadata(EMAIL, "yahoo")
    imap_reader.fetch_message_bodies(EMAIL, ["abc123@school.org"], "yahoo")

    for conn in FakeIMAP.instances:
        assert conn.selected_readonly is True
        assert all("PEEK" in c for c in conn.commands if "FETCH" in c)
        assert conn.logged_out


def test_bodies_fetched_only_for_requested_ids():
    FakeIMAP.messages = {b"1": PLAIN_MSG, b"2": ENCODED_MSG}

    bodies = imap_reader.fetch_message_bodies(EMAIL, ["abc123@school.org"], "yahoo")

    assert list(bodies) == ["abc123@school.org"]
    assert "Soccer practice" in bodies["abc123@school.org"]
    conn = FakeIMAP.instances[0]
    assert sum(1 for c in conn.commands if "BODY.PEEK[]" in c) == 1  # only uid 1


def test_ics_invite_produces_calendar_block_before_prose():
    FakeIMAP.messages = {b"3": ICS_INVITE_MSG}

    bodies = imap_reader.fetch_message_bodies(EMAIL, ["invite1@bookings.example"], "yahoo")

    body = bodies["invite1@bookings.example"]
    assert "Calendar invite details" in body
    assert "2026-08-06 14:00" in body
    assert body.index("Discovery Session") < body.index("scheduled from the bookings")


def test_quoted_printable_body_is_decoded():
    FakeIMAP.messages = {b"4": QP_MSG}

    bodies = imap_reader.fetch_message_bodies(EMAIL, ["qp1@d.com"], "yahoo")

    assert "Réunion demain 9:00" in bodies["qp1@d.com"]


def test_missing_message_id_falls_back_to_stable_hash():
    FakeIMAP.messages = {b"5": NO_MSGID_MSG}

    first = imap_reader.fetch_recent_metadata(EMAIL, "yahoo")
    second = imap_reader.fetch_recent_metadata(EMAIL, "yahoo")

    assert first[0]["message_id"].startswith("imap-")
    assert first[0]["message_id"] == second[0]["message_id"]  # stable across syncs


def test_vanished_message_is_omitted_not_raised():
    FakeIMAP.messages = {b"1": PLAIN_MSG}

    bodies = imap_reader.fetch_message_bodies(EMAIL, ["gone@nowhere"], "yahoo")

    assert bodies == {}


def test_revoked_app_password_raises_reauth():
    FakeIMAP.fail_login = True

    with pytest.raises(ReauthRequired):
        imap_reader.fetch_recent_metadata(EMAIL, "yahoo")


def test_missing_credential_raises_reauth():
    with pytest.raises(ReauthRequired):
        imap_reader.fetch_recent_metadata("nobody@rogers.com", "yahoo")


def test_google_shaped_credential_is_rejected():
    store_token("mixed@rogers.com", {"token": "ya29"}, provider="yahoo")  # wrong kind

    with pytest.raises(ReauthRequired):
        imap_reader.fetch_recent_metadata("mixed@rogers.com", "yahoo")


def test_since_date_uses_english_months(monkeypatch):
    assert imap_reader._since_date().split("-")[1] in imap_reader._MONTHS
