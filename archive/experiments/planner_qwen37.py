"""
Qwen3.7-Plus 原生 GUI Agent —— 截图直接输出像素坐标。
不需要 OmniParser，不需要 OCR，不需要 DeepSeek。
"""
import json, io, base64, os, sys, re
from openai import AsyncOpenAI
from . import executor

try: from ..core.config import Config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.config import Config

PROMPT = """你是桌面操作助手。请看截图完成任务。

【目标】{intent}
【已做】{history}

输出操作（一行，纯文本）:
click(487, 232)         点击像素
type("bilibili.com")    输入文字
press(enter)            按键
win_search(chrome)      Win搜索
ask(问题)               不确定
done(原因)              完成"""


def _b64(img): b=io.BytesIO(); img.save(b,format="PNG"); return base64.b64encode(b.getvalue()).decode()


def _parse(raw):
    raw = raw.strip()
    if raw.startswith("```"): raw = raw.split("\n",1)[1].rstrip("```").strip()
    raw = raw.split("\n")[0].strip()

    # click(487, 232)
    m = re.match(r'click\s*\(?\s*(\d+)\s*[,，]\s*(\d+)\s*\)?', raw, re.I)
    if m: return {"action":"click","x":int(m.group(1)),"y":int(m.group(2))}

    # type("text")
    m = re.match(r'type\s*\(\s*[""](.+?)[""]\s*\)', raw, re.I)
    if m: return {"action":"type","text":m.group(1)}

    # press(key)
    m = re.match(r'press\s*\((\w+)\)', raw, re.I)
    if m: return {"action":"press","key":m.group(1)}

    # win_search(query)
    m = re.match(r'win_search\s*\((.+?)\)', raw, re.I)
    if m: return {"action":"win_search","query":m.group(1).strip('"').strip('"').strip('"').strip('"')}

    # ask(question)
    m = re.match(r'ask\s*\((.+?)\)', raw, re.I)
    if m: return {"action":"ask","question":m.group(1).strip('"').strip("'")}

    # done(reason)
    m = re.match(r'done\s*\((.+?)\)', raw, re.I)
    if m: return {"action":"done","reason":m.group(1).strip('"').strip("'")}

    # wait(N)
    m = re.match(r'wait\((\d+)\)', raw, re.I)
    if m: return {"action":"wait","seconds":int(m.group(1))}

    # scroll(N)
    m = re.match(r'scroll\((-?\d+)\)', raw, re.I)
    if m: return {"action":"scroll","n":int(m.group(1))}

    print(f"  ⚠ 无法解析: {raw[:150]}")
    return {"action":"wait","seconds":1}


def _execute(action):
    a = action.get("action",""); r = action.get("reason","")
    if a == "click":
        x, y = action.get("x"), action.get("y")
        if x and y: executor.click_at(int(x), int(y)); return f"点击({x},{y})"
        return "缺坐标"
    elif a == "type":
        executor.type_text(action.get("text","")); return f"输入:{action.get('text','')}"
    elif a == "press":
        executor.press(action.get("key","enter")); return f"按键{action.get('key','enter')}"
    elif a == "win_search":
        q = action.get("query",""); executor.hotkey("win"); executor.wait(0.4)
        executor.type_text(q); executor.wait(0.3); executor.press("enter")
        return f"Win搜:{q}"
    elif a == "hotkey":
        executor.hotkey(*(action.get("keys") or ["win"])); return "组合键"
    elif a == "scroll":
        executor.scroll(action.get("n",3)); return f"滚{action.get('n',3)}"
    elif a == "ask": return f"ASK:{action.get('question',r)}"
    elif a == "done": return f"DONE:{r}"
    elif a == "wait": executor.wait(action.get("seconds",1)); return f"等{action.get('seconds',1)}s"
    return f"未知:{a}"


async def run(intent: str, llm_client=None, max_steps: int = 15) -> dict:
    vlm = AsyncOpenAI(api_key=Config.GLM_API_KEY, base_url=Config.GLM_BASE_URL)
    history, log = [], []

    for step in range(1, max_steps + 1):
        print(f"\n─ 第 {step} 步 ─")

        img = executor.screenshot()
        img = img.resize((img.width // 2, img.height // 2))

        prompt = PROMPT.format(
            intent=intent,
            history="\n".join(history[-5:]) if history else "（首次）",
        )
        print("  Qwen3.7-Plus...", end=" ", flush=True)
        resp = await vlm.chat.completions.create(
            model=Config.GLM_VISION_MODEL,
            messages=[{"role":"user","content":[
                {"type":"image_url","image_url":{"url":f"data:image/png;base64,{_b64(img)}"}},
                {"type":"text","text":prompt},
            ]}],
            stream=False, timeout=90,
        )
        raw = resp.choices[0].message.content.strip()
        action = _parse(raw)
        print(f"「{raw[:80]}」")

        if action.get("action") == "ask":
            q = action.get("question","？")
            a = input(f"\n  🤔 {q}\n  → ").strip()
            history.append(f"问:{q}答:{a}"); log.append({"step":step,"action":"ask","q":q,"a":a})
            continue

        result = _execute(action)
        print(f"  → {result}")
        history.append(result); log.append({"step":step,"action":action.get("action"),"result":result})

        if action.get("action") == "done":
            print(f"\n✅ {result}")
            return {"success":True,"log":log,"steps":step}

        executor.wait(2)

    return {"success":False,"log":log,"steps":max_steps}
