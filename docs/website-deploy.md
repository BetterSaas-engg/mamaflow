# Website + web app deploy (spec 2026-07-18)

## Local dev
Run the web app on a **fixed port** so it stays stable across `flutter run`
invocations: `flutter run -d chrome --web-port 5111`. That lets
`WEB_APP_ORIGINS=http://localhost:5111` (backend `.env`) and the Google
console's WEB OAuth client redirect URI `http://localhost:5111/auth.html`
stay put run to run — an unpinned/random port would otherwise drift and break
both.

## What deploys where (domain: themamaflow.com, purchased 2026-07-22)

One Flutter codebase, three outputs — plus a static marketing page:
- `website/` (static HTML) → Vercel project 1 → **https://themamaflow.com** (+ www).
  Required for Google OAuth verification (homepage + privacy policy) and, at ad
  launch, `app-ads.txt`.
- `frontend/` mobile builds → App Store / Play Store (TestFlight + Firebase App
  Distribution while testing).
- `frontend/` web build (`flutter build web`) → Vercel project 2 →
  **https://app.themamaflow.com**. Same app, in the browser; ships without push
  and without ads (D35).
Two Vercel projects because they deploy different folders — the `*.vercel.app`
URLs Vercel auto-assigns can be ignored once the domains are attached.

## Vercel setup (~30 min, do domains immediately)
1. **Landing:** New Project → import this repo → Root Directory `website/` →
   Framework "Other", no build command, output dir `.` → deploy → Settings →
   Domains → add `themamaflow.com` + `www.themamaflow.com` (Vercel shows the
   DNS records to add at the registrar).
2. **Web app:** built by CI/local (`cd frontend && flutter build web
   --dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app
   --dart-define=GOOGLE_WEB_CLIENT_ID=<GOOGLE_CLIENT_ID value>`), then
   `npx vercel deploy frontend/build/web` (the second Vercel project) →
   Domains → add `app.themamaflow.com`. Automating this deploy in CI is a
   follow-up.

## Backend + Google console (after domains attach)
- Google console → the WEB OAuth client (same id as backend GOOGLE_CLIENT_ID) →
  Authorized redirect URIs → add `https://app.themamaflow.com/auth.html`
  (keep the localhost one for dev).
- Railway: `WEB_APP_ORIGINS=https://app.themamaflow.com`.
- CTA link in `website/index.html` already points at app.themamaflow.com.
- Then run the browser sign-in smoke test (first real E2E of the web OAuth flow).
- At ad launch only: `website/app-ads.txt` with the AdMob publisher id.
