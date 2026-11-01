from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://conduit:conduit@localhost:5432/conduit"
    redis_url: str = ""  # empty = in-memory rate limiting (dev/tests only)
    secret_key: str  # signs access tokens; no default on purpose
    fernet_key: str  # encrypts provider keys at rest
    access_ttl_min: int = 15
    refresh_ttl_days: int = 14
    cookie_secure: bool = True
    allowed_origins: str = "http://localhost:3000"
    execution_mode: str = "live"  # live = real providers; demo = clearly labelled simulated outputs, no keys needed
    execution_backend: str = "thread"  # celery | thread | sync (tests)
    # Celery broker. Empty = use redis_url. With no Redis on a dev machine, a SQLite broker works:
    # CELERY_BROKER_URL=sqla+sqlite:///./celery_broker.db
    celery_broker_url: str = ""
    provider_timeout: float = 120.0  # seconds per provider HTTP call
    exec_parallelism: int = 3
    max_retries: int = 2
    retry_backoff: float = 0.5
    admin_emails: str = ""
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 2_000_000
    local_image_api_url: str = ""  # Optional local Automatic1111/Forge-compatible /sdapi/v1/txt2img endpoint

    @property
    def admins(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
