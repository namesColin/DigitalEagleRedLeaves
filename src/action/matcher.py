"""
元素匹配 + 视觉兜底。
ElementMatcher: DeepSeek 文本匹配、Qwen 看图、UIA/SoM/文本搜索。
"""
import json, re, math
import pyautogui
from perception.uia_scanner import UiaScanner


class ElementMatcher:
    """元素定位：LLM 文本匹配 + 视觉兜底 + UIA + SoM。无白名单。"""

    def __init__(self, ds_client=None, qwen_client=None, uia=None):
        self.ds = ds_client
        self.qwen = qwen_client
        self.uia = uia or UiaScanner()

    # ====================================================================
    # DeepSeek 文本匹配
    # ====================================================================

    async def _match_element(self, target: str, els: list[dict]) -> int | None:
        """把元素列表给 DeepSeek，让它选出匹配 target 的那个。零白名单。"""
        if not self.ds or not els:
            return None
        lines = []
        for i, e in enumerate(els[:60]):
            attrs = []
            if e["placeholder"]:
                attrs.append(f'placeholder="{e["placeholder"]}"')
            if e["aria"]:
                attrs.append(f'aria="{e["aria"]}"')
            if e["type"] and e["type"] not in ("text",):
                attrs.append(f"type={e['type']}")
            if e["role"]:
                attrs.append(f"role={e['role']}")
            if e["name"]:
                attrs.append(f'name="{e["name"]}"')
            if e["text"] and e["text"] != e["label"]:
                attrs.append(f'text="{e["text"]}"')
            tag_info = f"<{e['tag']}>"
            attr_str = " ".join(attrs) if attrs else ""
            label = f"{tag_info} {attr_str}".strip()
            if not attr_str:
                label = f"{tag_info} \"{e['label']}\""
            lines.append(f"[{i}] {label}")
        el_text = "\n".join(lines)
        try:
            resp = await self.ds.client.chat.completions.create(
                model=self.ds.model or "deepseek-v4-pro",
                messages=[{"role": "user", "content": f"""From the list below, find the element best matching: "{target}"

{el_text}

Output ONLY JSON with the index number: {{"index": N}}
If nothing matches, output: {{"index": -1}}
"""}], stream=False)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rstrip("```").strip()
            data = json.loads(raw)
            idx = data.get("index", -1)
            if isinstance(idx, int) and 0 <= idx < len(els):
                return idx
        except Exception as e:
            print(f"  [Match] DS error: {e}")
        return None

    # ====================================================================
    # Qwen 视觉兜底
    # ====================================================================

    async def _describe_screenshot(self, b64: str, goal: str) -> str | None:
        """Qwen 看图描述页面。仅用于视觉兜底。"""
        try:
            resp = await self.qwen.chat.completions.create(
                model="qwen3-vl-plus",
                extra_body={"enable_thinking": True, "thinking_budget": 2048},
                messages=[{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": (
                        f"目标: {goal}\n"
                        "描述当前浏览器页面: 1.页面状态(加载中/正常/空白/错误) "
                        "2.可见的输入框在哪个区域、有什么特征(placeholder、旁边文字) "
                        "3.可见的按钮有哪些、在哪\n"
                        "用中文简短回复。"
                    )},
                ]}], stream=False, timeout=30)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [Visual] Qwen error: {e}")
            return None

    # ====================================================================
    # 非 CDP 视觉辅助
    # ====================================================================

    def _try_uia(self, target: str) -> dict | None:
        if not target:
            return None
        keywords = [k for k in re.split(r'[，,、\s]+', target) if len(k) >= 2]
        if not keywords:
            return None
        uia_els = []
        try:
            uia_els = self.uia.scan_by_criteria(name="", max_depth=6)
        except Exception:
            pass
        try:
            fg = self.uia.scan_active_window(max_depth=5)
            seen = {(e["bbox"][0], e["bbox"][1], e.get("ocr_text", ""))
                    for e in uia_els}
            for e in fg:
                key = (e["bbox"][0], e["bbox"][1], e.get("ocr_text", ""))
                if key not in seen:
                    uia_els.append(e)
        except Exception:
            pass
        if not uia_els:
            return None
        WND = {"WindowControl", "PaneControl", "MenuBarControl",
               "TitleBarControl"}
        scored = []
        for e in uia_els:
            name = (e.get("ocr_text") or "").lower()
            ctype = e.get("control_type", "")
            if not name or len(name) < 2 or ctype in WND:
                continue
            score = 0
            for kw in keywords:
                if name == kw.lower():
                    score += 10
                elif name.startswith(kw.lower()):
                    score += 6
                elif kw.lower() in name:
                    score += 3
            if score == 0:
                continue
            if ctype in {"ButtonControl", "EditControl", "ListItemControl",
                         "HyperlinkControl", "TabItemControl", "MenuItemControl",
                         "RadioButtonControl", "CheckBoxControl",
                         "ComboBoxControl"}:
                score += 2
            scored.append((score, e))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return {"element_id": best["id"],
                "label": best.get("od_label", ""), "bbox": best["bbox"]}

    def _spatial_filter(self, target: str, els: list[dict]) -> list[dict]:
        desc = target.lower()
        sw, sh = pyautogui.size()
        regions = []
        TOP = {"top", "upper", "title", "tab", "toolbar", "menu",
               "search", "address", "url", "顶部", "上方", "搜索", "地址栏"}
        BOT = {"bottom", "taskbar", "status", "lower", "底部", "下方"}
        LFT = {"left", "sidebar", "左侧", "左边"}
        RGT = {"right", "右侧", "右边"}
        CTR = {"center", "middle", "中间", "中央"}
        if any(w in desc for w in TOP): regions.append("top")
        if any(w in desc for w in BOT): regions.append("bottom")
        if any(w in desc for w in LFT): regions.append("left")
        if any(w in desc for w in RGT): regions.append("right")
        if any(w in desc for w in CTR): regions.append("center")
        if not regions:
            return els
        filtered = []
        for e in els:
            cx, cy = e["center"]
            xr, yr = cx / sw, cy / sh
            if (("top" in regions and yr < 0.3)
                or ("bottom" in regions and yr > 0.7)
                or ("left" in regions and xr < 0.3)
                or ("right" in regions and xr > 0.7)
                or ("center" in regions
                    and 0.25 < xr < 0.75 and 0.25 < yr < 0.75)):
                filtered.append(e)
        return filtered if filtered else els

    def _try_text_match(self, target: str, els: list[dict]) -> dict | None:
        if not target or not els:
            return None
        keywords = [k for k in re.split(r'[，,、\s]+', target) if len(k) >= 3]
        if not keywords:
            return None
        for kw in keywords:
            kw_l = kw.lower()
            matches = []
            for e in els:
                t = (e.get("ocr_text") or "").lower()
                od = (e.get("od_label") or "").lower()
                if t and kw_l in t:
                    matches.append(e)
                elif (od and kw_l in od
                      and not od.startswith("a ")
                      and not od.startswith("an ")):
                    matches.append(e)
            if matches:
                e = max(matches,
                        key=lambda x: ((x["bbox"][2] - x["bbox"][0])
                                       * (x["bbox"][3] - x["bbox"][1])))
                return {"element_id": e["id"],
                        "label": e.get("od_label", ""),
                        "bbox": e["bbox"]}
        return None

    def _index(self, od_b, od_l, ocr_t, ocr_b):
        els = []
        for i, (b, lbl) in enumerate(zip(od_b, od_l)):
            if len(b) != 4:
                continue
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            e = {"id": i, "bbox": list(b), "center": (cx, cy),
                 "od_label": lbl, "ocr_text": ""}
            if ocr_t and ocr_b:
                best, bd = "", 120
                for t, ob in zip(ocr_t, ocr_b):
                    t = str(t).replace("</s>", "").replace("<s>", "").strip()
                    if len(t) < 2:
                        continue
                    ox, oy = self._c(ob)
                    d = math.hypot(cx - ox, cy - oy)
                    if d < bd:
                        best, bd = t, d
                e["ocr_text"] = best
            els.append(e)
        return els

    def _c(self, b):
        if len(b) == 8:
            return sum(b[0:8:2]) / 4, sum(b[1:8:2]) / 4
        if len(b) == 4:
            return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return 0, 0

    def _get_active_window_rect(self):
        try:
            import uiautomation as auto
            win = auto.GetForegroundControl()
            if win:
                r = win.BoundingRectangle
                if r and r.width() > 100 and r.height() > 100:
                    return (r.left, r.top, r.width(), r.height())
        except Exception:
            pass
        s = pyautogui.size()
        return (0, 0, s.width(), s.height())
