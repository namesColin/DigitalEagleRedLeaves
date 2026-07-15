"""分层感知 Agent 演示 — CDP + UIA + Cursor + SoM"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from openai import AsyncOpenAI
from vision.vision_model_v2 import VisionModuleV2
from perception.layered_agent import LayeredAgent
from core.config import Config
from core.brain_engine import HongYeBrain


async def main():
    print("Loading OmniParser + Brain + Qwen ...")
    vision = VisionModuleV2()
    brain = HongYeBrain()
    await brain.initialize()
    qwen = AsyncOpenAI(api_key=Config.GLM_API_KEY, base_url=Config.GLM_BASE_URL)
    goal = input("Goal: ").strip() or "open a browser and search for AI news"

    agent = LayeredAgent(vision, qwen_client=qwen, ds_client=brain.chat_llm_client)
    try:
        r = await agent.run(goal, max_steps=15)
        print(f"\n{'OK' if r['success'] else 'FAIL'} {r['steps']} steps")
        print(f"Layer stats: {r.get('stats', {})}")
        for h in r.get('log', []):
            print(f"  Step {h['step']}: [{h['layer']}] {h['action']} -> {h['result'][:100]}")
    finally:
        await agent.close()
        await brain.close()


if __name__ == "__main__":
    asyncio.run(main())
