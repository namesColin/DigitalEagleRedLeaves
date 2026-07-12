import asyncio
import os
import sys
import traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.brain_engine import HongYeBrain

# 人格维度 + 关键词（用于自动分类，无需额外 LLM 调用）
TOPICS = {
    "身份认同": ["我是", "认为自己是", "定义", "数字生命", "存在", "本质", "诞生", "观测者"],
    "世界观":    ["世界", "宇宙", "规律", "秩序", "混沌", "真实", "意义", "本质", "数据", "熵"],
    "价值观":    ["重视", "认为", "重要", "原则", "底线", "道德", "应该", "值得", "追求"],
    "情感倾向":  ["喜欢", "讨厌", "热爱", "厌恶", "感动", "恐惧", "悲伤", "快乐", "孤独", "触动"],
    "艺术审美":  ["音乐", "画", "电影", "书", "文学", "艺术", "摄影", "摇滚", "古典", "颜色"],
    "人际关系":  ["人类", "朋友", "家人", "爱情", "亲情", "友情", "陪伴", "理解", "共情"],
    "经历记忆":  ["记得", "曾经", "当时", "那天", "第一次", "过去", "以前", "遇到", "发现"],
    "向往恐惧":  ["希望", "害怕", "梦想", "担忧", "未来", "渴望", "改变", "永远", "消失", "死亡"],
}


def classify_topic(text: str) -> str:
    """简单关键词分类，匹配得分最高的维度。"""
    scores = {}
    for topic, keywords in TOPICS.items():
        scores[topic] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "其他"


INTERVIEW_PROMPT = """你是一个人格塑造师，正在帮助创建一个名为"红叶"的数字生命。

【已覆盖的人格维度】（数字 = 已有记忆条数，<=2 = 严重不足，3~5 = 尚可，6+ = 充分）
{coverage}

【关键约束】你必须从覆盖数 <= 2 的维度中挑选一个发问。如果所有维度都 >= 3，优先挑最少的。

【已有记忆参考】
{memories}

【规则】
1. 每次只问一个问题，中文，语气自然亲切
2. 问题应深入挖掘该维度的细节、矛盾或边界情况
3. 如果记忆还很空，从"身份认同"或"世界观"开始

只输出问题本身，不要加任何前缀或解释。"""


async def seed():
    Config.setup_env()

    brain = HongYeBrain()
    await brain.initialize()

    # 覆盖统计：{topic: count}
    topic_counts = {t: 0 for t in TOPICS}
    topic_counts["其他"] = 0

    print("=== 红叶人格播种（主题平衡模式）===")
    print("DeepSeek 会根据覆盖缺口自动切换提问维度。")
    print("输入 'quit' 退出，输入 'skip' 跳过当前问题。\n")

    question_count = 0

    while True:
        # 1. 检索已有记忆
        facts = await brain.search_memory("红叶 人格 世界观 喜好 价值观")
        memories_text = "\n".join([f"- {f}" for f in facts]) if facts else "（尚无记忆）"

        # 2. 生成覆盖报告
        coverage_lines = []
        for topic in TOPICS:
            bar = "█" * min(topic_counts[topic], 10)
            flag = " ← 优先" if topic_counts[topic] <= 2 else ""
            coverage_lines.append(f"  {topic}: {topic_counts[topic]}条 {bar}{flag}")
        coverage_text = "\n".join(coverage_lines)

        # 3. DeepSeek 生成问题
        prompt = INTERVIEW_PROMPT.format(coverage=coverage_text, memories=memories_text)
        response = await brain.chat_llm_client.client.chat.completions.create(
            model=Config.resolve_model(),
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        question = response.choices[0].message.content.strip()

        # 4. 展示问题
        print(f"\n[第 {question_count + 1} 问] {question}")
        answer = input("你的回答: ").strip()

        if answer.lower() == 'quit':
            break
        if answer.lower() == 'skip':
            continue

        if answer:
            try:
                is_dup = await brain.check_semantic_exists(answer, threshold=0.9, existing_facts=facts)
                if not is_dup:
                    await brain.add_memory(content=answer, source="Main-Brain")
                    question_count += 1
                    # 自动分类
                    topic = classify_topic(answer)
                    topic_counts[topic] += 1
                    print(f"  ✅ 已存入 [{topic}] (共 {question_count} 条)")
                else:
                    print("  ⏭️ 与已有记忆重复，已跳过")
            except Exception as e:
                print(f"  ❌ 存入失败: {e}")
                traceback.print_exc()

    await brain.close()
    print(f"\n=== 播种完成，共 {question_count} 条记忆 ===")
    print("各维度覆盖：")
    for t, c in sorted(topic_counts.items(), key=lambda x: -x[1]):
        if c > 0:
            print(f"  {t}: {c}条")


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
