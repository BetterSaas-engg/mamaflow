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
