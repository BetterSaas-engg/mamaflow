import logging
from zoneinfo import ZoneInfo

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_WEAK_SECRETS = {"", "dev-secret-key", "your-jwt-secret-key"}


class Settings(BaseSettings):
    google_client_id: str = ""
    google_client_secret: str = ""
    # Mobile PKCE flow (D23): the iOS OAuth client id the app uses for the
    # authorization-code request; the backend exchanges the code with it (no secret).
    google_ios_client_id: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    secret_key: str = "dev-secret-key"
    algorithm: str = "HS256"
    # Session length for the mobile app JWT (D31): 30 days. The client has no
    # refresh flow — on 401 it signs the user out — so a short TTL means a
    # forced re-login mid-use. Revisit (refresh tokens) in the E0 hardening.
    access_token_expire_minutes: int = 30 * 24 * 60
    anthropic_api_key: str = ""
    database_url: str = "postgresql://localhost:5432/mamaflow"
    environment: str = "development"
    # Gmail token persistence (D4: never the DB): "memory" (dev default; lost on
    # restart) or "secret-manager" (GCP, requires gcp_project_id + credentials).
    token_store_backend: str = "memory"
    gcp_project_id: str = ""
    # Service-account JSON for Secret Manager, whole JSON in the env var
    # (Railway has no filesystem for an ADC file). A credential: env only,
    # never the DB or source (D4). Empty -> standard ADC file path.
    google_application_credentials_json: str = ""
    # Min seconds between completed syncs per user (each sync = a full 30-day
    # metadata scan; repeated triggers are a cost/DoS vector — A2 audit).
    sync_cooldown_seconds: int = 60
    # Push reminders (Track B). Inert unless firebase_credentials_json is set
    # (the FCM service-account JSON — a credential, env only, never the DB).
    firebase_credentials_json: str = ""
    reminder_tz: str = "America/Toronto"
    reminder_hour: int = 18

    model_config = {"env_file": ".env", "extra": "ignore"}

    # The reminder knobs are cosmetic config: a bad value must degrade to the
    # default with a warning, never crash the app at import (2026-07-15 prod
    # outage: REMINDER_HOUR="10:30" -> ValidationError -> the whole API 502'd).
    # Security-critical settings (SECRET_KEY below) still fail hard.
    @field_validator("reminder_hour", mode="before")
    @classmethod
    def _tolerant_reminder_hour(cls, v: object) -> int:
        try:
            hour = int(v)  # type: ignore[arg-type]
            if not 0 <= hour <= 23:
                raise ValueError(f"hour {hour} out of range 0-23")
            return hour
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid REMINDER_HOUR %r (%s); falling back to 18. "
                "Use a whole hour 0-23 — the scheduler ticks on the hour.",
                v,
                exc,
            )
            return 18

    @field_validator("reminder_tz", mode="before")
    @classmethod
    def _tolerant_reminder_tz(cls, v: object) -> str:
        try:
            ZoneInfo(str(v))
            return str(v)
        except Exception as exc:
            logger.warning(
                "Invalid REMINDER_TZ %r (%s); falling back to America/Toronto.",
                v,
                exc,
            )
            return "America/Toronto"

    @model_validator(mode="after")
    def _require_strong_secret_outside_dev(self) -> "Settings":
        # JWTs signed with a placeholder secret are trivially forgeable.
        if self.environment != "development" and self.secret_key in _WEAK_SECRETS:
            raise ValueError(
                "SECRET_KEY must be set to a strong value when ENVIRONMENT != development"
            )
        return self


settings = Settings()
