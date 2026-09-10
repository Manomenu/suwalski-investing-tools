from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from suwalski_investing_library.constants import SOLUTION_ROOT

ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[SOLUTION_ROOT / ".env.base", SOLUTION_ROOT / ".env", ROOT / ".env.base", ROOT / ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 6100

    # How long a ticker snapshot is reused before Yahoo is asked again. Fundamentals move
    # quarterly and the price barely moves inside a session, so minutes are plenty.
    market_cache_ttl_seconds: int = 900

    # Browser origins allowed to call the API — the dashboard runs on its own origin,
    # so without this every request from it fails the preflight.
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
