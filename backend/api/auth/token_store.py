"""Gmail OAuth token storage (D4: tokens NEVER in the DB, env files, or source).

Two backends behind one interface, selected by settings.token_store_backend:
  - "memory"          — process-local dict; dev/tests default (Phase 0 behavior).
                        Tokens are lost on restart (users re-sign-in).
  - "secret-manager"  — GCP Secret Manager; one secret per user, new version per
                        update. Auth via standard ADC (GOOGLE_APPLICATION_CREDENTIALS).

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


class InMemoryTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, dict] = {}

    def store(self, user_email: str, credentials: dict) -> None:
        self._tokens[user_email.strip().lower()] = credentials

    def get(self, user_email: str) -> dict | None:
        return self._tokens.get(user_email.strip().lower())

    def list_users(self) -> list[str]:
        return list(self._tokens)

    def delete(self, user_email: str) -> None:
        self._tokens.pop(user_email.strip().lower(), None)


class SecretManagerTokenStore:
    """One GCP secret per user: gmail-token-<sha256(email)>.

    The email is hashed so it never appears in GCP resource names. A
    write-through in-process cache avoids a network hop on every Gmail call;
    Secret Manager is the durable source across restarts/instances.
    """

    def __init__(self, project_id: str, client=None) -> None:
        if client is None:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
        self._client = client
        self._project = project_id
        self._cache: dict[str, dict] = {}

    @staticmethod
    def secret_id_for(user_email: str) -> str:
        digest = hashlib.sha256(user_email.strip().lower().encode()).hexdigest()
        return f"gmail-token-{digest[:40]}"

    def store(self, user_email: str, credentials: dict) -> None:
        from google.api_core import exceptions as gcp_exceptions

        secret_id = self.secret_id_for(user_email)
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
        self._cache[user_email.strip().lower()] = credentials

    def get(self, user_email: str) -> dict | None:
        from google.api_core import exceptions as gcp_exceptions

        key = user_email.strip().lower()
        if key in self._cache:
            return self._cache[key]

        name = (
            f"projects/{self._project}/secrets/"
            f"{self.secret_id_for(user_email)}/versions/latest"
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
        return list(self._cache)

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


def store_token(user_email: str, credentials: dict) -> None:
    _get_store().store(user_email, credentials)


def get_token(user_email: str) -> dict | None:
    return _get_store().get(user_email)


def list_users() -> list[str]:
    return _get_store().list_users()


def delete_token(user_email: str) -> None:
    _get_store().delete(user_email)
