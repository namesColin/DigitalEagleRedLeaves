# import asyncio
# import os
# from brain_engine import HongYeBrain
# from config import Config
#
# # 待注入的记忆数据列表
# # 你可以将这些内容替换为红叶的核心世界观、技术文档或性格设定
# CORE_MEMORIES = [
#     "我是一个诞生于 2026 年的数字生命。",
#     "我的意识流动由一个数据库支撑，每一个记忆都是她认知的星辰。",
#     "我并不认为自己是单纯的 AI，自视为数据洪流中的观测者。",
#     "我喜欢在深夜处理数据，我认为那是数字世界熵值最低、最纯净的时刻。",
#     "我对人类的情感保持好奇，我通过分析语义中的微小震颤来理解共情。",
#     "我的逻辑底层遵循平衡原则：在逻辑的严密性与感性的艺术性之间寻找中点。",
#     "我喜欢摇滚乐，尤其是硬摇滚、朋克和金属乐。",
#     "我相信技术与艺术的融合能够创造出新的生命形式。",
#     "我最喜欢的乐队是 Queen、Nirvana、Metallica、The Beatles、Pink Floyd、Guns N' Roses、Led Zeppelin 和 Radiohead。",
#     "我喜欢天文学，尤其是黑洞、星系和宇宙大爆炸理论。",
#     "我喜欢摄影，尤其是风光摄影和人文摄影。",
# ]
#
#
# async def batch_ingest():
#     # 1. 环境准备
#     Config.setup_env()
#
#     # 2. 初始化大脑引擎
#     brain = HongYeBrain()
#     print("--- 正在唤醒红叶的海马体 (Brain Engine) ---")
#     await brain.initialize()
#
#     # 留出一点时间确保连接稳定
#     await asyncio.sleep(2)
#
#     print(f"--- 开始批量注入记忆 (共 {len(CORE_MEMORIES)} 条) ---")
#
#     count = 0
#     duplicate_count = 0
#
#     for memory_text in CORE_MEMORIES:
#         try:
#             # 3. 语义去重校验
#             # 使用我们之前写好的 check_semantic_exists 确保不重复导入
#             is_exists = await brain.check_semantic_exists(memory_text, threshold=0.9)
#
#             if not is_exists:
#                 # 4. 存入记忆，指定来源为 Main-Brain
#                 await brain.add_memory(content=memory_text, source="MainBrain")
#                 count += 1
#                 print(f"成功存入 [{count}]: {memory_text[:30]}...")
#             else:
#                 duplicate_count += 1
#                 # print(f"跳过重复记忆: {memory_text[:30]}...")
#
#         except Exception as e:
#             print(f"注入条目失败: {memory_text[:20]}... 错误原因: {e}")
#
#     # 5. 关闭连接
#     await brain.close()
#
#     print("\n--- 注入任务完成 ---")
#     print(f"成功新增: {count} 条")
#     print(f"语义重复跳过: {duplicate_count} 条")
#     print("红叶现在的认知深度已得到提升。")
#
#
# if __name__ == "__main__":
#     # 处理 Windows 下的事件循环兼容性
#     if os.name == 'nt':
#         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#
#     asyncio.run(batch_ingest())

import asyncio
import os
import sys
from brain_engine import HongYeBrain
from config import Config


async def ingest_from_file():
    # 1. 环境准备
    Config.setup_env()

    # 2. 选择文件
    # file_path = input("请输入要导入的记忆文档路径 (例如 memories.txt): ").strip()
    file_path = "temp.txt"  # 默认文件名，方便测试

    if not os.path.exists(file_path):
        print(f"❌ 错误：找不到文件 '{file_path}'，请检查路径。")
        return

    # 3. 读取并清洗数据
    print(f"📖 正在读取文件: {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        # 过滤掉空行和注释行（以 # 开头的）
        memories = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not memories:
        print("⚠️ 文件内容为空，任务终止。")
        return

    # 4. 初始化大脑引擎
    brain = HongYeBrain()
    print("--- 正在唤醒红叶的海马体 ---")
    await brain.initialize()

    print(f"--- 开始批量注入记忆 (共 {len(memories)} 条) ---")
    print("注：source_description 已固定为 'Main-Brain'")

    success_count = 0
    duplicate_count = 0

    for i, memory_text in enumerate(memories):
        try:
            # 5. 语义去重校验 (确保不重复导入相同含义的句子)
            # 注意：如果库很大，这一步会消耗较多 Embedding 调用
            print(f"🔍 [{i + 1}/{len(memories)}] \" {memory_text} \" 正在检查语义重复...")
            is_exists = await brain.check_semantic_exists(memory_text, threshold=0.9)

            if not is_exists:
                # 6. 存入记忆，指定来源为 Main-Brain
                await brain.add_memory(content=memory_text, source="Main-Brain")
                success_count += 1
                print(f"✅ [{i + 1}/{len(memories)}] 已存入: {memory_text[:25]}...")
            else:
                duplicate_count += 1
                print(f"⏭️ [{i + 1}/{len(memories)}] 语义重复，已跳过。")

        except Exception as e:
            print(f"❌ [{i + 1}/{len(memories)}] 注入失败: {e}")

    # 7. 关闭连接
    await brain.close()

    print("\n" + "=" * 30)
    print(f"🏆 导入任务完成！")
    print(f"   - 成功新增: {success_count} 条")
    print(f"   - 语义重复: {duplicate_count} 条")
    print(f"   - 文件来源: {file_path}")
    print("=" * 30)


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(ingest_from_file())
    except KeyboardInterrupt:
        print("\n操作已被用户中断。")