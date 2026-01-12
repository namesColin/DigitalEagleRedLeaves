from datetime import datetime, timezone
from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from config import Config
from scipy.spatial.distance import cosine # 需要安装 scipy，或手动写余弦相似度计算

#负责与 Neo4j 和 Graphiti 内核交互，这是红叶的“海马体”。
class HongYeBrain:
    def __init__(self):
        self.reranker = None
        self.embedder = None
        self.config = Config()
        self.graphiti = None

    async def initialize(self):
        """
        初始化 Graphiti 大脑引擎，配置 LLM、Embedding 和 Reranker。
        :return: None
        """
        # 配置 LLM
        llm_config = LLMConfig(base_url=self.config.BASE_URL, api_key=self.config.API_KEY, model=self.config.LLM_MODEL)
        llm_client = OpenAIGenericClient(config=llm_config)

        # 配置 Embedding
        embed_config = OpenAIEmbedderConfig(
            base_url=self.config.BASE_URL, api_key=self.config.API_KEY,
            embedding_model=self.config.EMBED_MODEL, embedding_dim=self.config.EMBED_DIM
        )
        embedder = OpenAIEmbedder(config=embed_config)
        self.embedder = OpenAIEmbedder(config=embed_config)

        # 配置 Reranker
        rerank_config = LLMConfig(base_url=self.config.BASE_URL, api_key=self.config.API_KEY, model=self.config.RERANK_MODEL)
        rerank_config.cross_encoder_model = rerank_config.model
        reranker = OpenAIRerankerClient(config=rerank_config)
        self.reranker = OpenAIRerankerClient(config=rerank_config)

        self.graphiti = Graphiti(
            uri=self.config.NEO4J_URI,
            user=self.config.NEO4J_USER,
            password=self.config.NEO4J_PWD,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=reranker
        )
        self.graphiti.driver.database = "neo4j"
        self.llm_client = llm_client # 留给 RAG 使用

    async def add_memory(self, content: str, source: str = "observation"):
        """
        添加记忆片段到 Graphiti。
        记忆以 episode 形式存储，包含内容和来源描述。
        记忆的时间戳为当前 UTC 时间。
        记忆的名称统一为 "daily_log" 以便后续检索
        :param content: 要添加的记忆内容
        :param source: 记忆的来源描述，默认为 "observation"
        :return:
        """
        await self.graphiti.add_episode(
            name="daily_log",
            episode_body=content,
            source_description=source,
            reference_time=datetime.now(timezone.utc)
        )

    async def search_memory(self, query: str):
        """
        根据查询检索相关记忆片段（Fact）。
        使用 Graphiti 的搜索功能，返回与查询相关的去重记忆列表。
        记忆以 Fact 对象形式返回。
        :param query: 检索查询字符串
        :return: 相关记忆片段列表
        """
        results = await self.graphiti.search(query)
        # 提取并去重 Fact
        facts = list(set([res.fact for res in results if hasattr(res, 'fact')]))
        return facts

    async def check_semantic_exists(self, new_content: str, threshold: float = 0.85):
        existing_facts = await self.search_memory(new_content)
        if not existing_facts:
            return False

        # graphiti-core 的 OpenAIEmbedder 标准异步接口通常是 embed_documents
        try:
            # 方案 C：尝试 embed_documents
            new_vecs = await self.embedder.embed_documents([new_content])
            new_vec = new_vecs[0]
        except AttributeError:
            # 最后的保底方案：直接查看其内部使用的 client 接口
            # 有些版本可能需要通过 self.embedder.client.embeddings.create
            print(f"DEBUG: 尝试所有已知接口失败。当前对象属性: {dir(self.embedder)}")
            return False

        for fact in existing_facts:
            fact_vecs = await self.embedder.embed_documents([fact])
            fact_vec = fact_vecs[0]

            similarity = 1 - cosine(new_vec, fact_vec)

            if similarity > threshold:
                print(f"[记忆去重] 发现相似记忆: '{fact}' (相似度: {similarity:.2f})，跳过存入。")
                return True

        return False

    async def close(self):
        """
        关闭 Graphiti 连接。
        释放资源。
        :return: None
        """
        if self.graphiti:
            await self.graphiti.close()