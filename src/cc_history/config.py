from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEV_LOGS_ROOT = PROJECT_ROOT / "docs" / "claude-logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CC_", env_file=".env")

    nas_root: Path = DEFAULT_DEV_LOGS_ROOT
    cache_dir: Path = Path.home() / ".cache" / "cc-history-viewer"
    single_user_name: str = "local"
    host: str = "0.0.0.0"
    port: int = 8000
    auth_password: str | None = None
    auth_cookie_name: str = "cc_history_auth"
    watch_enabled: bool = False
    log_level: str = "INFO"

    @property
    def cache_db_path(self) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / "cache.db"


settings = Settings()
