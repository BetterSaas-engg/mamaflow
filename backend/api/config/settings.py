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
    # Extraction model (D36). Haiku-first per the email-extraction skill: the
    # task is schema-locked structured extraction, so the cheap model is the
    # default ($1/$5 per MTok vs Sonnet's $3/$15 — ~3x cheaper). Flip to
    # EXTRACTION_MODEL=claude-sonnet-4-6 if accuracy on messy emails dips.
    extraction_model: str = "claude-haiku-4-5"
    # Cost controls. A message whose extraction keeps failing used to be
    # re-sent to Claude every hour for up to 30 days; give up after N tries
    # (hourly ticks => N hours of grace, ample for any transient fault).
    extraction_max_attempts: int = 3
    # Abort a sync run after this many CONSECUTIVE transient failures — a
    # Claude outage otherwise burns 50 failed calls per user per tick.
    extraction_failure_breaker: int = 5
    # Hard per-user daily ceiling on extraction calls. Structurally caps the
    # blast radius of any future runaway, including ones we haven't imagined.
    extraction_daily_call_budget: int = 200
    # How many message ids one sync LISTS (cheap — ids only, no bodies) and how
    # many it actually processes. These were a single value of 50, which meant
    # anything older than the newest 50 in the 30-day window was never listed
    # again once those were synced — silently unextracted forever, worst on a
    # new user's backlog. Listing wide + processing bounded drains a backlog
    # across runs without a cost spike.
    sync_scan_max_messages: int = 500
    sync_max_messages_per_run: int = 50
    # Auto-sync skips accounts with no authenticated request in this many days;
    # they resume the moment the user opens the app. Without it the hourly tick
    # billed every account that ever signed up, forever — the cost regression
    # that scales with churn instead of usage. 0 disables the skip.
    auto_sync_dormant_days: int = 14
    # Throttle for the last_seen_at write (it runs on every authed request;
    # the value only needs day-level accuracy).
    last_seen_throttle_seconds: int = 3600
    # Shared secret RevenueCat sends in the Authorization header of every
    # webhook. Env only, never the DB (D4). Empty = the endpoint refuses
    # everything, because an unconfigured webhook that accepts is exactly how a
    # staging URL becomes a tier-granting oracle.
    revenuecat_webhook_secret: str = ""
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
    # IMAP providers (Yahoo/Rogers, iCloud): socket timeout for connect/login/
    # fetch. Must stay under the frontend's 30s Dio timeout with headroom.
    imap_timeout_seconds: int = 25
    # Brute-force throttle for POST /auth/imap (credential-stuffing surface).
    imap_auth_max_attempts_per_ip: int = 10
    imap_auth_max_failures_per_email: int = 5
    imap_auth_window_seconds: int = 900
    # Push reminders (Track B). Inert unless firebase_credentials_json is set
    # (the FCM service-account JSON — a credential, env only, never the DB).
    firebase_credentials_json: str = ""
    reminder_tz: str = "America/Toronto"
    reminder_hour: int = 18
    # Hourly background auto-sync (spec 2026-07-15). Kill switch; cosmetic
    # knob, so parsing is fail-soft (never crashes the app at import).
    auto_sync_enabled: bool = True
    # Desktop web app (spec 2026-07-18). Comma-separated https origins allowed
    # to call the API from a browser; empty (default) = no CORS headers at all.
    web_app_origins: str = ""
    # Web sessions are shorter than mobile's 30 days (D31): browser storage is
    # more exposed than a device keychain. Default 7 days.
    web_token_expire_minutes: int = 7 * 24 * 60

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

    @field_validator("auto_sync_enabled", mode="before")
    @classmethod
    def _tolerant_auto_sync_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        text = str(v).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        logger.warning(
            "Invalid AUTO_SYNC_ENABLED %r; falling back to True.", v
        )
        return True

    @model_validator(mode="after")
    def _require_strong_secret_outside_dev(self) -> "Settings":
        # JWTs signed with a placeholder secret are trivially forgeable.
        if self.environment != "development" and self.secret_key in _WEAK_SECRETS:
            raise ValueError(
                "SECRET_KEY must be set to a strong value when ENVIRONMENT != development"
            )
        # The webhook secret is the ONLY thing between the internet and a free
        # family tier — there is no body signature to fall back on. Fail hard
        # rather than warn, same as SECRET_KEY: a paid product that boots with
        # an unset or placeholder billing secret is worse than one that doesn't
        # boot. Empty is allowed outside production only so a staging deploy
        # without billing still starts (the route then 503s).
        if self.environment == "production" and (
            not self.revenuecat_webhook_secret
            or self.revenuecat_webhook_secret in _WEAK_SECRETS
            or len(self.revenuecat_webhook_secret) < 32
        ):
            raise ValueError(
                "REVENUECAT_WEBHOOK_SECRET must be set to a strong value "
                "(>= 32 chars) when ENVIRONMENT=production"
            )
        # RFC 7518 §3.2 wants >= 256 bits for HMAC-SHA256; PyJWT warns below
        # that. Deliberately a WARNING, not a hard failure: refusing to boot
        # would take production down for a key that is merely shorter than
        # ideal rather than guessable, and rotating the key signs every user
        # out — that has to be a scheduled act, not a surprise on deploy.
        if (
            self.environment != "development"
            and len(self.secret_key.encode()) < 32
        ):
            logging.getLogger(__name__).warning(
                "SECRET_KEY is %d bytes; RFC 7518 recommends >= 32 for HS256. "
                "Rotate when convenient — note that rotating signs out every "
                "user, since the app has no refresh flow (D31).",
                len(self.secret_key.encode()),
            )
        return self

    @property
    def web_origins_list(self) -> list[str]:
        return [o.strip() for o in self.web_app_origins.split(",") if o.strip()]


settings = Settings()
