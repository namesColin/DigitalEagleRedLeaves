"""视觉 Agent 演示"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from vision.vision_model_v2 import VisionModuleV2
from vision.agent import VisionAgent

async def main():
    print("=== 视觉 Agent ===\n")
    print("加载 OmniParser V2 ...")
    v = VisionModuleV2()
    a = VisionAgent(v)
    g = input("目标: ").strip() or "打开Chrome进入bilibili主页"
    r = await a.run(g)
    print(f"\n{'✅' if r['success'] else '⚠'} {r['steps']}步")

if __name__ == "__main__":
    asyncio.run(main())
