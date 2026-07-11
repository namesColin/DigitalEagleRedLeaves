from datetime import datetime, timezone
from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from .config import Config
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
            base_url=self.config.BASE_URL,
            api_key=self.config.API_KEY,
            embedding_model=self.config.EMBED_MODEL,
            embedding_dim=self.config.EMBED_DIM
        )
        embedder = OpenAIEmbedder(config=embed_config)
        self.embedder = OpenAIEmbedder(config=embed_config)

        # 配置 Reranker
        rerank_config = LLMConfig(base_url=self.config.BASE_URL,
                                  api_key=self.config.API_KEY,
                                  model=self.config.RERANK_MODEL)
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

    # python
    async def check_semantic_exists(self, new_content: str, threshold: float = 0.85):
        '''
        `检查语义重复`：判断新内容在记忆中是否存在相似语义的片段。
        通过计算新内容与现有记忆片段的向量相似度，如果相似度超过阈值则认为存在重复。
        适用于避免存入语义重复的记忆片段。
        该方法依赖于 embedder 获取文本向量表示。
        目前实现了余弦相似度计算。
        :param new_content:  要检查的新的记忆内容
        :param threshold:  相似度阈值，默认 0.85
        :return:  True 如果存在相似记忆，False 否则
        说明：该方法会先检索现有记忆片段，然后计算新内容与每个记忆片段的相似度。
        如果任一记忆片段的相似度超过阈值，则返回 True，表示存在语义重复。
        该方法适用于在添加新记忆前进行语义去重检查。
        需要注意的是，该方法可能会消耗较多的 Embedding 调用，
        因为需要为新内容和每个现有记忆片段计算向量表示。
        适用于记忆库规模较小或中等的场景。
        '''
        existing_facts = await self.search_memory(new_content)
        if not existing_facts:
            return False

        import math
        import asyncio

        def to_list(vec):
            # 转换 numpy 等类型到列表
            try:
                return list(vec)
            except Exception:
                return vec

        async def get_embedding(text: str):
            # 方案 A：常见方法名 embed_documents
            if hasattr(self.embedder, "embed_documents"):
                res = await self.embedder.embed_documents([text])
                return to_list(res[0])

            # 方案 B：批量 create_batch
            if hasattr(self.embedder, "create_batch"):
                res = await self.embedder.create_batch([text])
                return to_list(res[0])

            # 方案 C：单条 create（有些实现接受 str 或 list）
            if hasattr(self.embedder, "create"):
                create_fn = self.embedder.create
                if asyncio.iscoroutinefunction(create_fn):
                    res = await create_fn(text)
                else:
                    # 兼容同步实现
                    res = create_fn(text)
                # 可能返回单个向量或包含向量的列表
                if isinstance(res, list) and res and isinstance(res[0], (list, tuple)):
                    return to_list(res[0])
                return to_list(res)

            # 方案 D：直接使用内部 client.embeddings.create（例如 openai 客户端）
            if hasattr(self.embedder, "client") and hasattr(self.embedder.client, "embeddings"):
                client = self.embedder.client
                # 支持 AsyncOpenAI 风格
                try:
                    res = await client.embeddings.create(input=[text],
                                                         model=getattr(self.embedder, "config", None) and getattr(
                                                             self.embedder.config, "embedding_model", None))
                    return to_list(res.data[0].embedding)
                except TypeError:
                    # 有些实现可能接受单字符串
                    res = await client.embeddings.create(input=text,
                                                         model=getattr(self.embedder, "config", None) and getattr(
                                                             self.embedder.config, "embedding_model", None))
                    return to_list(res.data[0].embedding)
                except Exception:
                    pass

            # 都失败则抛出
            raise AttributeError(
                "embedder 没有已知的 embedding 接口 (尝试过: embed_documents, create_batch, create, client.embeddings.create)")

        def cosine_sim(a, b):
            a = list(a)
            b = list(b)
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
            if na == 0 or nb == 0:
                return 0.0
            return dot / (na * nb)

        try:
            new_vec = await get_embedding(new_content)
        except Exception as e:
            print(f"DEBUG: 无法获取新文本向量: {e}")
            return False

        for fact in existing_facts:
            try:
                fact_vec = await get_embedding(fact)
            except Exception as e:
                # 如果某条记忆无法获得向量，跳过它
                print(f"DEBUG: 无法获取记忆向量，跳过: {e}")
                continue

            similarity = cosine_sim(new_vec, fact_vec)
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