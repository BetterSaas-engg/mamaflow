import base64
import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from api.auth.token_store import get_token

MAX_PREVIEW_MESSAGES = 50


def _build_gmail_client(user_email: str):
    token_data = get_token(user_email)
    if not token_data:
        raise ValueError(f"No stored token for {user_email}")

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )
    return build("gmail", "v1", credentials=creds)


def _extract_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower() and "value" in h:
            return h["value"]
    return ""


def _extract_plain_text(payload: dict) -> str:
    """Walk MIME parts to find text/plain and base64url-decode it.

    The payload is attacker-influenceable (anyone can email the user), so a
    malformed part degrades to "" — one bad message must never raise and fail
    the whole sync batch.
    """
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except (ValueError, TypeError):  # binascii.Error is a ValueError
                return ""
        return ""

    # Recurse into multipart
    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text

    return ""


def _list_recent_ids(gmail) -> list[str]:
    thirty_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    query = f"after:{int(thirty_days_ago.timestamp())}"

    results = gmail.users().messages().list(
        userId="me",
        q=query,
        maxResults=MAX_PREVIEW_MESSAGES,
    ).execute()

    return [m["id"] for m in results.get("messages", [])]


def fetch_recent_metadata(user_email: str) -> list[dict]:
    """List the last 30 days of messages with HEADERS ONLY (format="metadata").

    No body is fetched here. The caller checks each sender against the blocklist
    and fetches the body ONLY for senders that pass (AGENTS.md: metadata-first;
    a blocked sender's body is never pulled).
    """
    gmail = _build_gmail_client(user_email)
    metadata = []
    for message_id in _list_recent_ids(gmail):
        msg = gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        metadata.append({
            "message_id": msg["id"],
            "sender": _extract_header(headers, "From"),
            "subject": _extract_header(headers, "Subject"),
            "date": _extract_header(headers, "Date"),
        })
    return metadata


def fetch_message_bodies(user_email: str, message_ids: list[str]) -> dict[str, str]:
    """Fetch full bodies for the given message ids (format="full").

    Only call this with ids whose senders have already passed the blocklist.
    """
    if not message_ids:
        return {}

    gmail = _build_gmail_client(user_email)
    bodies = {}
    for message_id in message_ids:
        msg = gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()
        bodies[message_id] = _extract_plain_text(msg.get("payload", {}))
    return bodies
