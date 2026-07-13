import os

class Config:
    # ====================================================================
    # 对话 LLM — 切换 DeepSeek / Ollama
    # ====================================================================
    LLM_BACKEND = "deepseek"

    # ====================================================================
    # Graphiti 内部 LLM（实体提取、记忆搜索）— 独立切换
    # DeepSeek 支持 response_format(json_object) 但可能有兼容问题
    # 如遇 400 错误，切回 "ollama"
    # ====================================================================
    GRAPHITI_LLM_BACKEND = "deepseek"

    # DeepSeek API 预设
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    DEEPSEEK_API_KEY = "sk-300e118594544603a1f16f9716e508a9"
    DEEPSEEK_MODEL = "deepseek-v4-pro"

    # 本地 Ollama 预设
    OLLAMA_BASE_URL = "http://localhost:11434/v1"
    OLLAMA_API_KEY = "ollama"
    OLLAMA_MODEL = "qwen3:8b"

    # Neo4j 图数据库
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PWD = "admin123"

    # 视觉 LLM — Qwen3.7-Plus（阿里百炼 DashScope 北京）
    GLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    GLM_API_KEY = "sk-ws-H.EDMRYLR.E9eg.MEQCIE8BVlP7zBNNjGve-CYMJgrRd-vsxROWMy6hZCr1ED32AiB_ihiHQz8FCXSxmxE79L0jtl1ZLZWvVfKMrlZK2wRkeQ"
    GLM_VISION_MODEL = "qwen3.7-plus"

    # Embedding & Reranker — 始终使用本地 Ollama
    EMBED_BASE_URL = "http://localhost:11434/v1"
    EMBED_API_KEY = "ollama"
    EMBED_MODEL = "nomic-embed-text:latest"
    EMBED_DIM = 768
    RERANK_BASE_URL = "http://localhost:11434/v1"
    RERANK_API_KEY = "ollama"
    RERANK_MODEL = "qllama/bge-reranker-v2-m3:latest"

    # ===== 解析方法 — 对话 LLM =====

    @classmethod
    def _pick(cls, backend):
        return cls.DEEPSEEK_BASE_URL if backend == "deepseek" else cls.OLLAMA_BASE_URL

    @classmethod
    def _pick_key(cls, backend):
        return cls.DEEPSEEK_API_KEY if backend == "deepseek" else cls.OLLAMA_API_KEY

    @classmethod
    def _pick_model(cls, backend):
        return cls.DEEPSEEK_MODEL if backend == "deepseek" else cls.OLLAMA_MODEL

    @classmethod
    def resolve_base_url(cls):
        return cls._pick(cls.LLM_BACKEND)

    @classmethod
    def resolve_api_key(cls):
        return cls._pick_key(cls.LLM_BACKEND)

    @classmethod
    def resolve_model(cls):
        return cls._pick_model(cls.LLM_BACKEND)

    @classmethod
    def resolve_graphiti_base_url(cls):
        return cls._pick(cls.GRAPHITI_LLM_BACKEND)

    @classmethod
    def resolve_graphiti_api_key(cls):
        return cls._pick_key(cls.GRAPHITI_LLM_BACKEND)

    @classmethod
    def resolve_graphiti_model(cls):
        return cls._pick_model(cls.GRAPHITI_LLM_BACKEND)

    # ===== 环境变量 =====

    @staticmethod
    def setup_env():
        os.environ["OPENAI_API_KEY"] = Config.resolve_api_key()
        os.environ["NEO4J_DATABASE"] = "neo4j"
