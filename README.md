# Mamaflow

Mamaflow reads a parent's email, extracts family events and to-dos (school, medical,
activities, playdates, admin) with Claude, and surfaces them as a calendar + task list in a
mobile app — without compromising the family's privacy.

**Stack:** FastAPI + PostgreSQL (Railway) · Claude API extraction · Microsoft Presidio PII
redaction · Flutter (iOS + Android; web later).

> Project rules live in [AGENTS.md](AGENTS.md) (the firewall is not negotiable), the decision
> log in [DECISIONS.md](DECISIONS.md), and the living build state in [HANDOFF.md](HANDOFF.md).

## How it works — the 4-layer pipeline

```
Gmail (metadata first)                       ← headers only; a blocked sender's body is NEVER fetched
  → Layer 1: sender blocklist (Postgres)     ← allowlist wins → blocklist blocks → unknown passes
  → Layer 2: PII redaction (Presidio, local) ← cards, bank/account numbers, SSN/SIN; runs on our server
  → Layer 3: injection wrap (nonce tags)     ← email body is data, never instructions
  → Layer 4: Claude extraction               ← the only point content leaves our infrastructure
  → structured items in Postgres             ← raw email bodies are never stored
```

Privacy invariants (enforced by `scripts/firewall-guard.sh` on every edit and commit):
no content-derived signal ever reaches ads (D19); OAuth tokens stay server-side (D4); raw
bodies are never persisted (D5).

## Repo layout

```
backend/    FastAPI app (package `api`), Alembic migrations, tests
frontend/   Flutter app (iOS + Android)
infra/      Terraform (GCP project, Gmail API)
scripts/    firewall guard (+ .githooks/, .claude/ AI config)
```

## Backend — run locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg        # Presidio's NLP model (first time only)

cp .env.example .env                            # then fill in real values
python -m alembic upgrade head                  # apply schema to the DB
python -m api.db.seed                           # seed default blocklist (idempotent)

uvicorn api.main:app --reload                   # http://localhost:8000  (Swagger at /docs)
python -m pytest                                # test suite
```

To serve a physical phone on your LAN: `uvicorn api.main:app --host 0.0.0.0 --port 8000`.

## Backend — deploy (Railway)

The backend ships as a Docker image (`backend/Dockerfile`; the spaCy model is baked at build
time, `start.sh` runs migrations then uvicorn on `$PORT`). One service, **single instance**
(the token-store cache is not multi-instance coherent yet — see HANDOFF).

Railway setup (once):
1. New service → *Deploy from GitHub repo* → pick this repo, branch `main` (or the feature
   branch while testing). Set **Root Directory = `backend`** so Railway finds the Dockerfile.
2. Variables (Service → Variables):
   - `DATABASE_URL` → reference the Railway Postgres (`${{Postgres.DATABASE_URL}}`)
   - `SECRET_KEY` → fresh 48+ char random (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `ENVIRONMENT=production` (enforces the strong-SECRET_KEY check)
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_IOS_CLIENT_ID`, `ANTHROPIC_API_KEY`
   - `TOKEN_STORE_BACKEND=secret-manager`, `GCP_PROJECT_ID=<project>`,
     `GOOGLE_APPLICATION_CREDENTIALS_JSON=<paste the service-account JSON>` (start.sh
     materializes it to tmpfs for ADC — the key never lives in the repo/image)
3. Networking → *Generate Domain* → note the `https://….up.railway.app` URL.
4. Verify: `curl https://<domain>/health` → `{"status":"ok"}`; docs at `/docs`.

Point the app at it: `--dart-define=API_BASE_URL=https://<domain>` (https — the iOS dev ATS
exception is only needed for local http).

## Mobile auth (D23/D28)

Sign-in is a direct **OAuth 2.0 authorization-code + PKCE** flow: the app opens Google's
consent page (`flutter_web_auth_2`), gets an authorization code, and posts
`{code, code_verifier}` to `POST /api/v1/auth/google/mobile`. The backend exchanges it
(iOS client id + PKCE, no secret), stores the Gmail tokens **server-side only**, and returns
a short-lived app JWT. All data endpoints require `Authorization: Bearer <jwt>`.

GCP prerequisites (console, one-time): OAuth consent screen with the `gmail.readonly` scope
+ your account as a Test user, a **Web** OAuth client (backend), and an **iOS** OAuth client
(the app; its reversed client id is the URL scheme in `frontend/ios/Runner/Info.plist`).
An Android OAuth client (package + SHA-1) is needed when running on Android.

## Frontend — run the app

```bash
cd frontend
flutter pub get
flutter test && flutter analyze
```

Run against your local backend (dart-defines are required — Xcode's Run button does not
pass them, so always launch via `flutter run`):

```bash
flutter run -d <device-id> \
  --dart-define=API_BASE_URL=<see table> \
  --dart-define=GOOGLE_IOS_CLIENT_ID=<ios oauth client id>
```

| Target            | `API_BASE_URL`                  |
|-------------------|---------------------------------|
| iOS simulator     | `http://localhost:8000`         |
| Android emulator  | `http://10.0.2.2:8000`          |
| Physical device   | `http://<your-Mac-LAN-IP>:8000` (backend on `--host 0.0.0.0`, same Wi-Fi) |

Then in the app: **Continue with Google → approve Gmail read-only → Sync inbox**. Items
appear in the list; mark them done/dismiss via the row menu. The session JWT expires after
15 minutes — sign out/in to refresh (auto-refresh is on the roadmap).

## API surface (v1)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/auth/google/mobile` | PKCE code → app JWT (creates the user) |
| POST | `/api/v1/sync` | fetch → filter → redact → extract → persist (idempotent) |
| GET | `/api/v1/items?from=&to=&type=` | the user's events/actions |
| PATCH | `/api/v1/items/{id}` | `{"status": "done"\|"dismissed"}` |
| POST | `/api/v1/devices/register` | FCM token registration (sender deferred, D27) |
| GET | `/health` | health check |

All data endpoints are JWT-scoped; there is no `?email=` parameter anywhere.
