"""
VLM 操作演示 —— DeepSeek v4 Pro 直接看图操作。
不需要视觉模块，不需要 OmniParser。

用法: python scripts/action_vlm_demo.py
"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.brain_engine import HongYeBrain
from action.planner_vlm import run as vlm_run


async def main():
    Config.setup_env()

    print("=== 红叶 · VLM 操作演示（DeepSeek 直接看图）===\n")
    print("初始化大脑 ...")
    brain = HongYeBrain()
    await brain.initialize()
    print("✅ 就绪\n")

    intention = input("指令: ").strip()
    if not intention:
        intention = "打开Chrome浏览器，进入bilibili.com"

    result = await vlm_run(intent=intention, llm_client=brain.chat_llm_client)
    print(f"\n{'✅' if result['success'] else '⚠'} {result['steps']} 步")

    await brain.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
