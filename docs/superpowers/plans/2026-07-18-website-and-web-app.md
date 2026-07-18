# Website + Desktop Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship (1) a static Mama Coral landing site with the privacy policy (E0 prerequisite) and (2) the existing Flutter app running in desktop browsers with Google sign-in — per spec `docs/superpowers/specs/2026-07-18-website-and-web-app-design.md`.

**Architecture:** Static HTML landing under `website/` (Vercel, zero JS). The app is the existing Flutter codebase compiled for web: a `kIsWeb` auth branch runs OAuth PKCE against the existing **web** OAuth client (redirect to `<origin>/auth.html`), and a new backend endpoint `POST /api/v1/auth/google/web` exchanges the code (web client id + secret) and returns the same app JWT with a shorter TTL. CORS locked to configured origins. Web ships without push and without ads.

**Tech Stack:** FastAPI + httpx + PyJWT (backend, TDD with pytest from `backend/`); Flutter 3.44 / flutter_web_auth_2 (frontend, mocktail tests); plain HTML/CSS (landing).

## Global Constraints

- Backend commands run from `backend/`; use `.venv/bin/python -m pytest`. Frontend commands run from `frontend/`.
- TDD: failing test first, watch it fail, minimal code, watch it pass. Conventional Commits, one commit per task minimum.
- Types-only logging: never log tokens, email bodies, or exception text that can echo request content — log `type(exc).__name__` / fixed enum codes only.
- THE FIREWALL (D19): no content-derived value may reach anything ad-related. The ad SDK stays confined to `lib/ads/`. `scripts/firewall-guard.sh` runs on every edit/commit — if it blocks, fix the code, never the guard.
- Gmail tokens stay server-side (D4); the browser holds only the app JWT.
- Brand: Mama Coral `#F27E63`, cream background `#FFF8F4`, headings feel rounded/warm (system font stack on the landing site — no webfont downloads).
- Landing site: zero JavaScript, zero analytics/trackers.
- New backend env vars must be added to `backend/.env.example` in the same task that introduces them.
- The security-auditor subagent must review Task 3 (touches token flows) before it is considered done.

---

### Task 1: Static landing site (`website/`)

**Files:**
- Create: `website/index.html`
- Create: `website/privacy.html`
- Create: `website/style.css`
- Create: `website/assets/logo.png` (copied from `frontend/assets/brand/splash_logo_1024.png`)
- Create: `website/vercel.json`
- Modify: `docs/privacy-policy.md` (add a pointer line at the top; content stays until the site is live)

**Interfaces:**
- Consumes: `docs/privacy-policy.md` (existing policy text), `frontend/assets/brand/splash_logo_1024.png` (logo master).
- Produces: a self-contained static site; Vercel project can point at `website/` with no build step. Nothing else depends on this task.

- [ ] **Step 1: Copy the logo asset**

```bash
mkdir -p website/assets
cp frontend/assets/brand/splash_logo_1024.png website/assets/logo.png
```

- [ ] **Step 2: Write `website/style.css`**

```css
/* Mamaflow landing — Mama Coral brand. No JS, no trackers, by design. */
:root {
  --coral: #F27E63;
  --coral-dark: #D96A50;
  --cream: #FFF8F4;
  --ink: #3D2C29;
  --ink-soft: #7A6660;
}
* { box-sizing: border-box; margin: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--cream);
  color: var(--ink);
  line-height: 1.6;
}
main { max-width: 720px; margin: 0 auto; padding: 3rem 1.5rem 4rem; }
header.hero { text-align: center; padding-top: 2rem; }
header.hero img { width: 96px; height: 96px; }
h1 { font-size: 2.4rem; color: var(--coral); margin: 0.5rem 0 0.25rem; }
.tagline { font-size: 1.25rem; color: var(--ink-soft); margin-bottom: 2rem; }
h2 { color: var(--coral-dark); margin: 2rem 0 0.5rem; }
p { margin: 0.75rem 0; }
ul.trust { list-style: none; padding: 0; margin: 1.5rem 0; }
ul.trust li { padding-left: 1.6rem; position: relative; margin: 0.5rem 0; }
ul.trust li::before { content: "\2764"; color: var(--coral); position: absolute; left: 0; }
.cta {
  display: inline-block; background: var(--coral); color: #fff;
  padding: 0.8rem 2rem; border-radius: 999px; text-decoration: none;
  font-weight: 600; margin: 1rem 0.5rem 0 0;
}
.cta.secondary { background: transparent; color: var(--coral); border: 2px solid var(--coral); }
footer { text-align: center; color: var(--ink-soft); font-size: 0.85rem; padding: 2rem 1rem; }
footer a { color: var(--coral-dark); }
```

- [ ] **Step 3: Write `website/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Mamaflow reads the school and activity emails you never have time for and turns them into a family calendar and to-do list.">
  <title>Mamaflow — your family inbox, sorted</title>
  <meta name="theme-color" content="#F27E63">
  <link rel="stylesheet" href="style.css">
  <link rel="icon" href="assets/logo.png">
</head>
<body>
  <main>
    <header class="hero">
      <img src="assets/logo.png" alt="Mamaflow logo">
      <h1>Mamaflow</h1>
      <p class="tagline">School emails in. Family calendar out.</p>
    </header>
    <p>Mamaflow connects to your Gmail, finds the school newsletters, appointment
    reminders and activity sign-ups buried in your inbox, and turns them into a
    clean agenda and to-do list — so nothing about your kids' week falls through
    the cracks.</p>
    <ul class="trust">
      <li>We never store your emails — only the events we extract.</li>
      <li>Financial and sensitive senders are filtered out before anything is read.</li>
      <li>Your email content is never used for advertising. Ever.</li>
    </ul>
    <p>
      <a class="cta" href="https://app.example.invalid">Open Mamaflow in your browser</a>
      <a class="cta secondary" href="privacy.html">Privacy policy</a>
    </p>
    <p class="tagline">iOS and Android apps: coming to the stores soon.</p>
  </main>
  <footer>
    <p>&copy; 2026 Mamaflow · <a href="privacy.html">Privacy</a></p>
  </footer>
</body>
</html>
```

The `https://app.example.invalid` CTA href is a deliberate sentinel: replace it with the real
web-app URL in Task 6 (deploy docs) — grep for `example.invalid` then.

- [ ] **Step 4: Write `website/privacy.html`**

Use this shell, then convert the full text of `docs/privacy-policy.md` to HTML inside
`<main>` (headings → `h2`, tables → `<table>`, lists → `<ul>`). Do not summarize or
reword the policy — transcribe it.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy — Mamaflow</title>
  <meta name="theme-color" content="#F27E63">
  <link rel="stylesheet" href="style.css">
  <link rel="icon" href="assets/logo.png">
</head>
<body>
  <main>
    <header class="hero">
      <img src="assets/logo.png" alt="Mamaflow logo">
      <h1>Privacy Policy</h1>
    </header>
    <!-- docs/privacy-policy.md content, transcribed to HTML -->
  </main>
  <footer><p><a href="index.html">&larr; Mamaflow home</a></p></footer>
</body>
</html>
```

Then add this line at the very top of `docs/privacy-policy.md`:

```markdown
> Canonical public copy: `website/privacy.html` (served at /privacy on the production domain).
> Keep both in sync — edit here first, then re-transcribe.
```

- [ ] **Step 5: Write `website/vercel.json`**

```json
{
  "cleanUrls": true,
  "trailingSlash": false
}
```

- [ ] **Step 6: Verify — serve locally and check**

```bash
cd website && python3 -m http.server 8080 &
sleep 1
curl -s localhost:8080/ | grep -c "<script" ; curl -s localhost:8080/privacy.html | grep -c "<script"
curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/assets/logo.png
kill %1
```

Expected: both grep counts `0` (no JS anywhere), logo returns `200`. Also open
`http://localhost:8080` in a browser and eyeball the coral branding.

- [ ] **Step 7: Commit**

```bash
git add website/ docs/privacy-policy.md
git commit -m "feat(website): static Mama Coral landing + privacy policy pages"
```

---

### Task 2: Backend — web settings + CORS

**Files:**
- Modify: `backend/api/config/settings.py` (add two fields + a property, after `auto_sync_enabled` around line 46)
- Modify: `backend/api/main.py` (add `configure_cors`)
- Modify: `backend/.env.example`
- Test: `backend/tests/test_cors.py` (new)

**Interfaces:**
- Produces: `settings.web_app_origins: str` (env `WEB_APP_ORIGINS`, comma-separated, default `""`), `settings.web_origins_list: list[str]`, `settings.web_token_expire_minutes: int` (env `WEB_TOKEN_EXPIRE_MINUTES`, default `10080`), and `configure_cors(app)` in `api.main`. Task 3 consumes `web_origins_list` and `web_token_expire_minutes`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_cors.py`:

```python
"""Web CORS wiring (spec 2026-07-18): API callable from the configured web-app
origin(s) only; no origins configured (today's default) = no CORS headers."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.config.settings import Settings, settings
from api.main import configure_cors


def test_web_origins_list_parses_and_strips():
    s = Settings(web_app_origins=" https://app.mamaflow.example , https://mamaflow-app.vercel.app ,")
    assert s.web_origins_list == [
        "https://app.mamaflow.example",
        "https://mamaflow-app.vercel.app",
    ]
    assert Settings(web_app_origins="").web_origins_list == []


def test_web_token_ttl_defaults_to_seven_days():
    assert Settings().web_token_expire_minutes == 7 * 24 * 60


@pytest.mark.asyncio
async def test_preflight_allowed_for_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "https://app.mamaflow.example")
    app = FastAPI()
    configure_cors(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.options("/ping", headers={
            "Origin": "https://app.mamaflow.example",
            "Access-Control-Request-Method": "GET",
        })
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://app.mamaflow.example"


@pytest.mark.asyncio
async def test_no_origins_configured_means_no_cors(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "")
    app = FastAPI()
    configure_cors(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cors.py -v`
Expected: FAIL — `Settings` has no attribute `web_app_origins`; `configure_cors` import error.

- [ ] **Step 3: Implement settings fields** — in `backend/api/config/settings.py`, after the `auto_sync_enabled` field:

```python
    # Desktop web app (spec 2026-07-18). Comma-separated https origins allowed
    # to call the API from a browser; empty (default) = no CORS headers at all.
    web_app_origins: str = ""
    # Web sessions are shorter than mobile's 30 days (D31): browser storage is
    # more exposed than a device keychain. Default 7 days.
    web_token_expire_minutes: int = 7 * 24 * 60

    @property
    def web_origins_list(self) -> list[str]:
        return [o.strip() for o in self.web_app_origins.split(",") if o.strip()]
```

- [ ] **Step 4: Implement `configure_cors`** — in `backend/api/main.py`, add the import and function; call it right after `app = FastAPI(...)`:

```python
from fastapi.middleware.cors import CORSMiddleware

from api.config.settings import settings


def configure_cors(app: FastAPI) -> None:
    """Allow browser calls from the configured web-app origin(s) only.

    No origins configured (the default) adds no middleware — non-web deploys
    keep today's behavior of emitting no CORS headers at all."""
    origins = settings.web_origins_list
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
```

```python
app = FastAPI(title="Mamaflow API", version="0.1.0", lifespan=lifespan)
configure_cors(app)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cors.py -v` then the whole suite `.venv/bin/python -m pytest -q`
Expected: all PASS (175 existing + 4 new).

- [ ] **Step 6: Document the env vars** — append to `backend/.env.example`:

```bash
# Desktop web app (spec 2026-07-18)
# Comma-separated browser origins allowed via CORS; empty = web app disabled (no CORS headers).
WEB_APP_ORIGINS=
# Browser session JWT lifetime in minutes (default 10080 = 7 days; mobile stays 30 days, D31).
WEB_TOKEN_EXPIRE_MINUTES=10080
```

- [ ] **Step 7: Commit**

```bash
git add backend/api/config/settings.py backend/api/main.py backend/.env.example backend/tests/test_cors.py
git commit -m "feat(backend): WEB_APP_ORIGINS CORS wiring + web session TTL setting"
```

---

### Task 3: Backend — `POST /api/v1/auth/google/web`

**Files:**
- Modify: `backend/api/auth/oauth.py` (add `web_redirect_uri`, `exchange_code_web`, `google_web_auth` endpoint — place after the mobile section)
- Test: `backend/tests/test_web_app_auth.py` (new)

**Interfaces:**
- Consumes: `settings.web_origins_list`, `settings.web_token_expire_minutes` (Task 2); existing `MobileAuthRequest/Response`, `get_or_create_user`, `store_token`, `create_access_token(subject, email, expires_minutes=...)`, `_GOOGLE_TOKEN_URI`.
- Produces: `POST /api/v1/auth/google/web` — request `{code, code_verifier}`, response `MobileAuthResponse` shape. Task 4's `AuthService` posts here when `kIsWeb`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_web_app_auth.py`:

```python
"""POST /api/v1/auth/google/web (spec 2026-07-18): browser PKCE exchange against
the WEB OAuth client -> same app JWT, shorter TTL. Google is never hit live."""

import pytest

from api.auth import oauth
from api.auth.jwt import decode_access_token
from api.auth.token_store import get_token
from api.config.settings import settings

FAKE_CREDS = {
    "token": "ya29.web-access",
    "refresh_token": "1//web-refresh",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "web-client-id",
    "client_secret": "web-secret",
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
}
BODY = {"code": "web-code-123", "code_verifier": "web-verifier-xyz"}


def test_web_redirect_uri_derived_from_first_origin(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "https://app.mamaflow.example, https://x.vercel.app")
    assert oauth.web_redirect_uri() == "https://app.mamaflow.example/auth.html"


def test_web_redirect_uri_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "")
    with pytest.raises(ValueError):
        oauth.web_redirect_uri()


async def test_valid_code_returns_jwt_with_web_ttl(client, db, monkeypatch):
    async def _fake_exchange(code, code_verifier):
        assert code == "web-code-123" and code_verifier == "web-verifier-xyz"
        return FAKE_CREDS, "Parent@Example.com"

    monkeypatch.setattr(oauth, "exchange_code_web", _fake_exchange)

    resp = await client.post("/api/v1/auth/google/web", json=BODY)

    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == settings.web_token_expire_minutes * 60
    assert body["user"]["email"] == "parent@example.com"
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == body["user"]["id"]


async def test_gmail_tokens_stored_server_side(client, monkeypatch):
    async def _fake_exchange(code, code_verifier):
        return FAKE_CREDS, "parent@example.com"

    monkeypatch.setattr(oauth, "exchange_code_web", _fake_exchange)
    await client.post("/api/v1/auth/google/web", json=BODY)
    stored = get_token("parent@example.com")
    assert stored is not None and stored["refresh_token"] == "1//web-refresh"


async def test_web_auth_stores_token_off_the_event_loop(client, monkeypatch):
    import threading

    async def _fake_exchange(code, code_verifier):
        return FAKE_CREDS, "parent@example.com"

    monkeypatch.setattr(oauth, "exchange_code_web", _fake_exchange)
    store_threads = []
    monkeypatch.setattr(
        oauth, "store_token",
        lambda email, data: store_threads.append(threading.get_ident()),
    )

    resp = await client.post("/api/v1/auth/google/web", json=BODY)

    assert resp.status_code == 200
    assert store_threads and store_threads[0] != threading.get_ident()


async def test_invalid_code_returns_400_sanitized(client, monkeypatch):
    async def _boom(code, code_verifier):
        raise ValueError("google exploded")

    monkeypatch.setattr(oauth, "exchange_code_web", _boom)
    resp = await client.post("/api/v1/auth/google/web", json=BODY)
    assert resp.status_code == 400
    assert "exploded" not in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_app_auth.py -v`
Expected: FAIL — `oauth` has no attribute `web_redirect_uri` / `exchange_code_web`; POST returns 404.

- [ ] **Step 3: Implement** — append to `backend/api/auth/oauth.py` after `google_mobile_auth`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_app_auth.py -v` then `.venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Security audit (required)**

Dispatch the `security-auditor` subagent on the working-tree diff (token flow touched). It must
confirm: tokens only via `store_token`, no token/PII in logs, redirect URI server-derived,
firewall untouched. Fix anything it flags before committing.

- [ ] **Step 6: Commit**

```bash
git add backend/api/auth/oauth.py backend/tests/test_web_app_auth.py
git commit -m "feat(backend): browser sign-in — POST /auth/google/web (web OAuth client, web TTL)"
```

---

### Task 4: Frontend — web target + browser auth branch

**Files:**
- Create: `frontend/web/` (via `flutter create --platforms web .`), then customize `frontend/web/index.html`
- Create: `frontend/web/auth.html`
- Modify: `frontend/lib/auth/google_auth_codes.dart` (add `BrowserPkceCodes`; hoist the two PKCE helpers to top-level)
- Modify: `frontend/lib/auth/auth_service.dart` (injectable exchange path)
- Modify: `frontend/lib/core/providers.dart` (kIsWeb wiring)
- Test: `frontend/test/auth/auth_service_test.dart` (add one test), `frontend/test/auth/google_auth_codes_test.dart` (add browser-flow tests)

**Interfaces:**
- Consumes: `POST /api/v1/auth/google/web` (Task 3); existing `GoogleAuthCodes` / `OAuthCodeResult` / `WebAuthenticate` types; `AuthService(api, tokenStore, google)`.
- Produces: `BrowserPkceCodes({required String webClientId, required String origin, WebAuthenticate? authenticate})` implementing `GoogleAuthCodes`; `AuthService` gains named param `exchangePath` (default `'/api/v1/auth/google/mobile'`); new dart-define `GOOGLE_WEB_CLIENT_ID`.

- [ ] **Step 1: Scaffold the web target**

```bash
cd frontend && flutter create --platforms web .
```

Then edit the generated `frontend/web/index.html`: set `<title>Mamaflow</title>` and add
`<meta name="theme-color" content="#F27E63">` in `<head>`. Leave the rest generated.

- [ ] **Step 2: Write `frontend/web/auth.html`** (the flutter_web_auth_2 web callback contract):

```html
<!DOCTYPE html>
<title>Signing in…</title>
<p>Sign-in complete. You can close this window.</p>
<script>
  window.opener.postMessage({
    'flutter-web-auth-2': window.location.href
  }, window.location.origin);
  window.close();
</script>
```

(This page is inside the app bundle, not the landing site — the zero-JS rule applies to
`website/` only.)

- [ ] **Step 3: Write the failing frontend tests**

Add to `frontend/test/auth/auth_service_test.dart` (reuses its existing `_MockApi`,
`_MockTokenStore`, `_FakeGoogle`, `_fakeCode`):

```dart
  test('posts to the injected exchange path (web uses /auth/google/web)', () async {
    final api = _MockApi();
    final store = _MockTokenStore();
    when(() => api.postJson(any(), any())).thenAnswer((_) async => {
          'access_token': 'JWT456',
          'user': {'id': 'u2', 'email': 'p@example.com'},
        });
    when(() => store.saveJwt(any())).thenAnswer((_) async {});
    final auth = AuthService(api, store, _FakeGoogle(_fakeCode),
        exchangePath: '/api/v1/auth/google/web');

    await auth.signInWithGoogle();

    final captured = verify(() => api.postJson(captureAny(), any())).captured;
    expect(captured[0], '/api/v1/auth/google/web');
  });
```

Add to `frontend/test/auth/google_auth_codes_test.dart` (follow that file's existing
fake-`WebAuthenticate` pattern — it injects a function capturing the `url` and returning a
crafted callback URL):

```dart
  group('BrowserPkceCodes', () {
    test('builds the auth URL against the web client and origin redirect', () async {
      String? capturedUrl;
      Future<String> fake({
        required String url,
        required String callbackUrlScheme,
        required FlutterWebAuth2Options options,
      }) async {
        capturedUrl = url;
        final state = Uri.parse(url).queryParameters['state']!;
        return 'https://app.mamaflow.example/auth.html?code=C1&state=$state';
      }

      final codes = BrowserPkceCodes(
        webClientId: 'web-id.apps.googleusercontent.com',
        origin: 'https://app.mamaflow.example',
        authenticate: fake,
      );

      final result = await codes.obtainAuthorizationCode();

      final q = Uri.parse(capturedUrl!).queryParameters;
      expect(q['client_id'], 'web-id.apps.googleusercontent.com');
      expect(q['redirect_uri'], 'https://app.mamaflow.example/auth.html');
      expect(q['code_challenge_method'], 'S256');
      expect(result!.code, 'C1');
    });

    test('empty web client id fails loudly', () {
      final codes = BrowserPkceCodes(webClientId: '', origin: 'https://x');
      expect(codes.obtainAuthorizationCode, throwsStateError);
    });

    test('state mismatch drops the code', () async {
      Future<String> fake({
        required String url,
        required String callbackUrlScheme,
        required FlutterWebAuth2Options options,
      }) async =>
          'https://app.mamaflow.example/auth.html?code=C1&state=WRONG';
      final codes = BrowserPkceCodes(
          webClientId: 'id', origin: 'https://app.mamaflow.example', authenticate: fake);
      expect(codes.obtainAuthorizationCode, throwsStateError);
    });
  });
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd frontend && flutter test test/auth`
Expected: FAIL — `BrowserPkceCodes` undefined; `AuthService` has no `exchangePath`.

- [ ] **Step 5: Implement `BrowserPkceCodes`** — in `frontend/lib/auth/google_auth_codes.dart`:

First hoist the two static helpers out of `WebAuthPkceCodes` to top-level (same file, same
bodies) so both implementations share them:

```dart
String _randomVerifier() {
  const chars =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  final rand = Random.secure();
  return List.generate(64, (_) => chars[rand.nextInt(chars.length)]).join();
}

String _s256Challenge(String verifier) {
  final digest = sha256.convert(ascii.encode(verifier));
  return base64UrlEncode(digest.bytes).replaceAll('=', '');
}
```

(Delete the identical static methods from `WebAuthPkceCodes`; its call sites keep the same
names.) Then add:

```dart
/// Browser (desktop web) implementation: the same OAuth 2.0 auth-code + PKCE
/// flow, but against the WEB OAuth client with an https redirect back to this
/// app origin's auth.html (which posts the callback URL to the opener —
/// flutter_web_auth_2's web contract). The backend exchanges the code with the
/// web client's secret; Gmail tokens never touch the browser (D4).
class BrowserPkceCodes implements GoogleAuthCodes {
  BrowserPkceCodes({
    required String webClientId,
    required String origin,
    WebAuthenticate? authenticate,
  })  : _clientId = webClientId,
        _origin = origin,
        _authenticate = authenticate ?? _pluginAuthenticate;

  final String _clientId;
  final String _origin;
  final WebAuthenticate _authenticate;

  static Future<String> _pluginAuthenticate({
    required String url,
    required String callbackUrlScheme,
    required FlutterWebAuth2Options options,
  }) =>
      FlutterWebAuth2.authenticate(
          url: url, callbackUrlScheme: callbackUrlScheme, options: options);

  static const _scopes =
      'openid email https://www.googleapis.com/auth/gmail.readonly';

  @override
  Future<OAuthCodeResult?> obtainAuthorizationCode() async {
    if (_clientId.isEmpty) {
      throw StateError(
        'GOOGLE_WEB_CLIENT_ID is empty. Build with: flutter build web '
        '--dart-define=GOOGLE_WEB_CLIENT_ID=<web client id>.',
      );
    }

    final verifier = _randomVerifier();
    final challenge = _s256Challenge(verifier);
    final redirectUri = '$_origin/auth.html';
    final state = _randomVerifier();

    final url = Uri.https('accounts.google.com', '/o/oauth2/v2/auth', {
      'client_id': _clientId,
      'redirect_uri': redirectUri,
      'response_type': 'code',
      'scope': _scopes,
      'access_type': 'offline',
      'prompt': 'consent',
      'code_challenge': challenge,
      'code_challenge_method': 'S256',
      'state': state,
    }).toString();

    final String result;
    try {
      result = await _authenticate(
        url: url,
        // On web the plugin matches the callback by the redirect page's
        // postMessage, not a custom scheme; 'https' is the documented value.
        callbackUrlScheme: 'https',
        options: const FlutterWebAuth2Options(),
      );
    } on PlatformException catch (e) {
      if (e.code == 'CANCELED') return null;
      rethrow;
    }

    final params = Uri.parse(result).queryParameters;
    if (params['state'] != state) {
      throw StateError('OAuth callback state mismatch — dropping the code.');
    }
    final code = params['code'];
    if (code == null) return null;
    return OAuthCodeResult(code: code, codeVerifier: verifier);
  }

  @override
  Future<void> signOut() async {}
}
```

- [ ] **Step 6: Implement the `AuthService` exchange path** — in `frontend/lib/auth/auth_service.dart`:

```dart
class AuthService {
  AuthService(this._api, this._tokenStore, this._google,
      {String exchangePath = '/api/v1/auth/google/mobile'})
      : _exchangePath = exchangePath;

  final ApiClient _api;
  final TokenStore _tokenStore;
  final GoogleAuthCodes _google;
  final String _exchangePath;
```

and in `signInWithGoogle()` replace the literal path:

```dart
    final resp = await _api.postJson(
      _exchangePath,
      {'code': result.code, 'code_verifier': result.codeVerifier},
    );
```

- [ ] **Step 7: Wire providers** — in `frontend/lib/core/providers.dart`, change the
`kReleaseMode` import line and add the web wiring:

```dart
import 'package:flutter/foundation.dart' show kIsWeb, kReleaseMode;
```

```dart
// The WEB OAuth client id for the browser flow (spec 2026-07-18); same GCP
// client the backend exchanges with. --dart-define=GOOGLE_WEB_CLIENT_ID=...
const _webClientId =
    String.fromEnvironment('GOOGLE_WEB_CLIENT_ID', defaultValue: '');

final googleAuthCodesProvider = Provider<GoogleAuthCodes>(
  (ref) => kIsWeb
      ? BrowserPkceCodes(webClientId: _webClientId, origin: Uri.base.origin)
      : WebAuthPkceCodes(iosClientId: _iosClientId),
);

final authServiceProvider = Provider<AuthService>((ref) => AuthService(
      ref.watch(apiClientProvider),
      ref.watch(tokenStoreProvider),
      ref.watch(googleAuthCodesProvider),
      exchangePath:
          kIsWeb ? '/api/v1/auth/google/web' : '/api/v1/auth/google/mobile',
    ));
```

(Replace the existing `googleAuthCodesProvider`/`authServiceProvider` definitions.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd frontend && flutter test && flutter analyze`
Expected: all PASS (existing suite + new), analyze clean.

- [ ] **Step 9: Commit**

```bash
git add frontend/web frontend/lib/auth frontend/lib/core/providers.dart frontend/test/auth
git commit -m "feat(frontend): web target + browser Google sign-in (BrowserPkceCodes, web exchange path)"
```

---

### Task 5: Frontend — web-compat guards (push, ads, layout) + first web build

**Files:**
- Modify: `frontend/lib/push/push_service.dart` (drop `dart:io`; `kIsWeb` no-op)
- Create: `frontend/lib/ads/ad_config_stub.dart`, `frontend/lib/ads/ad_banner_slot_stub.dart`
- Modify: `frontend/lib/main.dart`, `frontend/lib/ui/home_shell.dart` (conditional imports)
- Modify: `frontend/lib/app.dart` (centered max-width shell)
- Test: `frontend/test/push/` (extend existing push test file with the web-guard test)

**Interfaces:**
- Consumes: `AdConfig.initialize()` and `const AdBannerSlot()` signatures (stubs must match); `PushService.start()`.
- Produces: a codebase that compiles with `flutter build web`; no behavior change on mobile.

- [ ] **Step 1: Write the failing web-guard test** — add to the existing PushService test file in `frontend/test/push/` (it already constructs `PushService` with an injected mock `FirebaseMessaging`); this asserts the platform string no longer comes from `dart:io`:

```dart
  test('platform string uses defaultTargetPlatform, not dart:io', () {
    // Compile-time guard: importing dart:io breaks `flutter build web`.
    // This test just pins the import change; the real check is Step 6's build.
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    expect(platformLabel(), 'ios');
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    expect(platformLabel(), 'android');
  });
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && flutter test test/push`
Expected: FAIL — `platformLabel` undefined.

- [ ] **Step 3: Implement the push web guard** — in `frontend/lib/push/push_service.dart`:

Replace `import 'dart:io' show Platform;` with:

```dart
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;
```

Add a top-level helper and use it in `_register`:

```dart
/// 'ios' | 'android' for the device registration row. Top-level so it is
/// testable without Firebase.
String platformLabel() =>
    defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
```

```dart
      await _registrar.register(
        fcmToken: token,
        platform: platformLabel(),
      );
```

And make `start()` a web no-op (first lines):

```dart
  Future<void> start() async {
    // Web ships without push (spec 2026-07-18): no FCM-web service worker.
    // Reminders keep arriving on the phone.
    if (kIsWeb) return;
    if (_started) return;
```

- [ ] **Step 4: Ads stubs (web ships ad-free)** — create `frontend/lib/ads/ad_config_stub.dart`:

```dart
/// Web stub (spec 2026-07-18): google_mobile_ads has no web support and web
/// ships ad-free. Same surface as AdConfig so main.dart compiles unchanged.
/// FIREWALL: lives in lib/ads/ per the isolation rule; contains no app/content
/// imports.
class AdConfig {
  static Future<void> initialize() async {}
}
```

and `frontend/lib/ads/ad_banner_slot_stub.dart`:

```dart
import 'package:flutter/widgets.dart';

/// Web stub (spec 2026-07-18): renders nothing; web ships ad-free.
class AdBannerSlot extends StatelessWidget {
  const AdBannerSlot({super.key});

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
```

Switch the two import sites to conditional imports — `frontend/lib/main.dart`:

```dart
import 'ads/ad_config.dart' if (dart.library.js_interop) 'ads/ad_config_stub.dart';
```

`frontend/lib/ui/home_shell.dart`:

```dart
import '../ads/ad_banner_slot.dart'
    if (dart.library.js_interop) '../ads/ad_banner_slot_stub.dart';
```

- [ ] **Step 5: Centered desktop shell** — in `frontend/lib/app.dart`, add a `builder` to
`MaterialApp.router` (before `routerConfig`):

```dart
      // Desktop/web: phone-designed screens stay readable in a centered column
      // (~phone width). No-op on phones, whose width is already below the cap.
      builder: (context, child) => ColoredBox(
        color: Theme.of(context).colorScheme.surface,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: child ?? const SizedBox.shrink(),
          ),
        ),
      ),
```

- [ ] **Step 6: Verify — tests, analyze, and the first web build**

```bash
cd frontend && flutter test && flutter analyze && flutter build web
bash ../scripts/firewall-guard.sh
```

Expected: tests pass, analyze clean, `flutter build web` succeeds (this is the step that
catches any remaining `dart:io`/plugin web-compile breakage — if it fails, fix the reported
import the same stub/conditional way), guard exit 0.

- [ ] **Step 7: Smoke-run in a browser against the local backend**

```bash
cd backend && .venv/bin/python -m uvicorn api.main:app --port 8000 &
cd frontend && flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000 --dart-define=GOOGLE_WEB_CLIENT_ID=<web client id from backend/.env GOOGLE_CLIENT_ID>
```

Backend `.env` needs `WEB_APP_ORIGINS=http://localhost:<the chrome port flutter prints>` for
CORS + redirect derivation, and the Google console web client needs
`http://localhost:<port>/auth.html` as an authorized redirect URI for a full sign-in
round-trip. If console access isn't available in this session, verify to the consent screen
(URL is built, popup opens) and record the remaining manual step in HANDOFF.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib frontend/test
git commit -m "feat(frontend): web-compat — push no-op on web, ad stubs, centered desktop shell"
```

---

### Task 6: CI web build + deploy/domain docs + project memory

**Files:**
- Modify: `.github/workflows/ci.yml` (frontend job)
- Create: `docs/website-deploy.md`
- Modify: `website/index.html` (real app URL once known — or leave the sentinel + note)
- Modify: `HANDOFF.md`, `DECISIONS.md`

**Interfaces:**
- Consumes: everything above. Produces: no code interfaces — CI/docs/memory only.

- [ ] **Step 1: Add the web build to CI** — in `.github/workflows/ci.yml`, frontend job, after `- run: flutter test`:

```yaml
      - run: flutter build web
```

- [ ] **Step 2: Write `docs/website-deploy.md`**

```markdown
# Website + web app deploy (spec 2026-07-18)

## Vercel projects (no domain needed)
1. **Landing:** New Project → import this repo → Root Directory `website/` →
   Framework "Other", no build command, output dir `.` → deploy.
   URL: https://<project>.vercel.app
2. **Web app:** built by CI/local (`cd frontend && flutter build web
   --dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app
   --dart-define=GOOGLE_WEB_CLIENT_ID=<GOOGLE_CLIENT_ID value>`), then
   `npx vercel deploy frontend/build/web` (a second Vercel project). Automating
   this deploy in CI is a follow-up once the domain exists.

## Backend + Google console (after the app URL exists)
- Railway: set `WEB_APP_ORIGINS=https://<app url>` (comma-separated if several).
- Google console → the WEB OAuth client (same id as backend GOOGLE_CLIENT_ID) →
  Authorized redirect URIs → add `https://<app url>/auth.html`.
- Replace the `example.invalid` CTA link in `website/index.html` with the app URL.

## Domain-arrival checklist (~30 min)
1. Buy domain; attach apex/www to the landing Vercel project, `app.` to the web
   app project (Vercel → Domains).
2. Google console: add `https://app.<domain>/auth.html` redirect URI.
3. Railway: update `WEB_APP_ORIGINS` to the new app origin.
4. Update the CTA link in `website/index.html`.
5. At ad launch only: `website/app-ads.txt` with the AdMob publisher id.
```

- [ ] **Step 3: Record the decision** — append to the DECISIONS.md table as the next `Dn`
(D35 if unchanged):

```markdown
| D35 | Web sessions: same app JWT via the existing WEB OAuth client, TTL 7 days (`WEB_TOKEN_EXPIRE_MINUTES=10080`) | locked | Spec 2026-07-18 (approach A): browser runs PKCE against the web client; backend exchanges with its secret; Gmail tokens stay server-side (D4). Browser storage is more exposed than a device keychain, so web TTL is 7 days vs mobile's 30 (D31). Web ships without push and without ads; `lib/ads/` stubs keep the web build compiling with the firewall isolation intact (D19). |
```

- [ ] **Step 4: Update HANDOFF.md** — add an update block (after the latest one) summarizing:
landing site live at the Vercel URL (or "ready to deploy"), web app tasks done, the two USER
steps (Vercel project creation + Google-console redirect URI), and the domain-arrival
checklist pointer to `docs/website-deploy.md`.

- [ ] **Step 5: Full verification + commit**

```bash
cd backend && .venv/bin/python -m pytest -q && cd ../frontend && flutter test && flutter analyze && cd .. && bash scripts/firewall-guard.sh
git add .github/workflows/ci.yml docs/website-deploy.md website/index.html HANDOFF.md DECISIONS.md
git commit -m "ci+docs: web build in CI, deploy/domain runbook, D35 web session decision"
```

Expected: backend suite green, frontend green, analyze clean, guard 0.
