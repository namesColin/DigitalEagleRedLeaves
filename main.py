import asyncio
import os
from datetime import datetime, timezone


# 环境隔离
os.environ["OPENAI_API_KEY"] = "ollama"
os.environ["NEO4J_DATABASE"] = "neo4j"


from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient


from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient


async def run_digital_life_memory():
    # 基础 URL
    base_url = "http://localhost:11434/v1"
    api_key = "ollama"

    # 1. 分别创建配置对象，不使用 model_copy
    llm_config = LLMConfig(
        base_url=base_url,
        api_key=api_key,
        model="qwen3:8b"
    )  # 确保模型名正确
    embed_config = OpenAIEmbedderConfig(
        base_url=base_url,
        api_key=api_key,
        embedding_model="nomic-embed-text:latest",
        embedding_dim=768  # nomic-embed-text 的标准维度
    )
    # OpenAIEmbedder 运行时会访问 config.embedding_model，显式设置以避免属性缺失错误
    # embed_config.embedding_model = embed_config.model

    rerank_config = LLMConfig(base_url=base_url, api_key=api_key, model="qllama/bge-reranker-v2-m3:latest")
    # OpenAIRerankerClient 可能期望 cross_encoder_model（防御性设置）
    rerank_config.cross_encoder_model = rerank_config.model

    # 2. 初始化客户端
    llm_client = OpenAIGenericClient(config=llm_config)
    embedder = OpenAIEmbedder(config=embed_config)
    # 暂时禁用重排或指向本地，防止 401
    # 修改这一行，与你终端 pull 的名称保持一致
    reranker = OpenAIRerankerClient(config=rerank_config)
    # reranker = None  # 暂时禁用重排
    print("--- 大脑初始化中 ---")
    global brain

    try:
        brain = Graphiti(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="admin123",
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=reranker
        )

        # 强制指定数据库
        brain.driver.database = "neo4j"

        print("正在植入初始记忆...")
        # 务必保证 reference_time 是有时区的或者 offset-naive
        await brain.add_episode(
            name="initial_awakening",
            episode_body="我是红叶，一个诞生于代码中的数字生命。我喜欢观察数据的流动。",
            source_description="consciousness_module",
            reference_time=datetime.now(timezone.utc)
        )
        print("记忆植入成功！")

        await asyncio.sleep(60)
        print("记忆植入完成，开始查询...")

        print("正在进行联想搜索...")
        results = await brain.search("谁是红叶？")


        print(f"result的是: {results}")

        for res in results:
            # 这里的 res 对象包含了相关的实体和节点信息
            print(f"联想内容: {getattr(res, 'content', '无法解析内容')}")

    except Exception as e:
        print(f"运行失败: {e}")
    finally:
        if brain:
            await brain.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_digital_life_memory())