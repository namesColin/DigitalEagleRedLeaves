"""规划层：LLM 任务分解 + 编排视觉→匹配→执行闭环"""
import json
from . import executor

PLAN_PROMPT = """你是一个桌面自动化规划器。将用户意图分解为具体操作步骤。

【意图】{intent}

【规则】
1. 每步描述具体可视觉定位: "点击 Chrome 图标" 而非 "打开浏览器"
2. 操作类型: click(点击), type(输入), press(按键), hotkey(组合键), scroll, wait
3. 考虑布局: 先找输入框再打字
4. 只输出 JSON 数组:
[{{"step":1, "goal":"点击Chrome图标", "action":"click"}}, ...]"""


async def plan(intent: str, llm_client) -> list[dict]:
    prompt = PLAN_PROMPT.format(intent=intent)
    resp = await llm_client.client.chat.completions.create(
        model=llm_client.model or "deepseek-v4-pro",
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1].rstrip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [{"step": 1, "goal": intent, "action": "click"}]


async def execute_step(step: dict, vision_module, matcher, llm_client,
                       text: str = None) -> bool:
    """截图→视觉→匹配→执行，单步。"""
    goal, action = step.get("goal", ""), step.get("action", "click")

    if action in ("click", "type"):
        screenshot = executor.screenshot()
        vision_result = await vision_module.analyze(screenshot, "<OD>")
        target = await matcher.find_element(goal, vision_result, llm_client)
        if target is None:
            print(f"  ⚠ 未匹配: {goal}")
            return False
        bbox = target.get("bbox")
        if bbox is None:
            return False
        if action == "click":
            executor.click_center(bbox)
        elif action == "type":
            executor.click_center(bbox)
            executor.wait(0.2)
            executor.type_text(text or "")
        print(f"  ✅ {action} {goal}")

    elif action == "press":
        executor.press(step.get("key", "enter"))
    elif action == "hotkey":
        executor.hotkey(*step.get("keys", ["ctrl", "c"]))
    elif action == "scroll":
        executor.scroll(step.get("amount", 3))
    elif action == "wait":
        executor.wait(step.get("seconds", 1))

    return True


async def run(intent: str, text: str, vision_module, llm_client) -> dict:
    """完整执行: 规划→逐步执行→返回结果。"""
    from .matcher import find_element

    steps = await plan(intent, llm_client)
    print(f"📋 {len(steps)} 步: {[s['goal'][:40] for s in steps]}")

    done = 0
    for step in steps:
        if await execute_step(step, vision_module, find_element, llm_client,
                              text=text if step["action"] == "type" else None):
            done += 1
        executor.wait(1)

    return {"success": done == len(steps), "steps_done": done,
            "total_steps": len(steps)}
