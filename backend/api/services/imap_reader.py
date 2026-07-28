"""IMAP mail reader (Yahoo/Rogers, iCloud — app-password providers).

Same two-function contract as gmail_reader — plain dicts, so sync_runner
needs no knowledge of the transport:

  fetch_recent_metadata(email, provider) -> [{"message_id","sender","subject","date"}]
  fetch_message_bodies(email, ids, provider) -> {message_id: body_text}

Invariants (mirroring the Gmail reader + AGENTS.md):
  - Metadata-first: the first pass fetches ONLY header fields
    (BODY.PEEK[HEADER.FIELDS ...]); full bodies are fetched exclusively for
    ids the caller passes to fetch_message_bodies (blocklist-passed,
    not-yet-synced).
  - Never mutate the mailbox: readonly SELECT plus BODY.PEEK everywhere —
    the \\Seen flag must never be set by Mamaflow.
  - Defensive parsing: one malformed message degrades to ""/skip, never
    fails the batch. Logging is types/counts only — never headers, bodies,
    or credentials.

All functions are synchronous (imaplib is blocking); callers wrap them in
asyncio.to_thread exactly like the Gmail reader's calls.
"""

import datetime
import email.parser
import email.policy
import hashlib
import imaplib
import logging
import re

from api.auth.token_store import get_token
from api.config.settings import settings
from api.services.email_body import calendar_summary_from_ics, compose_body
from api.services.mail_providers import get_provider
from api.services.reader_errors import ReauthRequired

MAX_PREVIEW_MESSAGES = 50  # parity with gmail_reader

_log = logging.getLogger(__name__)

# Explicit English month names — IMAP date syntax is locale-independent, but
# strftime('%b') is NOT (a de_DE locale would emit "Mär" and break SEARCH).
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_HEADER_FIELDS = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
_UID_RE = re.compile(rb"UID (\d+)")


def _connect(user_email: str, provider_key: str) -> imaplib.IMAP4_SSL:
    """Open + authenticate + readonly-select INBOX, or raise.

    ReauthRequired for anything the user must fix by signing in again
    (missing/wrong-kind credential, revoked app password). Network errors
    propagate as-is — transient, the sync reports a generic retryable failure.
    """
    provider = get_provider(provider_key)
    if provider is None or provider.imap_host is None:
        raise ReauthRequired

    cred = get_token(user_email, provider_key)
    if not cred or cred.get("kind") != "imap_app_password":
        raise ReauthRequired

    conn = imaplib.IMAP4_SSL(
        provider.imap_host, provider.imap_port, timeout=settings.imap_timeout_seconds
    )
    try:
        conn.login(cred["username"], cred["app_password"])
    except imaplib.IMAP4.error as exc:
        _shutdown(conn)
        # Revoked/changed app password — the user must reconnect.
        raise ReauthRequired from exc
    except Exception:
        _shutdown(conn)
        raise

    typ, _ = conn.select("INBOX", readonly=True)
    if typ != "OK":
        _shutdown(conn)
        # Post-auth select failure is a mailbox/provider problem, not a
        # credential one — surface as a transient sync failure.
        raise RuntimeError("IMAP INBOX select failed")
    return conn


def _shutdown(conn) -> None:
    try:
        conn.logout()
    except Exception:
        pass


def _since_date() -> str:
    d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).date()
    return f"{d.day}-{_MONTHS[d.month - 1]}-{d.year}"


def _search_recent_uids(conn) -> list[bytes]:
    typ, data = conn.uid("SEARCH", None, "SINCE", _since_date())
    if typ != "OK" or not data or not data[0]:
        return []
    uids = data[0].split()
    # Wide scan window: capping here at the per-run size meant anything older
    # than the newest N was never listed again once those synced — silently
    # unextracted. Header fetches are batched, so a wide window is cheap.
    return uids[-settings.sync_scan_max_messages:]


def _parse_header_blob(literal: bytes):
    """Header bytes -> EmailMessage (policy.default decodes RFC 2047 encoded
    words on access). None when even the fallback parser chokes."""
    try:
        return email.parser.BytesParser(policy=email.policy.default).parsebytes(literal)
    except Exception:
        try:
            return email.parser.BytesParser(policy=email.policy.compat32).parsebytes(literal)
        except Exception:
            return None


def _header(msg, name: str) -> str:
    """Decoded header value, '' when absent/undecodable. policy.default can
    raise at ACCESS time on pathological values — contain it per header."""
    try:
        value = msg[name]
        return str(value) if value is not None else ""
    except Exception:
        return ""


def _canonical_message_id(sender: str, subject: str, date: str, raw_mid: str) -> str:
    """RFC 5322 Message-ID (normalized) — globally unique by construction and
    stable across syncs/UIDVALIDITY. Fallback: a stable content hash with an
    'imap-' prefix (never collides with Gmail's hex ids)."""
    mid = raw_mid.strip().strip("<>").strip()
    if mid:
        return mid
    digest = hashlib.sha256(
        f"{sender}\x00{date}\x00{subject}".encode("utf-8", errors="replace")
    ).hexdigest()
    return f"imap-{digest[:40]}"


def _fetch_headers(conn, uids: list[bytes]) -> list[tuple[str, dict]]:
    """Batched header-only fetch -> [(uid, metadata_dict)]. Malformed response
    entries are skipped, never raised."""
    if not uids:
        return []
    uid_set = b",".join(uids).decode()
    typ, data = conn.uid("FETCH", uid_set, _HEADER_FIELDS)
    if typ != "OK" or not data:
        return []

    out: list[tuple[str, dict]] = []
    for entry in data:
        # imaplib interleaves (b'<n> (UID <uid> BODY[...] {len}', b'<literal>')
        # tuples with bare b')' closers — only the tuples carry data.
        if not isinstance(entry, tuple) or len(entry) < 2:
            continue
        prefix = entry[0] or b""
        uid_match = _UID_RE.search(prefix)
        if not uid_match:
            continue
        msg = _parse_header_blob(entry[1] or b"")
        if msg is None:
            continue
        sender = _header(msg, "From")
        subject = _header(msg, "Subject")
        date = _header(msg, "Date")
        out.append((
            uid_match.group(1).decode(),
            {
                "message_id": _canonical_message_id(
                    sender, subject, date, _header(msg, "Message-ID")
                ),
                "sender": sender,
                "subject": subject,
                "date": date,
            },
        ))
    return out


def _recent_metadata(user_email: str, provider: str) -> list[dict]:
    """Newest-first metadata for the scan window. One batched header FETCH."""
    conn = _connect(user_email, provider)
    try:
        rows = [meta for _uid, meta in _fetch_headers(conn, _search_recent_uids(conn))]
    finally:
        _shutdown(conn)
    rows.reverse()  # UIDs ascend (oldest first); callers expect newest first
    return rows


def list_recent_ids(user_email: str, provider: str) -> list[str]:
    """Message ids in the scan window, newest first.

    Unlike Gmail (where ids come from a cheap id-only list call), an IMAP
    message id IS a header, so this necessarily fetches headers — but in one
    batched FETCH, and still without touching any body (metadata-first)."""
    return [m["message_id"] for m in _recent_metadata(user_email, provider)]


def fetch_metadata(user_email: str, message_ids: list[str], provider: str) -> list[dict]:
    """Headers for the given ids. Stateless re-resolution (a fresh batched
    header pass, filtered) — same philosophy as fetch_message_bodies, so no
    UID/connection state is carried between calls."""
    if not message_ids:
        return []
    wanted = set(message_ids)
    return [m for m in _recent_metadata(user_email, provider) if m["message_id"] in wanted]


def _part_text(part) -> str:
    try:
        return part.get_content()
    except Exception:
        try:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        except Exception:
            return ""


def _extract_text_parts(msg) -> tuple[str, str]:
    """(first text/plain part, first text/calendar part) — '' when absent.
    text/calendar is accepted even as an attachment (invite.ics); text/plain
    attachments are skipped. HTML-only mail yields '' (Gmail-reader parity)."""
    plain, ics = "", ""
    try:
        for part in msg.walk():
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            if content_type == "text/calendar" and not ics:
                ics = _part_text(part)
            elif content_type == "text/plain" and not plain:
                if part.get_content_disposition() == "attachment":
                    continue
                plain = _part_text(part)
    except Exception:
        pass
    return plain, ics


def fetch_message_bodies(
    user_email: str, message_ids: list[str], provider: str
) -> dict[str, str]:
    """Full bodies for the given (blocklist-passed) message ids.

    Stateless UID re-resolution: a fresh SEARCH + header-stub pass rebuilds
    {message_id: uid} on this connection, making the reader immune to
    UIDVALIDITY changes between the metadata and body passes. Ids that
    vanished mid-sync are omitted (sync_runner treats a missing body as "")."""
    if not message_ids:
        return {}

    conn = _connect(user_email, provider)
    try:
        uid_by_mid = {
            meta["message_id"]: uid
            for uid, meta in _fetch_headers(conn, _search_recent_uids(conn))
        }
        bodies: dict[str, str] = {}
        for mid in message_ids:
            uid = uid_by_mid.get(mid)
            if uid is None:
                continue
            typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not data:
                continue
            raw = next(
                (entry[1] for entry in data if isinstance(entry, tuple) and len(entry) > 1),
                None,
            )
            if not raw:
                continue
            try:
                msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(raw)
            except Exception:
                continue
            plain, ics = _extract_text_parts(msg)
            bodies[mid] = compose_body(plain, calendar_summary_from_ics(ics))
        return bodies
    finally:
        _shutdown(conn)
