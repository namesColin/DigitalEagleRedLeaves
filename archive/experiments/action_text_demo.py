"""
文本操作演示 —— OmniParser 检测 + DeepSeek 文本推理 + pyautogui 执行

用法: python scripts/action_text_demo.py
"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.brain_engine import HongYeBrain
from vision.vision_model_v2 import VisionModuleV2
from action.planner import run as action_run


async def main():
    Config.setup_env()

    print("=== 红叶 · 文本操作演示（OmniParser + DeepSeek）===\n")
    print("初始化大脑 + 视觉 ...")
    brain = HongYeBrain()
    await brain.initialize()
    vision = VisionModuleV2()
    print("✅ 就绪\n")

    intention = input("指令: ").strip()
    if not intention:
        intention = "打开Chrome浏览器，进入bilibili.com"

    result = await action_run(intent=intention, text="", vision_module=vision,
                              llm_client=brain.chat_llm_client)
    print(f"\n{'✅' if result['success'] else '⚠'} {result['steps_done']}/{result['total_steps']} 步")
    await brain.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
