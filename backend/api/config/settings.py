from pydantic import model_validator
from pydantic_settings import BaseSettings

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
    access_token_expire_minutes: int = 15
    anthropic_api_key: str = ""
    database_url: str = "postgresql://localhost:5432/mamaflow"
    environment: str = "development"
    # Gmail token persistence (D4: never the DB): "memory" (dev default; lost on
    # restart) or "secret-manager" (GCP, requires gcp_project_id + ADC creds).
    token_store_backend: str = "memory"
    gcp_project_id: str = ""
    # Min seconds between completed syncs per user (each sync = a full 30-day
    # metadata scan; repeated triggers are a cost/DoS vector — A2 audit).
    sync_cooldown_seconds: int = 60
    # Push reminders (Track B). Inert unless firebase_credentials_json is set
    # (the FCM service-account JSON — a credential, env only, never the DB).
    firebase_credentials_json: str = ""
    reminder_tz: str = "America/Toronto"
    reminder_hour: int = 18

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _require_strong_secret_outside_dev(self) -> "Settings":
        # JWTs signed with a placeholder secret are trivially forgeable.
        if self.environment != "development" and self.secret_key in _WEAK_SECRETS:
            raise ValueError(
                "SECRET_KEY must be set to a strong value when ENVIRONMENT != development"
            )
        return self


settings = Settings()
