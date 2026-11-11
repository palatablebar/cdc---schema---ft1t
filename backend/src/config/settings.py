"""集中配置：全部来自环境变量，默认值与 .env.example 保持一致。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # 数据库
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "cdcmerge"
    db_user: str = "cdcmerge"
    db_password: str = "cdcmerge_pw_2026"

    # 安全
    jwt_secret: str = "cdcmerge-jwt-secret-change-me-2026"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    refresh_token_days: int = 7

    # 运行时
    redis_url: str = "redis://localhost:6379/0"
    seed_demo: bool = True
    max_window_events: int = 20000
    rate_limit_runs_per_minute: int = 10
    rate_limit_default_per_minute: int = 240

    # schema 名
    cdc_schema: str = "cdc"
    target_schema: str = "dw"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
