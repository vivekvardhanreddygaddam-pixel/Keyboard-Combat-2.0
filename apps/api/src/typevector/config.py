"""TypeVector Arena — Application Configuration via Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables."""

    # Database
    database_url: str = (
        "postgresql+asyncpg://typevector:local_dev_password@localhost:5432/typevector_dev"
    )
    database_url_sync: str = (
        "postgresql+psycopg://typevector:local_dev_password@localhost:5432/typevector_dev"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Application
    app_env: str = "development"
    app_debug: bool = True
    app_secret_key: str = "CHANGE_ME_generate_a_random_64_char_hex_string"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Session
    session_cookie_name: str = "tv_session"
    session_max_age_seconds: int = 604800

    # Supabase (Optional Cloud Database & Services)
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return self.app_env == "production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
