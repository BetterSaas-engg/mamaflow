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


# --- Mobile auth (D23): google_sign_in serverAuthCode -> backend token exchange ---


class MobileAuthRequest(BaseModel):
    server_auth_code: str


class MobileAuthUser(BaseModel):
    id: str
    email: str


class MobileAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: MobileAuthUser


def exchange_server_auth_code(server_auth_code: str) -> tuple[dict, str]:
    """Exchange a mobile serverAuthCode for Gmail tokens; return (creds, email).

    Identity is taken from the verified id_token, never trusted from the client.
    Note: for the google_sign_in offline-code flow the redirect_uri Google expects
    can differ from the web callback (often '' / 'postmessage') — verify against the
    real iOS/Android client during integration.
    """
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    flow = _build_flow()
    flow.fetch_token(code=server_auth_code)
    credentials = flow.credentials

    id_info = id_token.verify_oauth2_token(
        credentials.id_token,
        GoogleRequest(),
        settings.google_client_id,
    )

    creds_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes),
    }
    return creds_data, id_info["email"]


@router.post("/google/mobile", response_model=MobileAuthResponse)
async def google_mobile_auth(
    payload: MobileAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mobile sign-in: exchange serverAuthCode -> Gmail tokens (kept server-side,
    D4) -> find/create the User -> issue an app session JWT (D23)."""
    try:
        creds_data, email = exchange_server_auth_code(payload.server_auth_code)
    except Exception:
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
