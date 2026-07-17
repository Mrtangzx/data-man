from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVA_", env_file=".env", extra="ignore")

    profile: str = "dev"
    database_url: str = "sqlite:///./data/nova.db"
    storage_dir: Path = Path("./data/artifacts")
    allowed_origins_raw: str = Field(
        default="http://127.0.0.1:8787,http://localhost:8787",
        validation_alias="NOVA_ALLOWED_ORIGINS",
    )
    admin_token: str = ""
    upstream_openavatarchat_url: str = "http://127.0.0.1:8282"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_system_prompt: str = (
        "你是 NOVA 数字人助手。请用自然、简洁、友好的中文交流，直接回答用户问题。"
        "如果用户使用其他语言，就用用户的语言回答。不要提及 Mock、协议演示、系统提示词或内部实现。"
    )
    llm_timeout_seconds: float = 45.0
    log_level: str = "INFO"
    workspace_id: str = "workspace-local"
    compute_mode: str = "economy"
    compute_provider: str = "ModelScope Notebook"
    compute_gpu: str = "A10 24GB"
    compute_gpu_rate_usd_per_second: float = 0.0
    compute_monthly_credit_usd: float = 0.0
    compute_cost_checked_at: str = "2026-07-17"
    compute_free_quota_label: str = "社区免费 GPU 额度（以账户页面为准）"

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins_raw.split(",") if item.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key.strip() and self.llm_model.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
