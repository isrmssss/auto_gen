from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENRD_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8080
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8080"
    searxng_url: str = "http://127.0.0.1:8888"
    default_exec_memory_frac: float = 0.65
    prompt_core_token_budget: int = 5000
    prompt_brief_token_budget: int = 4000
    prompt_log_token_budget: int = 8000
    prompt_tools_token_budget: int = 2000
    sample_fraction: float = 0.05
    max_debug_depth: int = 5
    virtual_eval_k: int = 3
    novelty_cosine_block: float = 0.92
    refine_window: int = 5
    refine_max_in_window: int = 2
    source_fanout: int = 4
    fulltext_per_cycle: int = 2
    paper_card_chars: int = 900
    paper_disk_chars: int = 20000
    archive_body_chars: int = 1500

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
