import os

class Config:
    # ====================================================================
    # 切换 LLM 后端：只改这里
    #   "deepseek" → DeepSeek API（云端）
    #   "ollama"   → 本地 Ollama
    # ====================================================================
    LLM_BACKEND = "deepseek"

    # DeepSeek API 预设
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    DEEPSEEK_API_KEY = "sk-300e118594544603a1f16f9716e508a9"  # 替换为你的 key
    DEEPSEEK_MODEL = "deepseek-v4-pro"               # deepseek-chat 或 deepseek-reasoner

    # 本地 Ollama 预设
    OLLAMA_BASE_URL = "http://localhost:11434/v1"
    OLLAMA_API_KEY = "ollama"
    OLLAMA_MODEL = "qwen3:8b"

    # Neo4j 图数据库
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PWD = "admin123"

    # Embedding & Reranker — 始终使用本地 Ollama
    EMBED_BASE_URL = "http://localhost:11434/v1"
    EMBED_API_KEY = "ollama"
    EMBED_MODEL = "nomic-embed-text:latest"
    EMBED_DIM = 768
    RERANK_BASE_URL = "http://localhost:11434/v1"
    RERANK_API_KEY = "ollama"
    RERANK_MODEL = "qllama/bge-reranker-v2-m3:latest"

    # ===== 解析方法（brain_engine 调用，根据 LLM_BACKEND 自动选择）=====

    @classmethod
    def resolve_base_url(cls):
        return cls.DEEPSEEK_BASE_URL if cls.LLM_BACKEND == "deepseek" else cls.OLLAMA_BASE_URL

    @classmethod
    def resolve_api_key(cls):
        return cls.DEEPSEEK_API_KEY if cls.LLM_BACKEND == "deepseek" else cls.OLLAMA_API_KEY

    @classmethod
    def resolve_model(cls):
        return cls.DEEPSEEK_MODEL if cls.LLM_BACKEND == "deepseek" else cls.OLLAMA_MODEL

    # ===== 环境变量 =====

    @staticmethod
    def setup_env():
        os.environ["OPENAI_API_KEY"] = Config.resolve_api_key()
        os.environ["NEO4J_DATABASE"] = "neo4j"
