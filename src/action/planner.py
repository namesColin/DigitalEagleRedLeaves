"""
指令生成&发送 — 动作路由 + 执行。
ActionPlanner: 接收意图，路由到 CDP 或视觉管线，执行操作。
"""
import time, asyncio
import pyautogui, pyperclip
from perception.uia_scanner import UiaScanner
from perception.som_grounding import SomGrounding
from perception.cursor_explorer import CursorExplorer
from action.matcher import ElementMatcher


class ActionPlanner:
    """动作路由 + 执行。不包含意图生成（在 brain_loop）。"""

    def __init__(self, cdp, matcher, vision=None, qwen=None, ds=None,
                 uia=None, som=None, cursor=None):
        self.cdp = cdp
        self.matcher = matcher
        self.vision = vision
        self.qwen = qwen
        self.ds = ds
        self.uia = uia or UiaScanner()
        self.som = som or SomGrounding(qwen_client=qwen)
        self.cursor = cursor or CursorExplorer(qwen_client=qwen)

    # ====================================================================
    # 动作路由
    # ====================================================================

    async def _route_action(self, action: str, target: str, goal: str,
                            step: int, stats: dict,
                            elements: list = None,
                            element_index: int = None) -> dict:
        if action in ("win_search",):
            return {"action": action, "layer": "direct", "query": target,
                    "target": target}

        if action == "press":
            if self.cdp.is_connected:
                await self.cdp.press_key(target or "Enter")
                stats["cdp"] += 1
                return {"action": "press", "layer": "cdp", "executed": True,
                        "key": target or "Enter", "target": target}
            return {"action": "press", "layer": "direct",
                    "key": target or "enter", "target": target}

        if action in ("done", "ask"):
            return {"action": action, "layer": "direct",
                    "question": target, "reason": target, "target": target}

        if action == "scroll":
            if self.cdp.is_connected:
                direction = (target or "down").lower()
                await self.cdp.scroll(direction)
                stats["cdp"] += 1
            return {"action": "scroll",
                    "layer": "cdp" if self.cdp.is_connected else "direct",
                    "executed": self.cdp.is_connected,
                    "direction": target, "target": target}

        if action == "navigate":
            if self.cdp.is_connected:
                await self.cdp.navigate(target)
                stats["cdp"] += 1
            return {"action": "navigate", "layer": "cdp", "target": target}

        if action == "type":
            if self.cdp.is_connected:
                await self.cdp.type_text(target)
                stats["cdp"] += 1
                return {"action": "type", "layer": "cdp", "executed": True,
                        "text": target, "target": target}
            return {"action": "type", "layer": "text", "text": target,
                    "target": target}

        return await self._route_click(target, goal, step, stats,
                                        elements, element_index)

    async def _route_click(self, target: str, goal: str, step: int,
                           stats: dict, elements: list = None,
                           element_index: int = None) -> dict:
        if self.cdp.is_connected:
            # 快速路径：DeepSeek 已指定 element_index
            if element_index is not None and elements and 0 <= element_index < len(elements):
                e = elements[element_index]
                await self.cdp.click_at(e["center"][0], e["center"][1])
                stats["cdp"] += 1
                print(f"  [CDP-fast] -> [{element_index}] {e['tag']}: {e['label'][:50]}")
                return {"action": "click", "layer": "cdp", "target": target,
                        "executed": True, "element_index": element_index,
                        "bbox": e["bbox"], "label": e["label"],
                        "tag": e["tag"]}
            # 常规路径：取元素 → DeepSeek 匹配
            if not elements:
                elements = await self.cdp.get_page_elements()
            if elements:
                chosen = await self.matcher._match_element(target, elements)
                if chosen is not None and 0 <= chosen < len(elements):
                    e = elements[chosen]
                    await self.cdp.click_at(e["center"][0], e["center"][1])
                    stats["cdp"] += 1
                    print(f"  [CDP] -> [{chosen}] {e['tag']}: {e['label'][:50]}")
                    return {"action": "click", "layer": "cdp", "target": target,
                            "executed": True, "element_index": chosen,
                            "bbox": e["bbox"], "label": e["label"],
                            "tag": e["tag"]}
            print(f"  [CDP] click \"{target}\" -> no match, trying visual...")
            b64 = await self.cdp.screenshot()
            if b64 and self.qwen and self.ds:
                desc = await self.matcher._describe_screenshot(b64, goal)
                if desc:
                    els2 = await self.cdp.get_page_elements()
                    if els2:
                        c2 = await self.matcher._match_element(target, els2)
                        if c2 is not None:
                            e2 = els2[c2]
                            await self.cdp.click_at(e2["center"][0],
                                                    e2["center"][1])
                            stats["cdp"] += 1
                            print(f"  [Visual-retry] -> [{c2}] {e2['tag']}: {e2['label'][:50]}")
                            return {"action": "click", "layer": "cdp-visual",
                                    "target": target, "executed": True,
                                    "element_index": c2, "bbox": e2["bbox"],
                                    "label": e2["label"], "tag": e2["tag"]}
            return {"action": "ask", "layer": "ask",
                    "question":
                    f"Step {step}: cannot find \"{target}\" on page"}

        # 非 CDP 模式：视觉管线
        uia_r = self.matcher._try_uia(target)
        if uia_r:
            stats["uia"] += 1
            uia_r["layer"] = "uia"; uia_r["action"] = "click"
            uia_r["target"] = target
            return uia_r
        img = pyautogui.screenshot()
        od, ocr = await asyncio.gather(
            self.vision.analyze(img, "<OD>"),
            self.vision.analyze(img, "<OCR_WITH_REGION>"))
        omni_els = self.matcher._index(
            od.get("boxes", []), od.get("labels", []),
            ocr.get("labels", []), ocr.get("boxes", []))
        filtered = self.matcher._spatial_filter(target, omni_els)
        if filtered:
            best = max(filtered,
                       key=lambda e: ((e["bbox"][2] - e["bbox"][0])
                                      * (e["bbox"][3] - e["bbox"][1])))
            cr = await self.cursor.explore_region(
                int(best["center"][0]), int(best["center"][1]), goal=target)
            if cr:
                stats["cursor"] += 1
                return {"action": "click", "layer": "cursor",
                        "target": target, "executed": False,
                        "bbox": [cr["x"] - 5, cr["y"] - 5,
                                 cr["x"] + 5, cr["y"] + 5],
                        "label": cr.get("element", target)}
        if self.qwen and filtered:
            rect = self.matcher._get_active_window_rect()
            sr = await self.som.ground(
                img, filtered, goal=target, crop_region=rect)
            if sr:
                stats["som"] += 1
                sr["layer"] = "som"; sr["action"] = "click"
                sr["target"] = target; sr["executed"] = False
                return sr
        text_r = self.matcher._try_text_match(target, omni_els)
        if text_r:
            stats["text"] += 1
            text_r["layer"] = "text"; text_r["action"] = "click"
            text_r["target"] = target
            return text_r
        return {"action": "ask", "layer": "ask",
                "question": f"Step {step}: cannot find \"{target}\""}

    # ====================================================================
    # 执行
    # ====================================================================

    def _exec(self, act: dict) -> str:
        a = act.get("action", "")
        layer = act.get("layer", "?")
        target = act.get("target", "")
        if act.get("executed"):
            return f"{a} [{layer}]: {target[:80]}"
        if a == "click":
            bbox = act.get("bbox")
            if bbox:
                x, y = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
                pyautogui.click(x, y)
                return f"Click ({x},{y}) [{layer}]"
            return "Click failed: no coords"
        elif a == "type":
            t = act.get("text", target)
            pyperclip.copy(t); pyautogui.hotkey("ctrl", "v")
            return f"Type \"{t[:50]}\" [{layer}]"
        elif a == "press":
            pyautogui.press(act.get("key", "enter"))
            return f"Press {act.get('key', 'enter')}"
        elif a == "scroll":
            return f"Scroll {act.get('direction','?')} [{layer}]"
        elif a == "win_search":
            q = act.get("query", target)
            pyautogui.hotkey("win"); time.sleep(0.3)
            pyautogui.write(q); time.sleep(0.2)
            pyautogui.press("enter")
            return f"WinSearch \"{q}\""
        elif a == "navigate":
            return f"Navigate \"{target}\" [{layer}]"
        elif a == "ask":
            return f"Ask: {act.get('question', target)[:80]}"
        elif a == "done":
            return f"Done: {act.get('reason', target)[:80]}"
        return f"Unknown: {a}"

    async def close(self):
        await self.cdp.close()
