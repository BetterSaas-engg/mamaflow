# Design — Settings + Delete-account (App polish, Track D · slice 2)

**Date:** 2026-07-04
**Status:** Approved (brainstorming) — pending implementation plan.
**Roadmap:** HANDOFF.md Track D. Slice 2 (slice 1 = the useful-items view). Delete-account is also a **prerequisite for E0** (Google OAuth verification expects a working data-deletion path).

## Problem

The app has no settings surface: sign-out is a bare app-bar icon on the home screen, there's no way to see which account is connected, and — critically — no way to **delete your account and revoke Gmail access**. For a privacy-positioned product reading a restricted Gmail scope, a self-serve deletion + revocation path is both a trust essential and a verification requirement.

## Goal

A Settings screen with account info, sign out, and a **Delete account** action that soft-deletes the user's data and truly revokes Gmail access at Google.

## Decisions taken

- **Delete semantics:** soft-delete (`deleted_at`) on the user + their items + their devices, honoring the locked AGENTS.md rule ("soft-delete PII; never hard-delete"), **plus immediate revocation of the Gmail token at Google** so access ends instantly rather than merely being forgotten locally. A physical purge job is a possible later addition if verification demands it (out of scope here).
- **Privacy-policy row:** deferred — there's no hosted policy URL yet (that's E0). Settings ships with email / sign out / delete only.
- **Delete confirmation:** **type-to-confirm** (`DELETE`) — cheap insurance against an accidental tap on an unrecoverable action.

## Scope

**In:**
1. Settings screen (gear icon on home → Settings); sign-out moves here.
2. `DELETE /api/v1/account` — soft-delete user + items + devices, drop + revoke the Gmail token.
3. `delete_token(email)` on the token store (both backends).
4. Reactivation of a soft-deleted user on re-sign-in (required — see below).

**Out (non-goals):** privacy-policy screen (until E0 hosts a URL), profile editing, the month calendar tab (separate Track D slice), any purge/scheduler job, push/reminders.

## Architecture

```
Settings screen ──(gear on home)
  ├─ account email (read-only)
  ├─ Sign out ───────────────► sessionProvider.signOut()  (existing)
  └─ Delete account
        └─ type-"DELETE" dialog ─► AccountService.delete()
                                        │ DELETE /api/v1/account (JWT)
                                        ▼
                             delete_account(db, user):
                               soft-delete user, items, devices  (one txn)
                               + revoke_and_drop_gmail_token(email)  ──► Google /revoke
                                        │ 204
                                        ▼
                             app: signOut() + drop JWT ─► sign-in screen
```

### Backend

**`DELETE /api/v1/account`** (new router `api/routers/account.py`), JWT-scoped via `get_current_user`:
- In one transaction, set `deleted_at = now()` on: the `User` row, every non-deleted `Item` with `user_id == user.id`, and every non-deleted `Device` with `user_id == user.id`.
- Then `revoke_and_drop_gmail_token(user.email)`:
  - Read the stored credentials; POST the refresh token (falling back to the access token) to Google's revocation endpoint `https://oauth2.googleapis.com/revoke` (revoking the refresh token invalidates its derived access tokens). Blocking HTTP runs off the event loop.
  - Then `delete_token(user.email)` from the store.
  - **Best-effort:** a revocation network failure is logged (sanitized — no token values) but does **not** roll back the local soft-delete; the token is still dropped locally. The account is gone from the app's perspective regardless.
- Returns `204 No Content`.

**Token store — `delete_token(email)`:** add a `delete(email)` method to both `InMemoryTokenStore` and `SecretManagerTokenStore` (destroy/remove the secret; write-through cache eviction), plus a module-level `delete_token(email)` mirroring `store_token`/`get_token`. Deleting an absent token is a no-op (idempotent).

**Reactivation (`get_or_create_user`):** today it filters `deleted_at IS NULL`, so a soft-deleted user is not found and a new `User(email=...)` insert would violate the `unique` email constraint — i.e. re-sign-in after delete currently crashes. Change the lookup to find by email **regardless** of `deleted_at`; if the found user is soft-deleted, clear `deleted_at` (reactivate as a fresh start — their old soft-deleted items stay hidden) and return it; if active, return; else create. This keeps "delete, then sign in again" working.

### Frontend

- **`SettingsScreen`** (`ui/settings_screen.dart`): shows `sessionProvider`'s account email, a Sign-out row (calls the existing `sessionProvider.signOut()`), and a Delete-account row.
- **Home app bar:** replace the standalone Sign-out icon with a **gear** icon → `Navigator.push(SettingsScreen)`. The completed-toggle stays.
- **Delete dialog:** a modal explaining it's permanent and ends Gmail access, with a text field that enables the destructive "Delete account" button only when the input equals `DELETE`.
- **`AccountService`** (`account/account_service.dart`): `Future<void> delete()` → `DELETE /api/v1/account` via `ApiClient`.
- On success: `sessionProvider.signOut()` (clears the JWT; the auth gate returns to sign-in). On failure: a snackbar; stay on Settings.
- The account email must be available to the UI. If `sessionProvider` doesn't already expose it, decode it from the JWT (the token carries `email`) or add it to session state — the plan will pick the smallest change.

## Error handling

- Backend: revocation failure → sanitized log, local delete still commits, 204 returned. Missing token → no-op. Any unexpected error → 500 with a generic message (no token/PII in the body).
- Frontend: non-2xx from delete → snackbar "Couldn't delete your account. Try again."; the dialog's button is disabled until `DELETE` is typed.

## Testing

- **Backend (pytest, Google revocation mocked — never live):** delete soft-deletes user + items + devices (verified via `deleted_at`); the token store's `delete_token` is called and the revocation endpoint is hit with the stored token; after delete, JWT-gated calls for that user return **401** (this already holds: `get_current_user` rejects a user whose `deleted_at` is set — assert it as a regression guard, no new code); revocation failure still returns 204 and still drops the token; re-sign-in via `get_or_create_user` reactivates the soft-deleted user (clears `deleted_at`, no duplicate row, no unique-constraint error); `delete_token` on an absent token is a no-op.
- **Frontend (flutter test, mocked ApiClient):** Settings renders the email + rows; the delete dialog's button is disabled until `DELETE` is typed; a confirmed delete calls `AccountService.delete` then signs out; a failed delete shows a snackbar and stays.
- `flutter analyze` clean; backend + frontend suites green; firewall-guard green.

## Firewall / privacy invariants

- **D19 (firewall):** no content or derivation reaches the ad layer; this slice adds no ad surface.
- **D5:** no raw email body introduced; deletion only sets `deleted_at` on structured rows.
- **D4:** the Gmail token is handled only via the token store (never the DB); delete both drops it locally and revokes it at Google. No token value is ever logged.
- **Locked soft-delete rule honored:** deletion is `deleted_at`, never a hard `DELETE`.

## Security-audit note

Touches data persistence (account/item/device deletion) and the Gmail token (revocation + store deletion) → mandatory `@security-auditor` pass. Focus: user-scoping on every soft-delete (a user can only delete their own rows), token never logged, revocation targets only the stored token, reactivation can't leak a prior user's items.
