import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.brain_engine import HongYeBrain

INTERVIEW_PROMPT = """你是一个人格塑造师，正在帮助创建一个名为"红叶"的数字生命。

红叶已有的性格记忆：
{memories}

请根据已有记忆，生成下一个深度访谈问题。规则：
1. 问题应引导用户补充红叶的世界观、价值观、喜好、经历、信念、情感倾向等
2. 不要重复已有记忆中已充分覆盖的话题
3. 每次只问一个问题，用中文，语气自然亲切
4. 如果记忆还很空，从基础身份开始问（"红叶认为自己是什么？"）
5. 如果记忆已丰富，深入挖掘矛盾或细节
6. 最多问 3 个关于音乐/艺术偏好的问题（这些容易重复）

只输出问题本身，不要加任何前缀或解释。"""


async def seed():
    Config.setup_env()

    # 初始化大脑
    brain = HongYeBrain()
    await brain.initialize()
    print("=== 红叶人格播种 ===")
    print("DeepSeek 会不断问你关于红叶的问题，你的回答将构成她的人格记忆。")
    print("输入 'quit' 退出，输入 'skip' 跳过当前问题。\n")

    question_count = 0

    while True:
        # 1. 检索已有 Main-Brain 记忆
        facts = await brain.search_memory("红叶 人格 世界观 喜好 价值观")
        memories_text = "\n".join([f"- {f}" for f in facts]) if facts else "（尚无记忆，请从基础身份开始提问）"

        # 2. DeepSeek 生成下一个问题
        prompt = INTERVIEW_PROMPT.format(memories=memories_text)
        response = await brain.chat_llm_client.client.chat.completions.create(
            model=Config.resolve_model(),
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        question = response.choices[0].message.content.strip()

        # 3. 展示问题，等待用户回答
        print(f"\n[第 {question_count + 1} 问] {question}")
        answer = input("你的回答: ").strip()

        if answer.lower() == 'quit':
            break
        if answer.lower() == 'skip':
            continue

        # 4. 存入记忆
        if answer:
            try:
                is_dup = await brain.check_semantic_exists(answer, threshold=0.9)
                if not is_dup:
                    await brain.add_memory(content=answer, source="Main-Brain")
                    question_count += 1
                    print(f"  ✅ 已存入 (共 {question_count} 条)")
                else:
                    print("  ⏭️ 与已有记忆重复，已跳过")
            except Exception as e:
                print(f"  ❌ 存入失败: {e}")

    await brain.close()
    print(f"\n=== 播种完成，共存入 {question_count} 条人格记忆 ===")


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
