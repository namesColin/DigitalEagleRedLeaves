"""Qwen3.7-Plus GUI Agent 演示 —— 截图直接输出像素坐标"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from action.planner_qwen37 import run

async def main():
    print("=== Qwen3.7-Plus GUI Agent ===\n")
    i = input("指令: ").strip() or "打开Chrome进入bilibili主页"
    r = await run(intent=i)
    print(f"\n{'✅' if r['success'] else '⚠'} {r['steps']} 步")

if __name__ == "__main__":
    asyncio.run(main())
