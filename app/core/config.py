from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model_id: str = "gpt-3.5-turbo"
    llm_timeout: int = 20

    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com/search"  
    search_timeout_seconds: float = 20.0
    search_max_results: int = 3
    search_topic: Literal["general", "news", "finance"] = "general"
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic"  

    workspace_root: str = "workspace"
    lark_mode: Literal["fake", "dry_run", "real"] = "fake"
    lark_im_mode: Literal["fake", "dry_run", "real"] | None = None
    lark_artifact_mode: Literal["fake", "dry_run", "real"] | None = None
    lark_cli_timeout_seconds: float = 30.0
    lark_stream_delay_seconds: float = 0.0
    agent_pilot_default_chat_id: str | None = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    knowledge_base_dir: str = "workspace/knowledge_base"
    rag_index_dir: str = "workspace/knowledge_base/vector_index"
    rag_embedding_backend: Literal["huggingface", "openai"] = "huggingface"
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_model_cache_dir: str = "model"
    rag_openai_embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 4
    rag_vector_k: int = 6
    rag_bm25_k: int = 6
    rag_rrf_k: int = 60
    rag_max_context_chars: int = 2400

#lru_cache 装饰器用于缓存函数的返回值，即 Settings 实例，避免重复创建实例
@lru_cache
def get_settings() -> Settings:
    return Settings()
