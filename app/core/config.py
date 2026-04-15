from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com/search"  
    search_timeout_seconds: float = 20.0
    search_max_results: int = 3
    search_topic: Literal["general", "news", "finance"] = "general"
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic"  

    workspace_root: str = "workspaces"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

#lru_cache 装饰器用于缓存函数的返回值，即 Settings 实例，避免重复创建实例
@lru_cache
def get_settings() -> Settings:
    return Settings()