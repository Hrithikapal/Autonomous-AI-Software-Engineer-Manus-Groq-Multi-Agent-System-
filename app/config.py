from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Kimi / Moonshot
    kimi_api_key: str
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-128k"

    # App
    app_env: str = "production"
    log_level: str = "info"
    secret_key: str = "change-me"

    # Sandbox
    sandbox_url: str = "http://sandbox:8001"
    max_exec_time: int = 30

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_collection: str = "agent_memory"

    # Agent behaviour
    max_debug_retries: int = 3
    max_plan_steps: int = 10
    agent_timeout: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
