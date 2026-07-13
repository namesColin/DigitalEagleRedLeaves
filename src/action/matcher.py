"""匹配层：LLM 将操作意图翻译为屏幕元素坐标"""
import json

MATCH_PROMPT = """你是一个屏幕元素定位器。根据操作目标，从元素列表中找出最匹配的那个。

【操作目标】
{goal}

【屏幕元素】（编号、描述、坐标、尺寸）
{elements}

【规则】
1. 找出与目标最匹配的元素
2. 找按钮/图标用 click，找文本框用 type，找不到用 null
3. 只输出 JSON:

{{"element_id": <编号>, "bbox": [x1,y1,x2,y2], "confidence": 0.9, "action": "click"}}"""


def _region(cx, cy, sw, sh):
    x = "左" if cx < sw//3 else ("右" if cx > sw*2//3 else "中")
    y = "上" if cy < sh//3 else ("下" if cy > sh*2//3 else "中")
    return f"{x}{y}"


def format_elements(boxes: list, labels: list, screen_w: int = 2560, screen_h: int = 1600) -> str:
    # 按 9 宫格区域分组
    regions = {}
    for i, (b, lbl) in enumerate(zip(boxes, labels)):
        if len(b) != 4: continue
        cx, cy = (b[0]+b[2])/2, (b[1]+b[3])/2
        r = _region(cx, cy, screen_w, screen_h)
        regions.setdefault(r, []).append((i, b, lbl))

    lines = [f"画面 {screen_w}x{screen_h}，{len(boxes)} 个元素，按区域排列："]
    for r in ["左上", "中上", "右上", "左中", "中中", "右中", "左下", "中下", "右下"]:
        items = regions.get(r, [])
        if not items: continue
        lines.append(f"\n【{r}区域】{len(items)} 个元素:")
        for i, b, lbl in items:
            cx, cy = int((b[0]+b[2])/2), int((b[1]+b[3])/2)
            w, h = int(b[2]-b[0]), int(b[3]-b[1])
            lines.append(f"  [{i}] \"{lbl}\" ({cx},{cy}) {w}x{h}")
    return "\n".join(lines)


async def find_element(goal: str, vision_result: dict, llm_client) -> dict | None:
    boxes = vision_result.get("boxes", [])
    labels = vision_result.get("labels", [])
    if not boxes:
        return None

    prompt = MATCH_PROMPT.format(
        goal=goal,
        elements=format_elements(boxes, labels),
    )
    resp = await llm_client.client.chat.completions.create(
        model=llm_client.model or "deepseek-v4-pro",
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
