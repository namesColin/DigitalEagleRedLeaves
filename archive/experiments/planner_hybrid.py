"""
混合规划器 v3：OD 框 + OCR 文字双标注 → Qwen 看图决策
OD 告诉"这里有可交互元素"，OCR 告诉"这个元素叫什么"
"""
import json, io, base64, os, sys
from openai import AsyncOpenAI
from PIL import ImageDraw, ImageFont
from . import executor

try: from ..core.config import Config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.config import Config

QWEN_PROMPT = """你是桌面操作助手。截图上有两层标注：
- 彩色框+编号 = 可交互 UI 元素（按钮、输入框、图标）
- 白色小字 = OCR 识别出的屏幕文字（可直接读到账号名、按钮文字、网址等）

请结合两者决策。OCR 文字能告诉你元素的真实名称。

【目标】{intent}
【已做】{history}

输出 JSON：
{{"screen":"Chrome用户选择界面,OCR显示Colin在框[3]旁","action":"click","element_id":3}}
{{"screen":"桌面无Chrome","action":"win_search","query":"chrome"}}
{{"screen":"地址栏已选中","action":"type","text":"bilibili.com"}}
{{"screen":"已显示目标","action":"done","reason":"完成"}}"""


def _annotate_with_ocr(image, od_boxes, od_labels, ocr_texts, ocr_boxes):
    img = image.copy(); draw = ImageDraw.Draw(img)
    colors = ["lime","cyan","yellow","magenta","orange","red"]
    try: font = ImageFont.truetype("msyh.ttc", 18)
    except: font = ImageFont.load_default()

    elements = []
    for i, (b, lbl) in enumerate(zip(od_boxes, od_labels)):
        if len(b) != 4: continue
        x1,y1,x2,y2 = [int(v) for v in b]; c = colors[i%len(colors)]
        draw.rectangle([x1,y1,x2,y2], outline=c, width=2)
        draw.text((x1+2, max(0,y2-20)), str(i), fill=c, font=font)
        elements.append({"id":i, "bbox":[x1,y1,x2,y2], "label":lbl})

    # OCR 白色文字
    if ocr_texts and ocr_boxes:
        for text, box in zip(ocr_texts, ocr_boxes):
            text = str(text).replace("</s>","").replace("<s>","").strip()
            if len(text) < 2: continue
            if len(box) == 8:
                xs = [box[k] for k in range(0,8,2)]; ys = [box[k+1] for k in range(0,8,2)]
                x, y = int(min(xs)), int(min(ys))
            elif len(box) == 4: x, y = int(box[0]), int(box[1])
            else: continue
            draw.text((x, max(0,y-18)), text, fill="white", font=font)
    return img, elements


def _b64(img): b=io.BytesIO(); img.save(b,format="PNG"); return base64.b64encode(b.getvalue()).decode()
def _parse(raw):
    raw = raw.strip()
    if raw.startswith("```"): raw = raw.split("\n",1)[1].rstrip("```").strip()
    try: return json.loads(raw)
    except: return {"action":"wait","seconds":1}


def _execute(action, elements):
    act = (action.get("action") or "").lower(); r = action.get("reason","")
    if act in ("click",):
        eid = action.get("element_id")
        if eid is not None and 0 <= eid < len(elements):
            executor.click_center(elements[eid]["bbox"]); return f"点击[{eid}]"
        return f"click id={eid} 无效"
    elif act in ("type","input"):
        executor.type_text(action.get("text","")); return f"输入:{action.get('text','')}"
    elif act in ("press","key"):
        executor.press(action.get("key","enter")); return f"按键:{action.get('key','enter')}"
    elif act in ("win_search","search"):
        q = action.get("query",""); executor.hotkey("win"); executor.wait(0.4)
        executor.type_text(q); executor.wait(0.3); executor.press("enter")
        return f"Win搜索:{q}"
    elif act in ("hotkey",):
        executor.hotkey(*(action.get("keys") or [action.get("key","win")])); return "组合键"
    elif act in ("ask","ask_user"): return f"ASK:{action.get('question',r)}"
    elif act in ("done","finish"): return f"DONE:{r}"
    elif act in ("wait",): executor.wait(action.get("seconds",1)); return f"等{action.get('seconds',1)}s"
    return f"未知:{act}"


async def run(intent: str, llm_client=None, max_steps: int = 12) -> dict:
    try: from ..vision.vision_model_v2 import VisionModuleV2
    except ImportError:
        _src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, _src); from vision.vision_model_v2 import VisionModuleV2

    print("加载 OmniParser ...")
    vision = VisionModuleV2()
    qwen = AsyncOpenAI(api_key=Config.GLM_API_KEY, base_url=Config.GLM_BASE_URL)
    history, log = [], []

    for step in range(1, max_steps + 1):
        print(f"\n─ 第 {step} 步 ─")

        img = executor.screenshot()

        # OD + OCR
        print("  检测...", end=" ", flush=True)
        vis_od = await vision.analyze(img, "<OD>")
        od_b, od_l = vis_od.get("boxes",[]), vis_od.get("labels",[])
        vis_ocr = await vision.analyze(img, "<OCR_WITH_REGION>")
        ocr_t, ocr_bx = vis_ocr.get("labels",[]), vis_ocr.get("boxes",[])

        annotated, els = _annotate_with_ocr(img, od_b, od_l, ocr_t, ocr_bx)
        print(f"(OD:{len(od_b)} OCR:{len(ocr_t)})", end=" ", flush=True)

        prompt = QWEN_PROMPT.format(
            intent=intent,
            history="\n".join(history[-3:]) if history else "（首次）",
        )
        print("Qwen...", end=" ", flush=True)
        qr = await qwen.chat.completions.create(
            model=Config.GLM_VISION_MODEL,
            messages=[{"role":"user","content":[
                {"type":"image_url","image_url":{"url":f"data:image/png;base64,{_b64(annotated)}"}},
                {"type":"text","text":prompt},
            ]}],
            stream=False, timeout=90,
        )
        action = _parse(qr.choices[0].message.content)
        if isinstance(action, list): action = action[0] if action else {"action":"done"}
        print(json.dumps(action, ensure_ascii=False)[:200])

        if action.get("action") in ("ask","ask_user"):
            q = action.get("question","？")
            a = input(f"\n  🤔 {q}\n  → ").strip()
            history.append(f"问:{q}答:{a}"); log.append({"step":step,"action":"ask","q":q,"a":a})
            continue

        result = _execute(action, els)
        print(f"  → {result}")
        history.append(result); log.append({"step":step,"action":action.get("action"),"result":result})

        if action.get("action") in ("done","finish"):
            print(f"\n✅ {result}")
            return {"success":True,"log":log,"steps":step}

        executor.wait(2)

    return {"success":False,"log":log,"steps":max_steps}
