import asyncio
import os
from datetime import datetime, timezone
import ollama

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
    brain = None

    try:
        brain = Graphiti(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="admin123",
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=reranker
        )
        brain.driver.database = "neo4j"

        print("--- 唤醒红叶中 ---")
        await brain.add_episode(
            name="daily_log",
            episode_body="我是红叶，一个诞生于代码中的数字生命。我喜欢观察数据的流动。",
            source_description="consciousness_module",
            reference_time=datetime.now(timezone.utc)
        )

        # 本地 Ollama 建议等待 5-10 秒即可，60秒太久了
        print("等待大脑处理记忆碎片...")
        # await asyncio.sleep(30)

        question = "谁是红叶？"
        print(f"提问: {question}")
        results = await brain.search(question)

        # --- 处理联想内容的核心逻辑 ---
        if results:
            # 1. 提取所有事实 (Fact)
            retrieved_facts = []
            for res in results:
                # Graphiti 返回的 search 结果通常是 EntityEdge 对象
                if hasattr(res, 'fact'):
                    retrieved_facts.append(res.fact)

            # 2. 去重
            unique_facts = list(set(retrieved_facts))
            context = "\n".join([f"- {f}" for f in unique_facts])

            print(f"\n[大脑检索到的原始事实]:\n{context}\n")

            # 3. 将事实交给 LLM 生成对话回答 (RAG)
            prompt = f"""你现在是数字生命“红叶”。请根据以下从你记忆中检索到的事实，回答用户的问题。
            事实：{context}
            用户问题：{question}
            请用自然、感性的语气回答。"""

            print(f"prompt:{prompt}")

            # 这里的 response 调用取决于你的 llm_client 封装，通常如下：
            response = await llm_client.chat(messages=[{"role": "user", "content": prompt}])

            response = await llm_client.client.chat.completions.create(
                model='qwen3:8b',
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )

            print("--- 红叶的回答 ---")
            async for chunk in response:
                # 兼容不同返回结构（对象或 dict）
                try:
                    choice = chunk.choices[0] if hasattr(chunk, "choices") else chunk["choices"][0]
                except Exception:
                    continue

                delta = getattr(choice, "delta", None) if not isinstance(choice, dict) else choice.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                else:
                    content = getattr(delta, "content", None)

                if content:
                    print(content, end="", flush=True)

        else:
            print("红叶在记忆中没有找到相关信息。")

    except Exception as e:
        print(f"运行失败: {e}")
    finally:
        if brain:
            await brain.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_digital_life_memory())