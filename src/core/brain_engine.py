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
        self._embed_cache = {}  # {text: vector} 避免重复 embedding

    async def initialize(self):
        """
        初始化 Graphiti 大脑引擎，配置 LLM、Embedding 和 Reranker。
        :return: None
        """
        # Graphiti 内部 LLM — 根据 GRAPHITI_LLM_BACKEND 切换
        graphiti_llm_config = LLMConfig(
            base_url=Config.resolve_graphiti_base_url(),
            api_key=Config.resolve_graphiti_api_key(),
            model=Config.resolve_graphiti_model()
        )
        graphiti_llm_client = OpenAIGenericClient(config=graphiti_llm_config)

        # DeepSeek 不支持 json_schema，降级为 json_object
        if Config.GRAPHITI_LLM_BACKEND == "deepseek":
            self._patch_graphiti_for_deepseek(graphiti_llm_client)

        # 对话 LLM — 根据 LLM_BACKEND 切换
        chat_llm_config = LLMConfig(
            base_url=Config.resolve_base_url(),
            api_key=Config.resolve_api_key(),
            model=Config.resolve_model()
        )
        chat_llm_client = OpenAIGenericClient(config=chat_llm_config)

        # 配置 Embedding — 始终本地 Ollama
        embed_config = OpenAIEmbedderConfig(
            base_url=self.config.EMBED_BASE_URL,
            api_key=self.config.EMBED_API_KEY,
            embedding_model=self.config.EMBED_MODEL,
            embedding_dim=self.config.EMBED_DIM
        )
        embedder = OpenAIEmbedder(config=embed_config)
        self.embedder = OpenAIEmbedder(config=embed_config)

        # 配置 Reranker — 始终本地 Ollama
        rerank_config = LLMConfig(
            base_url=self.config.RERANK_BASE_URL,
            api_key=self.config.RERANK_API_KEY,
            model=self.config.RERANK_MODEL
        )
        rerank_config.cross_encoder_model = rerank_config.model
        reranker = OpenAIRerankerClient(config=rerank_config)
        self.reranker = OpenAIRerankerClient(config=rerank_config)

        self.graphiti = Graphiti(
            uri=self.config.NEO4J_URI,
            user=self.config.NEO4J_USER,
            password=self.config.NEO4J_PWD,
            llm_client=graphiti_llm_client,
            embedder=embedder,
            cross_encoder=reranker
        )
        self.graphiti.driver.database = "neo4j"
        self.chat_llm_client = chat_llm_client  # 对话 LLM（RAG / 提问用）

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

    async def check_semantic_exists(self, new_content: str, threshold: float = 0.85, existing_facts: list[str] = None):
        '''检查语义重复，支持传入已检索的 facts 避免重复 search_memory。'''
        if existing_facts is None:
            existing_facts = await self.search_memory(new_content)
        if not existing_facts:
            return False

        import math

        def cosine_sim(a, b):
            a, b = list(a), list(b)
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
            if na == 0 or nb == 0:
                return 0.0
            return dot / (na * nb)

        # 批量 embedding：new_content + 所有已有记忆，一次请求并行计算
        all_texts = [new_content] + existing_facts
        all_vecs = await self._batch_embed(all_texts)
        new_vec, fact_vecs = all_vecs[0], all_vecs[1:]

        for fact, fact_vec in zip(existing_facts, fact_vecs):
            similarity = cosine_sim(new_vec, fact_vec)
            if similarity > threshold:
                print(f"[记忆去重] 发现相似记忆: '{fact}' (相似度: {similarity:.2f})，跳过存入。")
                return True

        return False

    async def _batch_embed(self, texts: list[str]) -> list:
        '''批量 embedding，带缓存，避免重复计算。'''
        import asyncio

        results = [None] * len(texts)
        uncached_texts, uncached_indices = [], []

        for i, text in enumerate(texts):
            if text in self._embed_cache:
                results[i] = self._embed_cache[text]
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        if not uncached_texts:
            return results

        # 批量调用（embed_documents 和 client.embeddings.create 都支持列表）
        batch_vecs = await self._do_embed_batch(uncached_texts)

        for idx, vec in zip(uncached_indices, batch_vecs):
            results[idx] = vec
            self._embed_cache[uncached_texts[idx]] = vec

        return results

    async def _do_embed_batch(self, texts: list[str]):
        '''批量调用 embedder，兼容多种接口。'''
        import asyncio

        def to_list(vec):
            try:
                return list(vec)
            except Exception:
                return vec

        # 方案 A：embed_documents（支持列表）
        if hasattr(self.embedder, "embed_documents"):
            res = await self.embedder.embed_documents(texts)
            return [to_list(v) for v in res]

        # 方案 B：create_batch
        if hasattr(self.embedder, "create_batch"):
            res = await self.embedder.create_batch(texts)
            return [to_list(v) for v in res]

        # 方案 C：client.embeddings.create（OpenAI 风格）
        if hasattr(self.embedder, "client") and hasattr(self.embedder.client, "embeddings"):
            client = self.embedder.client
            model = getattr(getattr(self.embedder, "config", None), "embedding_model", None)
            res = await client.embeddings.create(input=texts, model=model)
            return [to_list(d.embedding) for d in res.data]

        # 兜底：逐条调用 create
        if hasattr(self.embedder, "create"):
            results = []
            for t in texts:
                fn = self.embedder.create
                if asyncio.iscoroutinefunction(fn):
                    r = await fn(t)
                else:
                    r = fn(t)
                if isinstance(r, list) and r and isinstance(r[0], (list, tuple)):
                    results.append(to_list(r[0]))
                else:
                    results.append(to_list(r))
            return results

        raise AttributeError("embedder 无已知批量接口")

    @staticmethod
    def _patch_graphiti_for_deepseek(client):
        """DeepSeek 不支持 json_schema，降级为 json_object + 将 schema 注入 prompt。"""
        import json
        import types
        from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS
        from graphiti_core.llm_client.config import ModelSize

        _original = client._generate_response

        async def _patched(self, messages, response_model=None, max_tokens=DEFAULT_MAX_TOKENS, model_size=ModelSize.medium):
            if response_model is not None:
                schema = response_model.model_json_schema()
                schema_hint = (
                    f"\nYou MUST respond in valid JSON format matching this schema exactly:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n"
                    f"Do NOT wrap in markdown code blocks. Output ONLY the JSON object."
                )
                messages[-1].content += schema_hint
            else:
                messages[-1].content += "\nRespond in JSON format. Output ONLY the JSON object."

            return await _original(messages, None, max_tokens, model_size)

        client._generate_response = types.MethodType(_patched, client)

    async def close(self):
        """
        关闭 Graphiti 连接。
        释放资源。
        :return: None
        """
        if self.graphiti:
            await self.graphiti.close()