import asyncio
import os
import sys

# 兼容直接运行（python chat.py）和模块运行（python -m src.core.chat）
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.config import Config
    from core.brain_engine import HongYeBrain
    from core.personality import HongYePersonality
else:
    from .config import Config
    from .brain_engine import HongYeBrain
    from .personality import HongYePersonality

async def main():

    # 设置环境变量
    Config.setup_env()

    # 初始化大脑引擎
    brain = HongYeBrain()
    await brain.initialize()

    # 初始化红叶个性化模块
    hongye = HongYePersonality(brain)

    print("--- 红叶已苏醒 (输入 'quit' 退出) ---")

    while True:
        user_input = input("\n你: ")
        if user_input.lower() == 'quit':
            break

        print("红叶: ", end="", flush=True)
        response_stream = await hongye.chat(user_input)

        full_response = ""  # 定义完整回复
        async for chunk in response_stream:
            content = chunk.choices[0].delta.content if chunk.choices[0].delta.content else ""
            print(content, end="", flush=True)
            full_response += content  # 拼接
        print()

        # 1. 记住用户说的话 (如果没听过类似的)
        await hongye.remember_dialogue(user_input, source="human_user")

        # 2. 记住红叶自己说的话 (防止自我重复，也作为性格积累)
        await hongye.remember_dialogue(content, source="hongye_response")

    await brain.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())