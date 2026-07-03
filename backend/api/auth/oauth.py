import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import create_access_token
from api.auth.token_store import store_token
from api.config.settings import settings
from api.db.session import get_db
from api.services.users import get_or_create_user

_log = logging.getLogger(__name__)

# Phase 0: in-memory PKCE state, same pattern as token_store
_pending_states: dict[str, str] = {}

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _build_flow() -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )


@router.get("/google")
async def google_login():
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    _pending_states[state] = flow.code_verifier
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(request: Request):
    state = request.query_params["state"]
    flow = _build_flow()
    flow.code_verifier = _pending_states.pop(state)
    flow.fetch_token(code=request.query_params["code"])

    credentials = flow.credentials
    # Decode the ID token to get the user's email
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleRequest

    id_info = id_token.verify_oauth2_token(
        credentials.id_token,
        GoogleRequest(),
        settings.google_client_id,
    )

    user_email = id_info["email"]

    store_token(user_email, {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes),
    })

    return {
        "message": "OAuth successful",
        "email": user_email,
    }


# --- Mobile auth (D23): OAuth 2.0 authorization-code + PKCE ---
#
# The app runs the OAuth consent directly (flutter_web_auth_2), obtaining an
# authorization code with a PKCE verifier, and posts {code, code_verifier,
# redirect_uri} here. The backend exchanges them with the iOS OAuth client id
# and the PKCE verifier — installed-app clients have NO secret. Gmail tokens
# stay server-side (D4); identity comes from the verified id_token, never the
# client. (google_sign_in's serverAuthCode can't cover an added scope like Gmail
# on iOS — see DECISIONS.)

_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def mobile_redirect_uri(ios_client_id: str) -> str:
    """The reversed-client-id redirect used by the app, derived server-side so
    the client can never influence the value sent to Google (defense-in-depth;
    Google independently enforces the /authorize <-> /token match)."""
    prefix = ios_client_id.replace(".apps.googleusercontent.com", "")
    return f"com.googleusercontent.apps.{prefix}:/oauth2redirect"


class MobileAuthRequest(BaseModel):
    code: str
    code_verifier: str


class MobileAuthUser(BaseModel):
    id: str
    email: str


class MobileAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: MobileAuthUser


async def exchange_code_pkce(
    code: str,
    code_verifier: str,
) -> tuple[dict, str]:
    """Exchange a PKCE authorization code for Gmail tokens; return (creds, email).

    Uses the iOS client id + PKCE verifier (no client secret); the redirect_uri
    is derived server-side, never client-supplied. Identity is taken from the
    verified id_token, never trusted from the client.
    """
    import asyncio

    import httpx
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(
            _GOOGLE_TOKEN_URI,
            data={
                "client_id": settings.google_ios_client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": mobile_redirect_uri(settings.google_ios_client_id),
                "grant_type": "authorization_code",
            },
        )
    resp.raise_for_status()
    tokens = resp.json()

    # verify_oauth2_token fetches Google's signing certs with a SYNC transport —
    # run it off the event loop.
    id_info = await asyncio.to_thread(
        id_token.verify_oauth2_token,
        tokens["id_token"],
        GoogleRequest(),
        settings.google_ios_client_id,
    )

    creds_data = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": _GOOGLE_TOKEN_URI,
        "client_id": settings.google_ios_client_id,
        "client_secret": None,
        "scopes": (tokens.get("scope") or "").split(),
    }
    return creds_data, id_info["email"]


@router.post("/google/mobile", response_model=MobileAuthResponse)
async def google_mobile_auth(
    payload: MobileAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mobile sign-in: exchange PKCE code -> Gmail tokens (kept server-side, D4)
    -> find/create the User -> issue an app session JWT (D23)."""
    try:
        creds_data, email = await exchange_code_pkce(payload.code, payload.code_verifier)
    except Exception as e:
        # Log the real reason server-side (e.g. Google's invalid_grant /
        # redirect_uri_mismatch body); return a generic 400 to the client.
        reason = getattr(getattr(e, "response", None), "text", None) or repr(e)
        _log.warning("mobile auth exchange failed: %s", reason)
        raise HTTPException(status_code=400, detail="Invalid authorization code")

    user = await get_or_create_user(db, email)
    # Token store keyed by the user's normalized email so Gmail lookups align.
    store_token(user.email, creds_data)

    token = create_access_token(subject=str(user.id), email=user.email)

    return MobileAuthResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=MobileAuthUser(id=str(user.id), email=user.email),
    )
