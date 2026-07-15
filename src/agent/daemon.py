"""
守护进程入口 — 组装依赖、连接 Chrome、启动 IPC。
单一职责：初始化 + 生命周期管理。
"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from openai import AsyncOpenAI
from vision.vision_model_v2 import VisionModuleV2
from core.brain_loop import BrainLoop
from core.config import Config
from core.brain_engine import HongYeBrain
from perception.uia_scanner import UiaScanner
from perception.som_grounding import SomGrounding
from perception.cursor_explorer import CursorExplorer
from perception.desktop_state import DesktopState
from action.chrome_driver import ChromeDriver
from action.matcher import ElementMatcher
from action.planner import ActionPlanner
from agent.task_runner import TaskRunner
from agent.ipc_server import IpcServer


async def main():
    print("=== Agent Daemon ===")
    vision = VisionModuleV2()
    brain = HongYeBrain()
    await brain.initialize()
    qwen = AsyncOpenAI(api_key=Config.GLM_API_KEY, base_url=Config.GLM_BASE_URL)

    chrome = ChromeDriver()
    uia = UiaScanner()
    matcher = ElementMatcher(
        ds_client=brain.chat_llm_client, qwen_client=qwen, uia=uia)
    planner = ActionPlanner(
        cdp=chrome, matcher=matcher, vision=vision, qwen=qwen,
        ds=brain.chat_llm_client, uia=uia,
        som=SomGrounding(qwen_client=qwen),
        cursor=CursorExplorer(qwen_client=qwen))
    state = DesktopState()
    agent = BrainLoop(vision, qwen_client=qwen,
                      ds_client=brain.chat_llm_client,
                      planner=planner, state=state)
    runner = TaskRunner(agent)
    ipc = IpcServer(runner)

    asyncio.create_task(runner.start())
    await ipc.start()

    print("Ready. Send goals: python -m agent.cli \"<goal>\"")
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await agent.close()
        await brain.close()


if __name__ == "__main__":
    asyncio.run(main())
