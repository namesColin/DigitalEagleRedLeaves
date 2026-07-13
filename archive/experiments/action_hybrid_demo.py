"""混合操作演示：Qwen看图 + DeepSeek决策 + OmniParser定位"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from core.config import Config
from core.brain_engine import HongYeBrain
from action.planner_hybrid import run


async def main():
    Config.setup_env()
    print("=== 红叶 · 混合操作演示（Qwen看图 + DeepSeek决策）===\n")
    brain = HongYeBrain(); await brain.initialize()
    print("✅\n")
    i = input("指令: ").strip() or "打开Chrome进入bilibili主页"
    r = await run(intent=i, llm_client=brain.chat_llm_client)
    print(f"\n{'✅' if r['success'] else '⚠'} {r['steps']} 步")
    await brain.close()

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
