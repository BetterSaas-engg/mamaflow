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
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _extract_plain_text(payload: dict) -> str:
    """Walk MIME parts to find text/plain and base64url-decode it."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    # Recurse into multipart
    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text

    return ""


def fetch_recent_emails(user_email: str) -> list[dict]:
    gmail = _build_gmail_client(user_email)

    thirty_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    query = f"after:{int(thirty_days_ago.timestamp())}"

    results = gmail.users().messages().list(
        userId="me",
        q=query,
        maxResults=MAX_PREVIEW_MESSAGES,
    ).execute()

    message_ids = results.get("messages", [])
    if not message_ids:
        return []

    emails = []
    for msg_ref in message_ids:
        msg = gmail.users().messages().get(
            userId="me",
            id=msg_ref["id"],
            format="full",
        ).execute()

        headers = msg.get("payload", {}).get("headers", [])
        body = _extract_plain_text(msg.get("payload", {}))

        emails.append({
            "message_id": msg["id"],
            "sender": _extract_header(headers, "From"),
            "subject": _extract_header(headers, "Subject"),
            "date": _extract_header(headers, "Date"),
            "body": body,
        })

    return emails
