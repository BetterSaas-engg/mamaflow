# A1 — Durable Gmail tokens (Secret Manager): activation checklist

The code is **DONE** (env-JSON credentials, audited): with `TOKEN_STORE_BACKEND=memory` nothing
changes; flipping the vars below makes Gmail tokens survive backend restarts/deploys (no more
re-sign-in after every deploy). The org-policy blocker is **already cleared** — the legacy
`iam.disableServiceAccountKeyCreation` constraint was overridden for the Mamaflow project during
the Firebase setup (that's how the FCM key got created).

## Your steps (GCP console, project `mamaflow-prod`)

1. **Create the service account** — IAM & Admin → Service Accounts → Create:
   - Name: `mamaflow-backend`
   - Grant role: **Secret Manager Admin** (`roles/secretmanager.admin`) — it creates one secret
     per user, so it needs create+addVersion+access+delete.
2. **Create a key** — the new service account → Keys → Add key → JSON → download.
   (If "key creation is not allowed" reappears, the org-policy override needs re-checking —
   same fix as the Firebase key: legacy constraint → project override → Not enforced.)
3. **Enable the API** (once per project): APIs & Services → enable **Secret Manager API**.
4. **Railway vars** (backend service — set all three in one edit so it's one redeploy):
   - `TOKEN_STORE_BACKEND` = `secret-manager`
   - `GCP_PROJECT_ID` = `mamaflow-prod`
   - `GOOGLE_APPLICATION_CREDENTIALS_JSON` = the whole key JSON, one line
     (credential — never commit it, never in the DB, D4; delete the download after pasting).
5. **Merge first**: the env-JSON code must be on `main` before the flip (it rides the current
   feature branch — PR it with the E0 docs batch).

## Verify

After the deploy: sign in on a device, run one sync, then **redeploy** (or restart) and run
another sync WITHOUT signing in again. If the second sync works, tokens are durable. A boot log
line `token store: Secret Manager (project mamaflow-prod)` confirms the backend selected it.

## Notes

- Bad `GOOGLE_APPLICATION_CREDENTIALS_JSON` fails loudly as `TokenStoreError` at first use — the
  raw JSON never rides an exception or log line.
- Audit flag (pre-existing): the in-process token cache is not multi-instance coherent — keep
  Railway at a single instance until a TTL/invalidation hook lands.
- Keyless alternative if key hygiene ever becomes a concern: host the backend on GCP (Cloud Run
  attaches the service account with no key file at all).
