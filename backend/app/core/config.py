from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LoreGuard"
    app_version: str = "0.1.0"
    debug: bool = False

    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "loreguard"
    database_user: str = "loreguard"
    database_password: str

    obsidian_vault_path: str

    # Optional -- LLM-based prose fact extraction is only
    # available when at least one of these is set. Everything else
    # in the app works fine without either.
    #
    # llm_provider controls which one is used: "auto" (default)
    # picks Gemini if GEMINI_API_KEY is set (it's free), else
    # Anthropic if ANTHROPIC_API_KEY is set. Set explicitly to
    # "anthropic" or "gemini" to force one regardless of what else
    # is configured. See app/services/llm_provider.get_llm_provider.
    llm_provider: str = "auto"

    anthropic_api_key: str | None = None
    # Haiku is the pragmatic default: this is short, structured
    # extraction on individual notes, not a task that needs
    # Sonnet/Opus-level reasoning -- and it's the cheapest tier.
    anthropic_model: str = "claude-haiku-4-5"

    gemini_api_key: str | None = None
    # Flash-Lite has the most generous free-tier quota of the
    # Gemini lineup as of Aug 2026. Model naming moves fast on
    # Google's side -- check ai.google.dev/gemini-api/docs/pricing
    # for the current free-tier-eligible model list if this stops
    # working.
    gemini_model: str = "gemini-2.5-flash-lite"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://"
            f"{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}"
            f"/{self.database_name}"
        )


settings = Settings()