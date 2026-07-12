"""视觉模块诊断 —— 不改现有代码，只采集模型原始返回数据。

用法: 先启动 vision_server，再跑 python scripts/vision_diagnose.py
输出: vision_diagnose.json（含原始坐标、格式、推理耗时等信息）
"""
import json, time, requests, pyautogui, io, ctypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

API_URL = "http://localhost:30001/analyze"
PROMPTS = ["<OCR_WITH_REGION>", "<OD>", "<DETAILED_CAPTION>"]

screenshot = pyautogui.screenshot()
w, h = screenshot.size
img_bytes = io.BytesIO()
screenshot.save(img_bytes, format='PNG')

results = {"screen": f"{w}x{h}", "tests": []}

for prompt in PROMPTS:
    print(f"跑 {prompt} ... ", end="", flush=True)
    img_bytes.seek(0)
    t0 = time.time()
    resp = requests.post(
        API_URL,
        files={'file': ('diag.png', img_bytes.getvalue(), 'image/png')},
        params={'prompt': prompt},
    )
    elapsed = round(time.time() - t0, 2)
    data = resp.json()
    task_data = data.get("data", {}).get(prompt, {}) or data.get("data", {})
    # V2 caption: {"caption": "...", "format": "text"}
    if isinstance(task_data, dict) and "caption" in task_data:
        results["tests"].append({"prompt": prompt, "elapsed_sec": elapsed,
                                 "caption": task_data["caption"]})
        print(f"{elapsed}s, caption={task_data['caption'][:50]}...")
        continue
    # V2: {"boxes": [...], "labels": [...], "format": "xyxy_pixel"}
    if isinstance(task_data, dict) and "boxes" in task_data:
        boxes = task_data["boxes"]
    else:
        boxes = task_data.get("bboxes") or task_data.get("quad_boxes") if isinstance(task_data, dict) else None
    test = {
        "prompt": prompt, "elapsed_sec": elapsed,
        "box_count": len(boxes) if boxes else 0,
        "raw_result": data.get("data", {}),
    }
    if boxes and len(boxes) > 0:
        test["box_dims"] = len(boxes[0])
        labels = task_data.get("labels", [])
        test["samples"] = [{"label": lbl, "box": b} for lbl, b in zip(labels, boxes[:5])]
    results["tests"].append(test)
    print(f"{elapsed}s, {test['box_count']} 个目标")

with open("vision_diagnose.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n诊断完成 → vision_diagnose.json")
