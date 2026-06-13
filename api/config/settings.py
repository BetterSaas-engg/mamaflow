from pydantic_settings import BaseSettings


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


settings = Settings()
