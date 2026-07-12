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


def format_elements(boxes: list, labels: list) -> str:
    lines = []
    for i, (bbox, label) in enumerate(zip(boxes, labels)):
        if len(bbox) == 4:
            cx, cy = int((bbox[0]+bbox[2])/2), int((bbox[1]+bbox[3])/2)
            w, h = int(bbox[2]-bbox[0]), int(bbox[3]-bbox[1])
            lines.append(f"  [{i}] \"{label}\" 中心({cx},{cy}) {w}x{h}")
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
