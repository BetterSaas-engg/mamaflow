from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from api.auth.token_store import store_token
from api.config.settings import settings

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
