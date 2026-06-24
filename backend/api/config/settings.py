from pydantic import model_validator
from pydantic_settings import BaseSettings

_WEAK_SECRETS = {"", "dev-secret-key", "your-jwt-secret-key"}


class Settings(BaseSettings):
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    secret_key: str = "dev-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    anthropic_api_key: str = ""
    database_url: str = "postgresql://localhost:5432/mamaflow"
    environment: str = "development"

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
