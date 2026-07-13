"""规划层：感知-行动闭环。每轮截屏→视觉→LLM决定下一步→执行→验证。"""
import json, os
from PIL import ImageDraw, ImageFont
from . import executor
from .matcher import format_elements


def _save_debug_image(screenshot, vision_result, step_num):
    """保存标注截图到 outputs/debug_steps/ 供人工核查。"""
    try:
        img = screenshot.copy()
        draw = ImageDraw.Draw(img)
        try: font = ImageFont.truetype("msyh.ttc", 16)
        except: font = ImageFont.load_default()
        boxes = vision_result.get("boxes", [])
        labels = vision_result.get("labels", [])
        colors = ["lime", "cyan", "yellow", "magenta", "orange", "red"]
        for i, (box, label) in enumerate(zip(boxes, labels)):
            if len(box) != 4: continue
            x1, y1, x2, y2 = [int(v) for v in box]
            c = colors[i % len(colors)]
            draw.rectangle([x1, y1, x2, y2], outline=c, width=2)
            draw.text((x1 + 2, max(0, y2 - 18)), str(i), fill=c, font=font)
        os.makedirs("outputs/debug_steps", exist_ok=True)
        img.save(f"outputs/debug_steps/step_{step_num:02d}.png")
    except Exception:
        pass  # 调试保存失败不阻塞主流程

STEP_PROMPT = """你是 Windows 桌面操作助手。根据当前屏幕状态，完成目标。

【用户目标】{intent}

【已尝试的步骤】{history}

【当前屏幕 UI 元素】
{elements}

【你必须】
1. 先简短描述当前屏幕是什么（浏览器主页？桌面？Chrome 用户选择界面？VS Code？开始菜单？空桌面？）
2. 再根据目标决定唯一的下一步操作

【可用操作】
{actions}

【关键策略】
1. 遇到意外的界面（用户选择、弹窗、权限确认）→ 直接点对应的按钮，不要犹豫
2. 目标 app 不在屏幕上 → win_search
3. 任务栏隐藏 → move_to_bottom
4. 地址栏/搜索框 → 找窗口顶部长条输入框
5. 目标已达成 → done
6. 连续操作同一步超过 2 次没变化 → 换策略

请输出 JSON（包含 screen_state 和下一步操作）:
{{"screen_state": "Chrome 用户选择界面", "action": "click", "target_id": 3}}
{{"screen_state": "空桌面", "action": "win_search", "query": "chrome"}}
{{"screen_state": "已显示bilibili主页", "action": "done", "reason": "任务完成"}}"""


ACTIONS_HELP = """- action="click"        target_id=<编号>
- action="type"         target_id=<编号> text="<输入内容，支持中文>"
- action="press"        key="<键名>"
- action="hotkey"       keys=["组合","键"]
- action="win_search"   query="<关键词>"
- action="move_to_bottom"
- action="wait"         seconds=1
- action="ask_user"     question="<问用户的问题>"  (遇到二选一、不确定时求助)
- action="done"         reason="<原因>"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rstrip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "done", "reason": "parse_error"}


def _execute_one(action: dict, vision_result: dict, step_text: str = None) -> str:
    """执行单个操作。返回描述字符串。"""
    act = (action.get("action") or "").lower().replace(" ", "_").replace("-", "_")
    reason = action.get("reason", "")

    # 兼容 LLM 可能返回的各种名称变体
    if act in ("click", "click_element"):
        tid = action.get("target_id") if "target_id" in action else action.get("element_id")
        boxes = vision_result.get("boxes", [])
        if tid is not None and 0 <= tid < len(boxes):
            executor.click_center(boxes[tid])
            return f"点击 [元素{tid}]: {reason}"
        return f"点击失败: target_id={tid} 不在 0-{len(boxes)-1} 范围"

    elif act in ("type", "input", "type_text", "write"):
        tid = action.get("target_id") if "target_id" in action else action.get("element_id")
        text = step_text or action.get("text", "") or action.get("query", "")
        boxes = vision_result.get("boxes", [])
        if tid is not None and 0 <= tid < len(boxes):
            executor.click_center(boxes[tid])
            executor.wait(0.2)
            executor.type_text(text)
            return f"输入 [元素{tid}]: {text}"
        return f"输入失败: target_id={tid}"

    elif act in ("press", "key", "enter"):
        executor.press(action.get("key", "enter"))
        return f"按键: {action.get('key', 'enter')}"

    elif act in ("hotkey", "shortcut", "combo"):
        keys = action.get("keys") or [action.get("key", "win")]
        executor.hotkey(*keys)
        return f"组合键: {'+'.join(keys)}"

    elif act in ("win_search", "search", "start_search", "win_s"):
        query = action.get("query") or action.get("text", "")
        executor.hotkey("win")
        executor.wait(0.4)
        executor.type_text(query)
        executor.wait(0.3)
        executor.press("enter")
        return f"Win 搜索: {query}"

    elif act in ("move_to_bottom", "unhide_taskbar", "show_taskbar"):
        w, h = executor.screen_size()
        executor.move_to(w // 2, h - 2)
        executor.wait(0.8)
        return "鼠标移到底部边缘"

    elif act in ("wait", "sleep"):
        executor.wait(action.get("seconds", 1))
        return f"等待 {action.get('seconds', 1)}s"

    elif act in ("ask_user", "ask", "help", "need_help"):
        return f"ASK: {reason}"

    elif act in ("done", "finish", "complete"):
        return f"DONE: {reason}"

    print(f"  ⚠ 未知操作类型 '{act}'，原始回复: {json.dumps(action, ensure_ascii=False)[:200]}")
    return f"UNKNOWN: {reason}"


async def run(intent: str, text: str, vision_module, llm_client,
              max_steps: int = 10) -> dict:
    """
    感知-行动闭环执行。

    Args:
        intent: "打开浏览器搜索bilibili"
        text: 要输入的文字
        vision_module: VisionModuleV2 实例
        llm_client: chat_llm_client
        max_steps: 最大循环次数

    Returns:
        {"success": bool, "log": [...], "steps": N}
    """
    history = []
    log = []

    for step_num in range(1, max_steps + 1):
        print(f"\n--- 第 {step_num} 步 ---")

        # 1. 截屏 + 视觉检测
        screenshot = executor.screenshot()
        w, h = screenshot.size
        vision_result = await vision_module.analyze(screenshot, "<OD>")
        elements_text = format_elements(
            vision_result.get("boxes", []),
            vision_result.get("labels", []),
            screen_w=w, screen_h=h,
        )
        _save_debug_image(screenshot, vision_result, step_num)

        # 2. LLM 决定下一步
        prompt = STEP_PROMPT.format(
            intent=intent,
            history="\n".join(history) if history else "（尚无）",
            elements=elements_text or "（未检测到任何 UI 元素）",
            actions=ACTIONS_HELP,
        )
        resp = await llm_client.client.chat.completions.create(
            model=llm_client.model or "deepseek-v4-pro",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        action = _parse_json(resp.choices[0].message.content)
        print(f"  DeepSeek 完整输出: {json.dumps(action, ensure_ascii=False)[:300]}")

        # 3. 如果是求助，暂停等用户回答
        if action.get("action") in ("ask_user", "ask", "help", "need_help"):
            question = action.get("question") or action.get("reason", "请问下一步怎么做？")
            print(f"\n  🤔 红叶问: {question}")
            user_answer = input("  你回答: ").strip()
            history.append(f"第{step_num}步: 红叶询问「{question}」，用户回答「{user_answer}」")
            log.append({"step": step_num, "action": "ask_user",
                         "question": question, "answer": user_answer})
            executor.wait(0.5)
            continue

        # 4. 执行
        result_msg = _execute_one(action, vision_result, text)
        history.append(f"第{step_num}步: {result_msg}")
        log.append({"step": step_num, "action": action.get("action"),
                     "result": result_msg})

        # 5. 是否完成
        if action.get("action") == "done":
            print(f"\n✅ {result_msg}")
            return {"success": True, "log": log, "steps": step_num}

        executor.wait(1)  # 等 UI 反应

    print(f"\n⚠ 达到最大步数 {max_steps}")
    return {"success": False, "log": log, "steps": max_steps}
