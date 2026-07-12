"""
操作模块演示 —— 给红叶下达操作指令，自动执行。

用法:
  1. 启动视觉服务: python src/vision/vision_server.py
  2. 运行这个:      python scripts/action_demo.py
"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.brain_engine import HongYeBrain
from vision.vision_model_v2 import VisionModuleV2
from action.planner import run as action_run


async def main():
    Config.setup_env()

    print("=== 红叶 · 操作模块演示 ===\n")
    print("初始化大脑 ...")
    brain = HongYeBrain()
    await brain.initialize()

    print("加载视觉模块 ...")
    vision = VisionModuleV2()

    print("✅ 就绪\n")
    intention = input("指令（如: 打开浏览器搜索XX）: ").strip()
    if not intention:
        print("未输入指令，使用默认演示: 打开文件管理器")
        intention = "在任务栏找到并点击文件管理器图标"

    print()
    result = await action_run(intent=intention, text="", vision_module=vision,
                              llm_client=brain.chat_llm_client)

    print(f"\n{'✅ 完成' if result['success'] else '⚠ 部分完成'} "
          f"({result['steps_done']}/{result['total_steps']} 步)")

    await brain.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
