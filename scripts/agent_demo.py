"""视觉 Agent：Qwen看图 + DeepSeek决策 + OmniParser定位"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from openai import AsyncOpenAI
from vision.vision_model_v2 import VisionModuleV2
from vision.agent import VisionAgent
from core.config import Config
from core.brain_engine import HongYeBrain

async def main():
    print("=== 视觉 Agent (Qwen+DeepSeek+OmniParser) ===\n")
    print("加载 OmniParser + 大脑 + Qwen ...")
    vision = VisionModuleV2()
    brain = HongYeBrain(); await brain.initialize()
    qwen = AsyncOpenAI(api_key=Config.GLM_API_KEY, base_url=Config.GLM_BASE_URL)
    print("✅\n")

    agent = VisionAgent(vision, qwen_client=qwen, ds_client=brain.chat_llm_client)
    goal = input("目标: ").strip() or "打开Chrome进入bilibili主页"
    r = await agent.run(goal)
    print(f"\n{'✅' if r['success'] else '⚠'} {r['steps']}步")
    await brain.close()

if __name__ == "__main__":
    asyncio.run(main())
