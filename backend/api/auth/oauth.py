import asyncio
import datetime
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

# Phase 0: in-memory PKCE state, same pattern as token_store. Bounded because
# abandoned logins (browser closed before the callback) never remove entries.
_pending_states: dict[str, str] = {}
_MAX_PENDING_STATES = 1000


def _remember_state(state: str, verifier: str) -> None:
    while len(_pending_states) >= _MAX_PENDING_STATES:
        _pending_states.pop(next(iter(_pending_states)))  # oldest first
    _pending_states[state] = verifier

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
    _remember_state(state, flow.code_verifier)
    return RedirectResponse(auth_url)


class WebCallbackResponse(BaseModel):
    message: str
    email: str


@router.get("/google/callback", response_model=WebCallbackResponse)
async def google_callback(request: Request):
    if request.query_params.get("error"):
        # The user denied consent (or Google reported an OAuth error code).
        raise HTTPException(status_code=400, detail="Google sign-in was not completed")

    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing OAuth state or code")

    verifier = _pending_states.pop(state, None)
    if verifier is None:
        # Replay, or the in-memory state store was lost to a restart mid-login.
        raise HTTPException(
            status_code=400, detail="Sign-in session expired — start again"
        )

    flow = _build_flow()
    flow.code_verifier = verifier

    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleRequest

    try:
        # Both make sync network calls (token exchange; Google's signing-cert
        # fetch) — run them off the event loop, as the mobile flow does.
        await asyncio.to_thread(flow.fetch_token, code=code)
        id_info = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            flow.credentials.id_token,
            GoogleRequest(),
            settings.google_client_id,
        )
    except Exception as exc:
        _log.warning("web oauth callback failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Google sign-in failed — try again")

    credentials = flow.credentials
    user_email = id_info["email"]

    # store_token is a blocking gRPC call on the secret-manager backend —
    # off the loop, like the Google calls above.
    await asyncio.to_thread(store_token, user_email, {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes),
    })

    return WebCallbackResponse(message="OAuth successful", email=user_email)


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

    # Stamp an absolute expiry so the token store knows when to refresh (the
    # mobile PKCE credential has no client_secret, so google-auth can't refresh
    # it — google_token.ensure_fresh does, keyed off this expiry).
    lifetime = int(tokens.get("expires_in", 3600))
    creds_data = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": _GOOGLE_TOKEN_URI,
        "client_id": settings.google_ios_client_id,
        "client_secret": None,
        "scopes": (tokens.get("scope") or "").split(),
        "expiry": (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=lifetime)
        ).isoformat(),
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
        # Types-only logging convention: Google's OAuth error *code* (a fixed
        # enum like invalid_grant) is safe and diagnostic; the raw response
        # body can echo request-derived text and is never logged.
        reason = type(e).__name__
        response = getattr(e, "response", None)
        if response is not None:
            try:
                reason = f"{reason}/{response.json().get('error', '')}"
            except Exception:
                reason = f"{reason}/HTTP {response.status_code}"
        _log.warning("mobile auth exchange failed (%s)", reason)
        raise HTTPException(status_code=400, detail="Invalid authorization code")

    user = await get_or_create_user(db, email)
    # Token store keyed by the user's normalized email so Gmail lookups align.
    # Blocking gRPC on the secret-manager backend — off the loop.
    await asyncio.to_thread(store_token, user.email, creds_data)

    token = create_access_token(subject=str(user.id), email=user.email)

    return MobileAuthResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=MobileAuthUser(id=str(user.id), email=user.email),
    )


# --- Desktop web app auth (spec 2026-07-18) ---
#
# Same authorization-code + PKCE contract as mobile, but against the EXISTING
# web OAuth client (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET — the legacy dev-flow
# client) with an https redirect back to the app origin's auth.html. Gmail
# tokens stay server-side (D4); the browser gets the same app JWT with the
# shorter web TTL (browser storage is more exposed than a device keychain).


def web_redirect_uri() -> str:
    """Redirect URI for the browser flow, derived server-side from the FIRST
    configured web origin — never client-supplied (same defense-in-depth as
    mobile_redirect_uri). Raises when the web app isn't configured."""
    origins = settings.web_origins_list
    if not origins:
        raise ValueError("WEB_APP_ORIGINS is not configured")
    return f"{origins[0]}/auth.html"


async def exchange_code_web(code: str, code_verifier: str) -> tuple[dict, str]:
    """Exchange a browser PKCE authorization code for Gmail tokens; return
    (creds, email). Identity comes from the verified id_token, never the client."""
    import httpx
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(
            _GOOGLE_TOKEN_URI,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": web_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    resp.raise_for_status()
    tokens = resp.json()

    # verify_oauth2_token fetches Google's signing certs with a SYNC transport —
    # off the event loop, as everywhere else.
    id_info = await asyncio.to_thread(
        id_token.verify_oauth2_token,
        tokens["id_token"],
        GoogleRequest(),
        settings.google_client_id,
    )

    lifetime = int(tokens.get("expires_in", 3600))
    creds_data = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": _GOOGLE_TOKEN_URI,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes": (tokens.get("scope") or "").split(),
        # Absolute expiry so google_token.ensure_fresh refreshes on schedule
        # (same convention as the mobile flow).
        "expiry": (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=lifetime)
        ).isoformat(),
    }
    return creds_data, id_info["email"]


@router.post("/google/web", response_model=MobileAuthResponse)
async def google_web_auth(
    payload: MobileAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Browser sign-in: exchange PKCE code -> Gmail tokens (server-side, D4)
    -> find/create the User -> app session JWT with the web TTL."""
    try:
        creds_data, email = await exchange_code_web(payload.code, payload.code_verifier)
    except Exception as e:
        # Types-only logging; Google's fixed OAuth error code is safe/diagnostic.
        reason = type(e).__name__
        response = getattr(e, "response", None)
        if response is not None:
            try:
                reason = f"{reason}/{response.json().get('error', '')}"
            except Exception:
                reason = f"{reason}/HTTP {response.status_code}"
        _log.warning("web auth exchange failed (%s)", reason)
        raise HTTPException(status_code=400, detail="Invalid authorization code")

    user = await get_or_create_user(db, email)
    # Blocking gRPC on the secret-manager backend — off the loop.
    await asyncio.to_thread(store_token, user.email, creds_data)

    token = create_access_token(
        subject=str(user.id),
        email=user.email,
        expires_minutes=settings.web_token_expire_minutes,
    )
    return MobileAuthResponse(
        access_token=token,
        expires_in=settings.web_token_expire_minutes * 60,
        user=MobileAuthUser(id=str(user.id), email=user.email),
    )
