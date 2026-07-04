# Settings + Delete-account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Settings screen (account email, sign out, delete account) and a `DELETE /api/v1/account` endpoint that soft-deletes the user + their items + devices and revokes the Gmail token at Google.

**Architecture:** One new backend endpoint + service, a token-store `delete` method, and a `get_or_create_user` reactivation fix; frontend adds a Settings screen reached from a home gear icon, a JWT-email helper, and an account-delete service with a type-to-confirm dialog. Soft-delete only (never hard-delete); Gmail access is severed by calling Google's revocation endpoint.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + httpx (backend); Flutter + Riverpod + Dio + mocktail (frontend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-04-settings-delete-account-design.md`

## Global Constraints

- Deletion is **soft-delete only** — set `deleted_at`, never a hard `DELETE` (AGENTS.md locked rule).
- Every soft-delete is scoped to the authed user (`user_id == user.id`); a user can only delete their own rows.
- The Gmail token is dropped from the token store AND revoked at Google (`https://oauth2.googleapis.com/revoke`). A revocation failure is logged **sanitized** (never a token value) and must NOT roll back the local soft-delete; the endpoint still returns 204.
- No token value or PII is ever logged. No raw email body is introduced (D5). No content reaches the ad layer (D19).
- `DELETE /api/v1/account` returns **204 No Content**.
- Delete confirmation on the client uses **type-to-confirm**: the destructive button is enabled only when the input equals the exact string `DELETE`.
- Backend: run from `backend/`, tests `./.venv/bin/python -m pytest -q` (venv python; never system python). Google revocation is **mocked in tests — never call live Google**.
- Frontend: `flutter test` + `flutter analyze` clean; mock `ApiClient`/services, never live.
- TDD every task (failing test first). Commit after each task; Conventional Commits; end each commit body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Backend — `delete_token` on the token store

**Files:**
- Modify: `backend/api/auth/token_store.py` (`InMemoryTokenStore`, `SecretManagerTokenStore`, module funcs)
- Test: `backend/tests/test_token_store.py` (add cases; create the file if absent)

**Interfaces:**
- Consumes: existing `InMemoryTokenStore.store/get`, `SecretManagerTokenStore` (secret id derived from email), module `store_token`/`get_token`.
- Produces: `InMemoryTokenStore.delete(user_email)`, `SecretManagerTokenStore.delete(user_email)`, module `delete_token(user_email: str) -> None`. Deleting an absent token is a no-op (idempotent).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_token_store.py` (match the existing test style in that file if it exists; otherwise this is the file's initial content plus these tests):

```python
from api.auth import token_store
from api.auth.token_store import InMemoryTokenStore


def test_in_memory_delete_removes_token():
    store = InMemoryTokenStore()
    store.store("a@b.com", {"token": "x"})
    assert store.get("a@b.com") == {"token": "x"}

    store.delete("a@b.com")

    assert store.get("a@b.com") is None


def test_in_memory_delete_absent_is_noop():
    store = InMemoryTokenStore()
    store.delete("nobody@b.com")  # must not raise
    assert store.get("nobody@b.com") is None


def test_module_delete_token_uses_active_store(monkeypatch):
    store = InMemoryTokenStore()
    monkeypatch.setattr(token_store, "_store", store)
    monkeypatch.setattr(token_store, "_get_store", lambda: store)
    store.store("c@d.com", {"token": "y"})

    token_store.delete_token("c@d.com")

    assert store.get("c@d.com") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_token_store.py -q`
Expected: FAIL — `InMemoryTokenStore` has no `delete`; `token_store.delete_token` undefined.

- [ ] **Step 3: Add `delete` to `InMemoryTokenStore`**

In `backend/api/auth/token_store.py`, inside `InMemoryTokenStore` (which stores a dict `self._tokens`), add after `list_users`:

```python
    def delete(self, user_email: str) -> None:
        self._tokens.pop(user_email, None)
```

- [ ] **Step 4: Add `delete` to `SecretManagerTokenStore`**

Inside `SecretManagerTokenStore`, add a `delete` that removes the secret and evicts the write-through cache. The class already has: the static `secret_id_for(user_email)`, `self._project`, `self._client`, and `self._cache` keyed by `user_email.strip().lower()` (module already imports `logging` with `_log = logging.getLogger(__name__)`). Add after `get`:

```python
    def delete(self, user_email: str) -> None:
        from google.api_core import exceptions as gcp_exceptions

        self._cache.pop(user_email.strip().lower(), None)
        name = f"projects/{self._project}/secrets/{self.secret_id_for(user_email)}"
        try:
            self._client.delete_secret(request={"name": name})
        except gcp_exceptions.NotFound:
            pass  # already absent — idempotent
        except gcp_exceptions.GoogleAPIError as exc:
            # Sanitized, non-fatal: a failed revoke/delete must not block account
            # deletion. GCP internals stay out of the logged message.
            _log.warning("token delete: secret manager delete failed (%s)", type(exc).__name__)
```

Deleting an absent secret must not raise out of `delete`.

- [ ] **Step 5: Add the module-level `delete_token`**

After the existing `list_users` module function:

```python
def delete_token(user_email: str) -> None:
    _get_store().delete(user_email)
```

- [ ] **Step 6: Run tests + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_token_store.py -q && ./.venv/bin/python -m pytest -q`
Expected: new tests PASS; full suite green.

- [ ] **Step 7: Commit**

```bash
git add backend/api/auth/token_store.py backend/tests/test_token_store.py
git commit -m "feat(backend): delete_token on the token store (in-memory + secret-manager)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend — reactivate a soft-deleted user on re-sign-in

**Files:**
- Modify: `backend/api/services/users.py` (`get_or_create_user`)
- Test: `backend/tests/test_users_service.py` (add cases; create if absent)

**Interfaces:**
- Consumes: `User` model (has `deleted_at`), `normalize_email`.
- Produces: `get_or_create_user(db, email)` now finds a user by email **regardless of `deleted_at`**; if soft-deleted, clears `deleted_at` (reactivates) and returns it; if active, returns it; else creates. No duplicate-email insert.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_users_service.py`:

```python
import datetime

from api.services.users import get_or_create_user


async def test_get_or_create_reactivates_soft_deleted_user(db):
    user = await get_or_create_user(db, "Parent@Example.com")
    original_id = user.id
    user.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()

    # Signing in again must reactivate the SAME row (email is unique) — not
    # crash on the unique constraint, not create a duplicate.
    again = await get_or_create_user(db, "parent@example.com")

    assert again.id == original_id
    assert again.deleted_at is None


async def test_get_or_create_returns_active_user(db):
    a = await get_or_create_user(db, "x@y.com")
    b = await get_or_create_user(db, "x@y.com")
    assert a.id == b.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_users_service.py -q`
Expected: FAIL — the reactivation test errors (the current code filters `deleted_at IS NULL`, so it tries to insert a duplicate email → IntegrityError).

- [ ] **Step 3: Rewrite `get_or_create_user`**

Replace the function body in `backend/api/services/users.py`:

```python
async def get_or_create_user(db: AsyncSession, email: str) -> User:
    """Return the user for `email`, creating one if absent. Idempotent.

    A previously soft-deleted user is reactivated (deleted_at cleared) rather
    than duplicated — email is unique, and re-signing-in after account deletion
    is a fresh start (their old soft-deleted items stay hidden)."""
    normalized = normalize_email(email)

    result = await db.execute(select(User).where(User.email == normalized))
    user = result.scalar_one_or_none()
    if user is not None:
        if user.deleted_at is not None:
            user.deleted_at = None
            await db.commit()
            await db.refresh(user)
        return user

    user = User(email=normalized)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

- [ ] **Step 4: Run test to verify it passes + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_users_service.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/users.py backend/tests/test_users_service.py
git commit -m "fix(backend): reactivate soft-deleted user on re-sign-in (unique email)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Backend — delete-account service + `DELETE /api/v1/account`

**Files:**
- Create: `backend/api/services/account.py`
- Create: `backend/api/routers/account.py`
- Modify: `backend/api/main.py` (register the router)
- Test: `backend/tests/test_account_api.py`

**Interfaces:**
- Consumes: `User`, `Item` (`api.models.item.Item`), `Device` (`api.models.device.Device`), `token_store.get_token`/`delete_token` (Task 1), `get_current_user`, `get_db`.
- Produces:
  - `revoke_gmail_token(credentials: dict) -> None` — best-effort POST to Google's revocation endpoint; never raises.
  - `async delete_account(db, user) -> None` — soft-deletes user + their items + devices in one commit, then revokes + drops the Gmail token.
  - `DELETE /api/v1/account` → 204.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_account_api.py`:

```python
"""Delete-account endpoint (Track D slice 2). Google revocation is mocked."""

import datetime

from sqlalchemy import select

from api.auth import token_store
from api.auth.jwt import create_access_token
from api.models.device import Device
from api.models.item import Item
from api.schemas.family_event import FamilyItem
from api.services import account as account_service
from api.services.items import persist_items
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def test_delete_account_soft_deletes_and_revokes(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    await persist_items(
        db, user, "m1",
        [FamilyItem(item_type="event", event_title="Soccer", date="2026-06-20")],
    )
    db.add(Device(user_id=user.id, fcm_token="fcm-1", platform="ios"))
    await db.commit()
    token_store.store_token(user.email, {"refresh_token": "rt", "token": "at"})

    revoked = {}
    monkeypatch.setattr(account_service, "revoke_gmail_token",
                        lambda creds: revoked.update(creds))

    resp = await client.delete("/api/v1/account", headers=_auth(token))

    assert resp.status_code == 204
    # user soft-deleted
    refreshed = await db.get(type(user), user.id)
    assert refreshed.deleted_at is not None
    # items soft-deleted
    items = (await db.execute(select(Item).where(Item.user_id == user.id))).scalars().all()
    assert all(i.deleted_at is not None for i in items)
    # devices soft-deleted
    devs = (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
    assert all(d.deleted_at is not None for d in devs)
    # token revoked (with the stored creds) AND dropped
    assert revoked == {"refresh_token": "rt", "token": "at"}
    assert token_store.get_token(user.email) is None


async def test_deleted_account_jwt_is_rejected(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    monkeypatch.setattr(account_service, "revoke_gmail_token", lambda creds: None)

    await client.delete("/api/v1/account", headers=_auth(token))
    # The same JWT now names a soft-deleted user -> 401 (get_current_user guard).
    after = await client.get("/api/v1/items", headers=_auth(token))
    assert after.status_code == 401


async def test_delete_account_survives_revocation_failure(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    token_store.store_token(user.email, {"token": "at"})

    def boom(creds):
        raise RuntimeError("google down")
    # delete_account must swallow revocation errors (revoke_gmail_token is
    # best-effort); the account is still deleted and the token still dropped.
    monkeypatch.setattr(account_service, "revoke_gmail_token", boom)

    resp = await client.delete("/api/v1/account", headers=_auth(token))

    assert resp.status_code == 204
    assert token_store.get_token(user.email) is None


async def test_delete_account_requires_auth(client):
    resp = await client.delete("/api/v1/account")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_account_api.py -q`
Expected: FAIL — `api.services.account` and the route don't exist.

- [ ] **Step 3: Write the account service**

Create `backend/api/services/account.py`:

```python
"""Account deletion: soft-delete the user's data + revoke the Gmail token.

Deletion is soft (deleted_at), per the locked AGENTS.md rule. Gmail access is
truly severed by revoking the token at Google. Revocation is best-effort — a
failure never blocks the local delete, and no token value is ever logged."""

import datetime
import logging

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import token_store
from api.models.device import Device
from api.models.item import Item
from api.models.user import User

_log = logging.getLogger(__name__)

_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def revoke_gmail_token(credentials: dict) -> None:
    """Best-effort revoke at Google. Revoking the refresh token invalidates its
    derived access tokens. Never raises; never logs the token value."""
    token = credentials.get("refresh_token") or credentials.get("token")
    if not token:
        return
    try:
        httpx.post(_GOOGLE_REVOKE_URL, data={"token": token}, timeout=10)
    except Exception as exc:
        _log.warning("gmail token revoke failed (%s)", type(exc).__name__)


async def delete_account(db: AsyncSession, user: User) -> None:
    """Soft-delete the user + their items + devices (one commit), then revoke
    and drop the Gmail token."""
    now = datetime.datetime.now(datetime.UTC)

    await db.execute(
        update(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    await db.execute(
        update(Device).where(Device.user_id == user.id, Device.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    user.deleted_at = now
    await db.commit()

    creds = token_store.get_token(user.email)
    if creds is not None:
        try:
            revoke_gmail_token(creds)
        except Exception as exc:  # defensive: revoke_gmail_token shouldn't raise
            _log.warning("gmail token revoke raised (%s)", type(exc).__name__)
    token_store.delete_token(user.email)
```

- [ ] **Step 4: Write the router**

Create `backend/api/routers/account.py`:

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.db.session import get_db
from api.models.user import User
from api.services.account import delete_account

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete the authed user's account + data and revoke Gmail access."""
    await delete_account(db, user)
```

- [ ] **Step 5: Register the router**

In `backend/api/main.py`, add the import alongside the others and include it:

```python
from api.routers.account import router as account_router
# ... after the other include_router calls ...
app.include_router(account_router)
```

- [ ] **Step 6: Run tests to verify they pass + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_account_api.py -q && ./.venv/bin/python -m pytest -q`
Expected: 4 new tests PASS; full suite green.

- [ ] **Step 7: Commit**

```bash
git add backend/api/services/account.py backend/api/routers/account.py backend/api/main.py backend/tests/test_account_api.py
git commit -m "feat(backend): DELETE /account — soft-delete user data + revoke Gmail token

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — `emailFromJwt` helper + `accountEmailProvider`

**Files:**
- Create: `frontend/lib/account/jwt_email.dart`
- Create: `frontend/lib/account/account_providers.dart`
- Test: `frontend/test/account/jwt_email_test.dart`

**Interfaces:**
- Consumes: `tokenStoreProvider` (`core/providers.dart`) → `TokenStore.readJwt()`.
- Produces:
  - `String? emailFromJwt(String? jwt)` — decodes a JWT's payload and returns its `email` claim; null on any malformed input.
  - `final accountEmailProvider = FutureProvider<String?>(...)` — reads the stored JWT and returns its email.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/account/jwt_email_test.dart`:

```dart
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/jwt_email.dart';

String _jwt(Map<String, dynamic> payload) {
  String seg(Map<String, dynamic> m) =>
      base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
  return '${seg({'alg': 'HS256'})}.${seg(payload)}.sig';
}

void main() {
  test('extracts the email claim from a JWT payload', () {
    expect(emailFromJwt(_jwt({'sub': '1', 'email': 'a@b.com'})), 'a@b.com');
  });

  test('returns null for a payload without email', () {
    expect(emailFromJwt(_jwt({'sub': '1'})), isNull);
  });

  test('returns null for malformed or null input', () {
    expect(emailFromJwt(null), isNull);
    expect(emailFromJwt('not-a-jwt'), isNull);
    expect(emailFromJwt('a.b'), isNull);
    expect(emailFromJwt('a.!!!.c'), isNull);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/account/jwt_email_test.dart`
Expected: FAIL — `jwt_email.dart` doesn't exist.

- [ ] **Step 3: Implement the helper**

Create `frontend/lib/account/jwt_email.dart`:

```dart
import 'dart:convert';

/// Returns the `email` claim from a JWT's payload segment, or null if the
/// token is absent, malformed, or has no email. Pure — no verification (the
/// server issued and signs the token; this only reads a claim for display).
String? emailFromJwt(String? jwt) {
  if (jwt == null) return null;
  final parts = jwt.split('.');
  if (parts.length != 3) return null;
  try {
    final payload = utf8.decode(base64Url.decode(base64Url.normalize(parts[1])));
    final map = jsonDecode(payload);
    if (map is Map && map['email'] is String) return map['email'] as String;
    return null;
  } catch (_) {
    return null;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && flutter test test/account/jwt_email_test.dart`
Expected: PASS (3 tests).

- [ ] **Step 5: Add the provider**

Create `frontend/lib/account/account_providers.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import 'jwt_email.dart';

/// The signed-in account's email, read from the stored session JWT. Null if
/// no token or no email claim.
final accountEmailProvider = FutureProvider<String?>((ref) async {
  final jwt = await ref.watch(tokenStoreProvider).readJwt();
  return emailFromJwt(jwt);
});
```

- [ ] **Step 6: Analyze + commit**

Run: `cd frontend && flutter analyze`
Expected: no issues.

```bash
git add frontend/lib/account/jwt_email.dart frontend/lib/account/account_providers.dart frontend/test/account/jwt_email_test.dart
git commit -m "feat(frontend): emailFromJwt helper + accountEmailProvider

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — `ApiClient.delete` + `AccountService`

**Files:**
- Modify: `frontend/lib/core/api_client.dart` (add `delete`)
- Create: `frontend/lib/account/account_service.dart`
- Modify: `frontend/lib/account/account_providers.dart` (add `accountServiceProvider`)
- Test: `frontend/test/account/account_service_test.dart`

**Interfaces:**
- Consumes: `ApiClient` (Dio wrapper), `apiClientProvider` (`core/providers.dart`).
- Produces:
  - `Future<void> ApiClient.delete(String path)`.
  - `class AccountService { AccountService(ApiClient); Future<void> deleteAccount(); }` calling `DELETE /api/v1/account`.
  - `final accountServiceProvider = Provider<AccountService>(...)`.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/account/account_service_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_service.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  test('deleteAccount calls DELETE /api/v1/account', () async {
    final api = _MockApi();
    when(() => api.delete(any())).thenAnswer((_) async {});

    await AccountService(api).deleteAccount();

    verify(() => api.delete('/api/v1/account')).called(1);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/account/account_service_test.dart`
Expected: FAIL — `AccountService` doesn't exist; `ApiClient.delete` missing.

- [ ] **Step 3: Add `delete` to `ApiClient`**

In `frontend/lib/core/api_client.dart`, add after `patchJson`:

```dart
  Future<void> delete(String path) async {
    await _dio.delete(path);
  }
```

- [ ] **Step 4: Write `AccountService`**

Create `frontend/lib/account/account_service.dart`:

```dart
import '../core/api_client.dart';

/// Deletes the signed-in user's account (soft-delete + Gmail revocation
/// server-side). The caller signs out afterward.
class AccountService {
  AccountService(this._api);
  final ApiClient _api;

  Future<void> deleteAccount() => _api.delete('/api/v1/account');
}
```

- [ ] **Step 5: Add the provider**

Append to `frontend/lib/account/account_providers.dart`:

```dart
import 'account_service.dart';

final accountServiceProvider =
    Provider<AccountService>((ref) => AccountService(ref.watch(apiClientProvider)));
```

(Keep the existing imports; add the `account_service.dart` import at the top with the others.)

- [ ] **Step 6: Run test + analyze + commit**

Run: `cd frontend && flutter test test/account/account_service_test.dart && flutter analyze`
Expected: PASS; analyze clean.

```bash
git add frontend/lib/core/api_client.dart frontend/lib/account/account_service.dart frontend/lib/account/account_providers.dart frontend/test/account/account_service_test.dart
git commit -m "feat(frontend): ApiClient.delete + AccountService.deleteAccount

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend — Settings screen + home gear entry

**Files:**
- Create: `frontend/lib/ui/settings_screen.dart`
- Modify: `frontend/lib/ui/home_screen.dart` (swap the sign-out app-bar icon for a gear → Settings)
- Test: `frontend/test/account/settings_screen_test.dart`

**Interfaces:**
- Consumes: `accountEmailProvider`, `accountServiceProvider` (Tasks 4-5), `sessionProvider` (`auth/session_controller.dart`).
- Produces: `SettingsScreen` (ConsumerWidget) with account email, a Sign-out row, and a Delete-account row that opens a type-to-confirm dialog; on confirmed delete it calls `accountServiceProvider.deleteAccount()` then `sessionProvider.signOut()`.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/account/settings_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_providers.dart';
import 'package:mamaflow/account/account_service.dart';
import 'package:mamaflow/ui/settings_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockAccount extends Mock implements AccountService {}

Widget _host(AccountService account) => ProviderScope(
      overrides: [
        accountServiceProvider.overrideWithValue(account),
        accountEmailProvider.overrideWith((ref) async => 'parent@example.com'),
      ],
      child: const MaterialApp(home: SettingsScreen()),
    );

void main() {
  testWidgets('shows the account email', (tester) async {
    await tester.pumpWidget(_host(_MockAccount()));
    await tester.pumpAndSettle();
    expect(find.text('parent@example.com'), findsOneWidget);
  });

  testWidgets('delete button is gated on typing DELETE, then calls the service',
      (tester) async {
    final account = _MockAccount();
    when(() => account.deleteAccount()).thenAnswer((_) async {});

    await tester.pumpWidget(_host(account));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Delete account'));
    await tester.pumpAndSettle();

    // The confirm button exists but is disabled until "DELETE" is typed.
    final confirm = find.widgetWithText(FilledButton, 'Delete account');
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(find.byType(TextField), 'DELETE');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);

    await tester.tap(confirm);
    await tester.pumpAndSettle();

    verify(() => account.deleteAccount()).called(1);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/account/settings_screen_test.dart`
Expected: FAIL — `settings_screen.dart` doesn't exist.

- [ ] **Step 3: Write the Settings screen**

Create `frontend/lib/ui/settings_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../account/account_providers.dart';
import '../auth/session_controller.dart';

/// Account settings: connected email, sign out, and delete account.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final email = ref.watch(accountEmailProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          ListTile(
            leading: const Icon(Icons.account_circle_outlined),
            title: const Text('Signed in as'),
            subtitle: Text(email.valueOrNull ?? '—'),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Sign out'),
            onTap: () => ref.read(sessionProvider.notifier).signOut(),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.delete_forever, color: Colors.red),
            title: const Text('Delete account',
                style: TextStyle(color: Colors.red)),
            subtitle: const Text('Removes your data and ends Gmail access.'),
            onTap: () => _confirmDelete(context, ref),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => const _DeleteAccountDialog(),
    );
    if (confirmed != true) return;
    try {
      await ref.read(accountServiceProvider).deleteAccount();
      await ref.read(sessionProvider.notifier).signOut();
    } catch (_) {
      messenger.showSnackBar(const SnackBar(
        content: Text("Couldn't delete your account. Try again."),
      ));
    }
  }
}

/// Type-to-confirm dialog: the destructive button enables only when the input
/// equals exactly "DELETE". Pops true on confirm.
class _DeleteAccountDialog extends StatefulWidget {
  const _DeleteAccountDialog();
  @override
  State<_DeleteAccountDialog> createState() => _DeleteAccountDialogState();
}

class _DeleteAccountDialogState extends State<_DeleteAccountDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canDelete = _controller.text == 'DELETE';
    return AlertDialog(
      title: const Text('Delete account?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'This permanently deletes your data and revokes Mamaflow\'s '
            'access to your Gmail. This cannot be undone.\n\nType DELETE to confirm.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _controller,
            autofocus: true,
            decoration: const InputDecoration(hintText: 'DELETE'),
            onChanged: (_) => setState(() {}),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: Colors.red),
          onPressed: canDelete ? () => Navigator.of(context).pop(true) : null,
          child: const Text('Delete account'),
        ),
      ],
    );
  }
}
```

- [ ] **Step 4: Wire the home app bar to Settings**

In `frontend/lib/ui/home_screen.dart`, add the import at the top:

```dart
import 'settings_screen.dart';
```

Then in the `AppBar` `actions:` list, **replace the Sign-out `IconButton`** (the one with `Icons.logout` calling `signOut()`) with a gear that opens Settings — keep the completed-toggle `IconButton` unchanged:

```dart
          IconButton(
            tooltip: 'Settings',
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
```

- [ ] **Step 5: Run tests to verify they pass + full suite + analyze + firewall**

Run: `cd frontend && flutter test test/account/settings_screen_test.dart && flutter test && flutter analyze && cd .. && bash scripts/firewall-guard.sh`
Expected: settings tests PASS; full suite green; analyze clean; firewall-guard exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ui/settings_screen.dart frontend/lib/ui/home_screen.dart frontend/test/account/settings_screen_test.dart
git commit -m "feat(frontend): settings screen with delete-account (type-to-confirm) + home gear

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Security audit + HANDOFF update

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Security audit (touches data persistence + the Gmail token)**

Dispatch `@security-auditor` on the feature diff. Focus: every soft-delete is user-scoped (`user_id == user.id`), so a user can only delete their own items/devices; the account soft-delete + `get_current_user`'s existing `deleted_at` guard mean a retained JWT can't act on a deleted account; the Gmail token value is never logged (revoke + delete are sanitized); revocation targets only the stored token and its failure can't roll back the delete; reactivation on re-sign-in can't surface a prior user's soft-deleted items; firewall (D19) untouched. Address any BLOCK before proceeding.

- [ ] **Step 2: Update HANDOFF Track D row**

In `HANDOFF.md`, extend the Track D row to note slice 2 shipped (settings screen + `DELETE /account` soft-delete + Gmail revocation + soft-deleted-user reactivation), that it's an E0 data-deletion prerequisite, and that the month calendar tab + sync-progress UX remain.

- [ ] **Step 3: Commit + push**

```bash
git add HANDOFF.md
git commit -m "docs: HANDOFF — Track D slice 2 (settings + delete-account) shipped

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

## Self-review notes

- **Spec coverage:** Settings screen + gear entry (Task 6), sign-out relocation (Task 6), `DELETE /account` soft-delete of user+items+devices (Task 3), Gmail revoke + drop (Task 3 + Task 1's `delete_token`), reactivation on re-sign-in (Task 2), type-to-confirm (Task 6), email display via JWT (Task 4), retained-JWT-rejected regression (Task 3 test, existing guard), firewall/privacy audit (Task 7). Deferred privacy-policy row correctly absent.
- **Type consistency:** `delete_token`/`.delete()`, `revoke_gmail_token(credentials)`, `delete_account(db, user)`, `emailFromJwt(String?)`, `accountEmailProvider`, `AccountService.deleteAccount()`, `accountServiceProvider`, `ApiClient.delete(path)`, `SettingsScreen` are used with identical signatures across tasks.
- **Note for implementer (Task 1 Step 4):** the `SecretManagerTokenStore` field/helper names (`_secret_id` vs `_secret_name`, `_cache`, `_project`) must be read from the existing `store`/`get` methods and reused — do not invent names. If the delete-secret client call differs from `delete_secret(name=...)`, match the client library the class already imports.
```
