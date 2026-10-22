from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from suwinvtools_library.constants import SOLUTION_ROOT

PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[SOLUTION_ROOT / ".env.base", SOLUTION_ROOT / ".env", PROJECT_ROOT / ".env.base", PROJECT_ROOT / ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"  # noqa: S104 — inside a container, the pod network is the boundary
    port: int = 6240

    # How long a ticker snapshot is reused before Yahoo is asked again. Fundamentals move
    # quarterly and the price barely moves inside a session, so minutes are plenty.
    market_cache_ttl_seconds: int = 900

    # Browser origins allowed to call the API directly. Behind the vite proxy and nginx the
    # browser sees a single origin, so this only matters for a UI served from elsewhere.
    cors_origins: list[str] = ["http://localhost:3240"]

    # The default is the container `just db up` starts; compose and the cluster point this at
    # their own database.
    database_url: str = "postgresql://suwinvtools:suwinvtools@localhost:5473/suwinvtools"

    # --- signals (the monthly AI cycle job) -------------------------------------------------
    # Discord webhooks. Green and red are where verdicts go; status gets INVALID readings, single-
    # source claims and the run summary. Empty = that channel is off (the job only logs).
    discord_webhook_green: str = ""
    discord_webhook_red: str = ""
    discord_webhook_status: str = ""
    # Mentioned in every red message, so red pings even with the server muted. "<@&role id>" or empty.
    discord_red_mention: str = ""

    # Any OpenAI-compatible endpoint; the model only extracts facts from text the job fetched.
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    # Qwen-style models spend their budget thinking and sometimes return nothing; off by default.
    llm_disable_thinking: bool = True

    # Where the web app lives, for the links in Discord messages (…/signals/<id>).
    web_base: str = "http://localhost:3240"


settings = Settings()
