"""
VLM 规划器：截图 → base64 → DeepSeek v4 Pro 看图 → 直接输出像素坐标。

核心理念：LLM 能直接"看见"屏幕，不需要 OmniParser，不需要白名单规则。
"""
import json, io, base64
from . import executor

VLM_PROMPT = """你是 Windows 桌面操作助手。你能看到屏幕截图。

【用户目标】{intent}

【操作历史】{history}

请仔细观察截图，完成一步操作：

1. 描述你看到了什么（当前屏幕状态，有哪些关键元素）

2. 选择下一步操作并输出 JSON：
{{
  "screen": "Chrome用户选择界面，左边是Colins头像，右边是Guest头像",
  "action": "click", "x": 350, "y": 420,
  "reason": "点击Colins的头像"
}}

{{
  "screen": "Chrome已打开，地址栏在顶部中央",
  "action": "click", "x": 600, "y": 55,
  "reason": "点击地址栏准备输入网址"
}}

{{
  "screen": "有两个账号头像，不确定哪个是Colins",
  "action": "ask", "question": "选择左边还是右边的账号？"
}}

可用操作:
- click(x,y):    点击像素坐标
- type("text"):  在当前焦点输入（先 click 输入框）
- press("enter"): 按键
- hotkey(["win","r"]): 组合键
- win_search("chrome"): Win键搜索
- scroll(n):     滚动
- wait(n):       等待n秒
- ask("问题"):   不确定时问用户
- done("原因"):  任务完成

注意:
- x,y 是屏幕像素坐标
- 输入框先点击再 type
- 不确定就 ask，不要猜
- 地址栏通常在浏览器顶部中间"""


def _img_b64(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1].rstrip("```").strip()
    try: return json.loads(raw)
    except json.JSONDecodeError: return {"action": "done", "reason": "parse_error"}


def _execute(action: dict) -> str:
    act = (action.get("action") or "").lower()
    reason = action.get("reason", "")

    if act == "click":
        x, y = action.get("x"), action.get("y")
        if x is not None and y is not None:
            executor.click_at(int(x), int(y))
            return f"点击({int(x)},{int(y)}) → {reason}"
        return f"click缺少坐标"

    elif act == "type":
        executor.type_text(action.get("text", ""))
        return f"输入: {action.get('text', '')}"

    elif act == "press":
        executor.press(action.get("key", "enter"))
        return f"按键: {action.get('key', 'enter')}"

    elif act in ("hotkey", "shortcut"):
        executor.hotkey(*(action.get("keys") or [action.get("key", "win")]))
        return f"组合键"

    elif act in ("win_search", "search"):
        q = action.get("query", "")
        executor.hotkey("win"); executor.wait(0.4)
        executor.type_text(q); executor.wait(0.3)
        executor.press("enter")
        return f"Win搜索: {q}"

    elif act == "scroll":
        executor.scroll(action.get("n", 3))
        return f"滚动{action.get('n',3)}"

    elif act == "wait":
        executor.wait(action.get("seconds", 1))
        return f"等待{action.get('seconds',1)}s"

    elif act in ("ask", "ask_user"):
        return f"ASK: {action.get('question', reason)}"

    elif act in ("done", "finish"):
        return f"DONE: {reason}"

    return f"未知操作: {act}"


async def run(intent: str, llm_client, max_steps: int = 12) -> dict:
    """VLM 闭环：截图→DeepSeek看图→坐标→执行→重复。"""
    history, log = [], []

    for step in range(1, max_steps + 1):
        print(f"\n--- 第 {step} 步 ---")

        img = executor.screenshot()
        b64 = _img_b64(img)

        prompt = VLM_PROMPT.format(
            intent=intent,
            history="\n".join(history[-5:]) if history else "（首次）",
        )
        resp = await llm_client.client.chat.completions.create(
            model=llm_client.model or "deepseek-v4-pro",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            stream=False,
        )
        action = _parse(resp.choices[0].message.content)

        print(f"  {action.get('screen', '?')}")
        print(f"  → {action.get('action')}: {action.get('reason', '')}")

        # ask_user
        if action.get("action") in ("ask", "ask_user"):
            q = action.get("question", "请问？")
            ans = input(f"\n  🤔 红叶问: {q}\n  你回答: ").strip()
            history.append(f"Step{step}: 红叶问「{q}」答「{ans}」")
            log.append({"step": step, "action": "ask", "q": q, "a": ans})
            continue

        # execute
        result = _execute(action)
        history.append(f"Step{step}: {result}")
        log.append({"step": step, "action": action.get("action"), "result": result})

        if action.get("action") in ("done", "finish"):
            print(f"\n✅ {result}")
            return {"success": True, "log": log, "steps": step}

        executor.wait(1)

    return {"success": False, "log": log, "steps": max_steps}
