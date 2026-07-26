"""Mail credential storage (D4: credentials NEVER in the DB, env files, or source).

Provider-aware since the multi-provider work: Google OAuth tokens keep their
original un-prefixed keys/secret ids (zero migration for existing users);
IMAP app-password credentials are stored under provider-prefixed keys.

Two backends behind one interface, selected by settings.token_store_backend:
  - "memory"          — process-local dict; dev/tests default (Phase 0 behavior).
                        Tokens are lost on restart (users re-sign-in).
  - "secret-manager"  — GCP Secret Manager; one secret per user, new version per
                        update. Auth: GOOGLE_APPLICATION_CREDENTIALS_JSON (the
                        service-account JSON in an env var — Railway has no
                        filesystem for an ADC file), falling back to standard
                        ADC (GOOGLE_APPLICATION_CREDENTIALS) when unset.

The module-level store_token/get_token/list_users functions remain the stable
interface for callers (oauth endpoint, gmail_reader).
"""

import hashlib
import json
import logging

from api.config.settings import settings

_log = logging.getLogger(__name__)


class TokenStoreError(Exception):
    """Token storage backend unavailable/failed. Message is sanitized — never
    carries GCP internals (they stay in the chained exception for server logs)."""


def _mem_key(user_email: str, provider: str) -> str:
    # \x00 can't appear in either component — collision-proof join.
    return f"{provider}\x00{user_email.strip().lower()}"


class InMemoryTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, dict] = {}

    def store(self, user_email: str, credentials: dict, provider: str = "google") -> None:
        self._tokens[_mem_key(user_email, provider)] = credentials

    def get(self, user_email: str, provider: str = "google") -> dict | None:
        return self._tokens.get(_mem_key(user_email, provider))

    def list_users(self) -> list[str]:
        return [key.split("\x00", 1)[1] for key in self._tokens]

    def delete(self, user_email: str, provider: str = "google") -> None:
        self._tokens.pop(_mem_key(user_email, provider), None)


def _credentials_from_env():
    """Service-account credentials from GOOGLE_APPLICATION_CREDENTIALS_JSON —
    the whole JSON in an env var (a credential: env only, never the DB, D4).
    Returns None when unset, letting the client fall back to standard ADC."""
    raw = settings.google_application_credentials_json
    if not raw:
        return None
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_info(json.loads(raw))


class SecretManagerTokenStore:
    """One GCP secret per user: gmail-token-<sha256(email)>.

    The email is hashed so it never appears in GCP resource names. A
    write-through in-process cache avoids a network hop on every Gmail call;
    Secret Manager is the durable source across restarts/instances.
    """

    def __init__(self, project_id: str, client=None) -> None:
        if client is None:
            from google.cloud import secretmanager

            try:
                client = secretmanager.SecretManagerServiceClient(
                    credentials=_credentials_from_env()
                )
            except Exception as exc:
                # Sanitized boundary (class contract): the raw env JSON must
                # never ride an exception message toward a client.
                raise TokenStoreError("token store credentials invalid") from exc
        self._client = client
        self._project = project_id
        self._cache: dict[str, dict] = {}

    @staticmethod
    def secret_id_for(user_email: str, provider: str = "google") -> str:
        digest = hashlib.sha256(user_email.strip().lower().encode()).hexdigest()
        if provider == "google":
            # MUST stay byte-identical to the pre-multi-provider scheme —
            # existing prod secrets keep working with zero migration.
            return f"gmail-token-{digest[:40]}"
        # Provider keys come only from the registry (validated at the auth
        # endpoint), never raw user input — safe in a GCP resource name.
        return f"mail-{provider}-{digest[:40]}"

    def store(self, user_email: str, credentials: dict, provider: str = "google") -> None:
        from google.api_core import exceptions as gcp_exceptions

        secret_id = self.secret_id_for(user_email, provider)
        parent = f"projects/{self._project}"
        try:
            try:
                self._client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
            except gcp_exceptions.AlreadyExists:
                pass  # updating an existing user's token

            self._client.add_secret_version(
                request={
                    "parent": f"{parent}/secrets/{secret_id}",
                    "payload": {"data": json.dumps(credentials).encode()},
                }
            )
        except gcp_exceptions.GoogleAPIError as e:
            # Sanitized: GCP internals stay in the chained exception (server
            # logs), never in the message callers might surface.
            raise TokenStoreError("token store write failed") from e
        self._cache[_mem_key(user_email, provider)] = credentials

    def get(self, user_email: str, provider: str = "google") -> dict | None:
        from google.api_core import exceptions as gcp_exceptions

        key = _mem_key(user_email, provider)
        if key in self._cache:
            return self._cache[key]

        name = (
            f"projects/{self._project}/secrets/"
            f"{self.secret_id_for(user_email, provider)}/versions/latest"
        )
        try:
            response = self._client.access_secret_version(request={"name": name})
        except gcp_exceptions.NotFound:
            return None
        except gcp_exceptions.GoogleAPIError as e:
            raise TokenStoreError("token store read failed") from e

        credentials = json.loads(response.payload.data.decode())
        self._cache[key] = credentials
        return credentials

    def list_users(self) -> list[str]:
        # Emails are hashed in secret ids by design; only cached (this-process)
        # users are listable. Nothing currently depends on a global listing.
        return [key.split("\x00", 1)[1] for key in self._cache]

    def delete(self, user_email: str, provider: str = "google") -> None:
        from google.api_core import exceptions as gcp_exceptions

        self._cache.pop(_mem_key(user_email, provider), None)
        name = f"projects/{self._project}/secrets/{self.secret_id_for(user_email, provider)}"
        try:
            self._client.delete_secret(request={"name": name})
        except gcp_exceptions.NotFound:
            pass  # already absent — idempotent
        except gcp_exceptions.GoogleAPIError as exc:
            # Sanitized, non-fatal: a failed revoke/delete must not block account
            # deletion. GCP internals stay out of the logged message.
            _log.warning("token delete: secret manager delete failed (%s)", type(exc).__name__)


# Built lazily on first use — NOT at import time — so a dev .env selecting
# secret-manager can't couple test collection / module import to live GCP
# credentials (audit finding).
_store = None


def _get_store():
    global _store
    if _store is None:
        if settings.token_store_backend == "secret-manager":
            if not settings.gcp_project_id:
                raise RuntimeError(
                    "TOKEN_STORE_BACKEND=secret-manager requires GCP_PROJECT_ID"
                )
            _log.info(
                "token store: Secret Manager (project %s)", settings.gcp_project_id
            )
            _store = SecretManagerTokenStore(settings.gcp_project_id)
        else:
            _log.info("token store: in-memory (tokens lost on restart)")
            _store = InMemoryTokenStore()
    return _store


def store_token(user_email: str, credentials: dict, provider: str = "google") -> None:
    _get_store().store(user_email, credentials, provider)


def get_token(user_email: str, provider: str = "google") -> dict | None:
    return _get_store().get(user_email, provider)


def list_users() -> list[str]:
    return _get_store().list_users()


def delete_token(user_email: str, provider: str = "google") -> None:
    _get_store().delete(user_email, provider)


def _all_provider_keys() -> list[str]:
    # Lazy import avoids any import-order coupling with the services layer.
    from api.services.mail_providers import PROVIDERS

    return list(PROVIDERS)


def delete_other_tokens(user_email: str, keep_provider: str) -> None:
    """Purge this email's stored credential under EVERY provider except the one
    just written. Called on every successful sign-in so a user who moves
    between providers (e.g. yahoo → google → icloud) never leaves a live app
    password / OAuth token behind under an old provider (D4 credential
    lifecycle). Idempotent — deleting an absent key is a no-op."""
    store = _get_store()
    for key in _all_provider_keys():
        if key != keep_provider:
            store.delete(user_email, key)


def delete_all_tokens(user_email: str) -> None:
    """Purge this email's credential under every known provider — used on
    account deletion so nothing survives, regardless of which providers the
    account passed through."""
    store = _get_store()
    for key in _all_provider_keys():
        store.delete(user_email, key)
