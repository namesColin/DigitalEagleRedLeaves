import os

#将硬编码的 URL 和模型名称抽离，方便后续一键切换模型（比如从 Qwen3 切换到 DeepSeek）。
class Config:
    # 基础连接
    BASE_URL = "http://localhost:11434/v1"
    API_KEY = "ollama"
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PWD = "admin123"

    # 模型配置
    LLM_MODEL = "qwen3:8b"
    EMBED_MODEL = "nomic-embed-text:latest"
    EMBED_DIM = 768
    RERANK_MODEL = "qllama/bge-reranker-v2-m3:latest"

    @staticmethod
    def setup_env():
        """
        设置环境变量，隔离 OpenAI API Key 和 Neo4j 数据库名称。
        :return: None
        """
        os.environ["OPENAI_API_KEY"] = Config.API_KEY
        os.environ["NEO4J_DATABASE"] = "neo4j"