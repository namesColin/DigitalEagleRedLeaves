"""
分层感知 Agent
CDP 可用时：Playwright DOM 查询 + 键盘输入
CDP 不可用时：UIA → Cursor → SoM → Text
"""
import time, json, os, re, asyncio, math, random, io, base64
import pyautogui, pyperclip
from perception.uia_scanner import UiaScanner
from perception.som_grounding import SomGrounding
from perception.chrome_driver import ChromeDriver
from perception.cursor_explorer import CursorExplorer
from perception.desktop_state import DesktopState


class LayeredAgent:

    def __init__(self, vision_module, qwen_client=None, ds_client=None):
        self.vision = vision_module
        self.qwen = qwen_client
        self.ds = ds_client
        self.uia = UiaScanner()
        self.som = SomGrounding(qwen_client=qwen_client)
        self.cdp = ChromeDriver()
        self.cursor = CursorExplorer(qwen_client=qwen_client)
        self.state = DesktopState()
        self.history = []
        self._prev_shots = []
        self._status_file = "outputs/agent_status.json"
        self._layer_stats = {"cdp": 0, "uia": 0, "cursor": 0, "som": 0, "text": 0}

    async def run(self, goal, max_steps=20, should_abort=None):
        print(f"\n[Agent] Goal: {goal}")
        if not self.cdp.is_connected:
            cdp_ok = await self.cdp.connect() or await self.cdp.launch()
            if not cdp_ok:
                print("  [Agent] Cannot connect to Chrome.")
                return {"success": False, "steps": 0, "log": [], "reason": "Chrome not available"}

        for s in range(1, max_steps + 1):
            if should_abort and should_abort():
                return {"success": False, "steps": s, "log": self.history,
                        "stats": self._layer_stats, "aborted": True}
            print(f"\n-- Step {s} --")
            self.state._refresh()

            intent = await self._get_intent(goal)
            if not intent:
                return {"success": False, "steps": s, "log": self.history,
                        "stats": self._layer_stats, "reason": "DS无响应"}

            action = intent.get("action", "")
            target = intent.get("target", "")
            print(f"  Intent: {action} \"{target}\"")
            print(f"  State: {self.state.status_text}")

            act = await self._route_action(action, target, goal, s)
            msg = self._exec(act)
            print(f"  -> {msg}")
            await asyncio.sleep(1)

            cur = self._shot()
            t = self._timing(cur)
            changed = t != "static"
            self.state.update(s, action, target, msg, changed)
            self._write_status(s, act.get("layer", "?"), msg)

            if self.state.is_stuck:
                print("  !! STUCK: injecting strategy hint")
                goal = self._inject_stuck_hint(goal, target)

            self.history.append({
                "step": s, "action": action, "result": msg,
                "layer": act.get("layer", "?"), "timing": t,
            })

            if action == "done":
                return {"success": True, "steps": s, "log": self.history, "stats": self._layer_stats}
            if action == "ask":
                self._write_status(s, intent.get("question", ""), "waiting")
                ans = ""
                try:
                    ans = input(f"\n  ? {intent.get('question', '')}\n  > ").strip()
                except EOFError:
                    pass
                if not ans:
                    ans = "skip"
                goal = f"({goal})\nLatest feedback: {ans}"
                continue
            if not changed and action == "click":
                print("  WARNING: screen unchanged")

        return {"success": False, "steps": max_steps, "log": self.history, "stats": self._layer_stats}

    # ====================================================================
    # 动作路由
    # ====================================================================

    async def _route_action(self, action: str, target: str, goal: str, step: int) -> dict:
        if action in ("win_search",):
            return {"action": action, "layer": "direct", "query": target, "target": target}

        if action == "press":
            if self.cdp.is_connected:
                await self.cdp.press_key(target or "Enter")
                self._layer_stats["cdp"] += 1
                return {"action": "press", "layer": "cdp", "executed": True, "key": target or "Enter", "target": target}
            return {"action": "press", "layer": "direct", "key": target or "enter", "target": target}

        if action in ("done", "ask"):
            return {"action": action, "layer": "direct", "question": target, "reason": target, "target": target}

        if action == "scroll":
            if self.cdp.is_connected:
                direction = (target or "down").lower()
                await self.cdp.scroll(direction)
                self._layer_stats["cdp"] += 1
            return {"action": "scroll", "layer": "cdp" if self.cdp.is_connected else "direct",
                    "executed": self.cdp.is_connected, "direction": target, "target": target}

        if action == "navigate":
            if self.cdp.is_connected:
                await self.cdp.navigate(target)
                self._layer_stats["cdp"] += 1
            return {"action": "navigate", "layer": "cdp", "target": target}

        if action == "type":
            if self.cdp.is_connected:
                await self.cdp.type_text(target)
                self._layer_stats["cdp"] += 1
                return {"action": "type", "layer": "cdp", "executed": True, "text": target, "target": target}
            return {"action": "type", "layer": "text", "text": target, "target": target}

        return await self._route_click(target, goal, step)

    async def _route_click(self, target: str, goal: str, step: int) -> dict:
        # CDP 模式：获取页面所有元素 → DeepSeek 匹配 → 点击
        if self.cdp.is_connected:
            els = await self.cdp.get_page_elements(timeout_ms=8000)
            if els:
                # 格式化为文本让 DeepSeek 选
                chosen = await self._match_element(target, els, step)
                if chosen is not None and 0 <= chosen < len(els):
                    e = els[chosen]
                    await self.cdp.click_at(e["center"][0], e["center"][1])
                    self._layer_stats["cdp"] += 1
                    print(f"  [CDP] -> [{chosen}] {e['tag']}: {e['label'][:50]}")
                    return {"action": "click", "layer": "cdp", "target": target, "executed": True,
                            "element_index": chosen, "bbox": e["bbox"],
                            "label": e["label"], "tag": e["tag"]}
            # 0 元素或匹配失败 → 截图视觉兜底
            print(f"  [CDP] click \"{target}\" → no match, trying visual fallback...")
            b64 = await self.cdp.screenshot()
            if b64 and self.qwen and self.ds:
                desc = await self._describe_screenshot(b64, goal)
                if desc:
                    els2 = await self.cdp.get_page_elements(timeout_ms=4000)
                    if els2:
                        chosen2 = await self._match_element(target, els2, step)
                        if chosen2 is not None:
                            e2 = els2[chosen2]
                            await self.cdp.click_at(e2["center"][0], e2["center"][1])
                            self._layer_stats["cdp"] += 1
                            print(f"  [Visual-retry] -> [{chosen2}] {e2['tag']}: {e2['label'][:50]}")
                            return {"action": "click", "layer": "cdp-visual", "target": target, "executed": True,
                                    "element_index": chosen2, "bbox": e2["bbox"],
                                    "label": e2["label"], "tag": e2["tag"]}
            return {"action": "ask", "layer": "ask",
                    "question": f"Step {step}: cannot find \"{target}\" on page"}

        # 非 CDP 模式：视觉管线
        uia_r = self._try_uia(target)
        if uia_r:
            self._layer_stats["uia"] += 1
            uia_r["layer"] = "uia"; uia_r["action"] = "click"; uia_r["target"] = target
            return uia_r
        img = self._shot()
        od, ocr = await asyncio.gather(
            self.vision.analyze(img, "<OD>"), self.vision.analyze(img, "<OCR_WITH_REGION>"))
        omni_els = self._index(od.get("boxes", []), od.get("labels", []),
                               ocr.get("labels", []), ocr.get("boxes", []))
        filtered = self._spatial_filter(target, omni_els)
        if filtered:
            best = max(filtered, key=lambda e: (e["bbox"][2] - e["bbox"][0]) * (e["bbox"][3] - e["bbox"][1]))
            cursor_r = await self.cursor.explore_region(int(best["center"][0]), int(best["center"][1]), goal=target)
            if cursor_r:
                self._layer_stats["cursor"] += 1
                return {"action": "click", "layer": "cursor", "target": target, "executed": False,
                        "bbox": [cursor_r["x"] - 5, cursor_r["y"] - 5, cursor_r["x"] + 5, cursor_r["y"] + 5],
                        "label": cursor_r.get("element", target)}
        if self.qwen and filtered:
            som_r = await self.som.ground(img, filtered, goal=target, crop_region=self._get_active_window_rect())
            if som_r:
                self._layer_stats["som"] += 1
                som_r["layer"] = "som"; som_r["action"] = "click"; som_r["target"] = target; som_r["executed"] = False
                return som_r
        text_r = self._try_text_match(target, omni_els)
        if text_r:
            self._layer_stats["text"] += 1
            text_r["layer"] = "text"; text_r["action"] = "click"; text_r["target"] = target
            return text_r
        return {"action": "ask", "layer": "ask", "question": f"Step {step}: cannot find \"{target}\""}

    # ====================================================================
    # Intent
    # ====================================================================

    async def _get_intent(self, goal: str) -> dict | None:
        if not self.ds:
            return None
        ctx = "\n".join([h["result"] for h in self.history[-3:]]) if self.history else "start"
        try:
            resp = await self.ds.client.chat.completions.create(
                model=self.ds.model or "deepseek-v4-pro",
                messages=[{"role": "user", "content": f"""Decide the next action.

Goal: {goal}
State: {self.state.status_text}
Recent results: {ctx}

You control a Chrome browser via CDP (DevTools Protocol).
Available actions:
  navigate("url")  — open any website
  click("element description")  — click an element on the page
  type("text")  — type into the currently focused input
  press("Enter"/"Tab"/"Escape")  — press a key
  scroll("up"/"down")  — scroll the page
  done("reason")  — goal achieved
  ask("question")  — need user help
Output ONLY JSON: {{"action":"...","target":"..."}}
"""}], stream=False)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"): raw = raw.split("\n", 1)[1].rstrip("```").strip()
            intent = json.loads(raw)
            print(f"  DS: {intent.get('action')} -> \"{intent.get('target', '')[:80]}\"")
            return intent
        except Exception as e:
            print(f"  DS error: {e}")
            return None

    # ====================================================================
    # 视觉辅助
    # ====================================================================

    def _try_uia(self, target: str) -> dict | None:
        if not target: return None
        keywords = [k for k in re.split(r'[，,、\s]+', target) if len(k) >= 2]
        if not keywords: return None
        ACT = {"ButtonControl", "EditControl", "ListItemControl", "HyperlinkControl", "TabItemControl",
               "MenuItemControl", "RadioButtonControl", "CheckBoxControl", "ComboBoxControl"}
        WND = {"WindowControl", "PaneControl", "MenuBarControl", "TitleBarControl"}
        uia_els = [];
        try: uia_els = self.uia.scan_by_criteria(name="", max_depth=6)
        except: pass
        try:
            fg = self.uia.scan_active_window(max_depth=5)
            seen = {(e["bbox"][0], e["bbox"][1], e.get("ocr_text", "")) for e in uia_els}
            for e in fg:
                if (e["bbox"][0], e["bbox"][1], e.get("ocr_text", "")) not in seen: uia_els.append(e)
        except: pass
        if not uia_els: return None
        scored = []
        for e in uia_els:
            name = (e.get("ocr_text") or "").lower(); ctype = e.get("control_type", "")
            if not name or len(name) < 2 or ctype in WND: continue
            score = 0
            for kw in keywords:
                if name == kw.lower(): score += 10
                elif name.startswith(kw.lower()): score += 6
                elif kw.lower() in name: score += 3
            if score == 0: continue
            if ctype in ACT: score += 2
            scored.append((score, e))
        if not scored: return None
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return {"element_id": best["id"], "label": best.get("od_label", ""), "bbox": best["bbox"]}

    def _spatial_filter(self, target: str, els: list[dict]) -> list[dict]:
        desc = target.lower(); sw, sh = pyautogui.size(); regions = []
        if any(w in desc for w in ["top", "upper", "title", "tab", "toolbar", "menu", "search", "address", "url", "顶部", "上方", "搜索", "地址栏"]): regions.append("top")
        if any(w in desc for w in ["bottom", "taskbar", "status", "lower", "底部", "下方"]): regions.append("bottom")
        if any(w in desc for w in ["left", "sidebar", "左侧", "左边"]): regions.append("left")
        if any(w in desc for w in ["right", "右侧", "右边"]): regions.append("right")
        if any(w in desc for w in ["center", "middle", "中间", "中央"]): regions.append("center")
        if not regions: return els
        filtered = []
        for e in els:
            cx, cy = e["center"]; xr, yr = cx / sw, cy / sh
            if ("top" in regions and yr < 0.3) or ("bottom" in regions and yr > 0.7) or \
               ("left" in regions and xr < 0.3) or ("right" in regions and xr > 0.7) or \
               ("center" in regions and 0.25 < xr < 0.75 and 0.25 < yr < 0.75): filtered.append(e)
        return filtered if filtered else els

    def _try_text_match(self, target: str, els: list[dict]) -> dict | None:
        if not target or not els: return None
        keywords = [k for k in re.split(r'[，,、\s]+', target) if len(k) >= 3]
        if not keywords: return None
        for kw in keywords:
            kw_l = kw.lower(); matches = []
            for e in els:
                t = (e.get("ocr_text") or "").lower(); od = (e.get("od_label") or "").lower()
                if t and kw_l in t: matches.append(e)
                elif od and kw_l in od and not od.startswith("a ") and not od.startswith("an "): matches.append(e)
            if matches:
                e = max(matches, key=lambda x: (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]))
                return {"element_id": e["id"], "label": e.get("od_label", ""), "bbox": e["bbox"]}
        return None

    # ====================================================================
    # Helpers
    # ====================================================================

    async def _match_element(self, target: str, els: list[dict], step: int) -> int | None:
        """把元素列表给 DeepSeek，让它选出匹配 target 的那个。零白名单。"""
        if not self.ds or not els:
            return None
        # 格式化前60个元素
        lines = []
        for i, e in enumerate(els[:60]):
            attrs = []
            if e["placeholder"]: attrs.append(f'placeholder="{e["placeholder"]}"')
            if e["aria"]: attrs.append(f'aria="{e["aria"]}"')
            if e["type"] and e["type"] not in ("text",): attrs.append(f"type={e["type"]}")
            if e["role"]: attrs.append(f"role={e["role"]}")
            if e["name"]: attrs.append(f'name="{e["name"]}"')
            if e["text"] and e["text"] != e["label"]: attrs.append(f'text="{e["text"]}"')
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
            if raw.startswith("```"): raw = raw.split("\n", 1)[1].rstrip("```").strip()
            data = json.loads(raw)
            idx = data.get("index", -1)
            if isinstance(idx, int) and 0 <= idx < len(els):
                return idx
        except Exception as e:
            print(f"  [Match] DS error: {e}")
        return None

    async def _describe_screenshot(self, b64: str, goal: str) -> str | None:
        """Qwen 看图描述页面。仅用于视觉兜底。"""
        try:
            resp = await self.qwen.chat.completions.create(
                model="qwen3-vl-plus",
                extra_body={"enable_thinking": True, "thinking_budget": 2048},
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
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

    def _shot(self): return pyautogui.screenshot()
    def _get_active_window_rect(self):
        try:
            import uiautomation as auto
            win = auto.GetForegroundControl()
            if win:
                r = win.BoundingRectangle
                if r and r.width() > 100 and r.height() > 100: return (r.left, r.top, r.width(), r.height())
        except: pass
        s = pyautogui.size(); return (0, 0, s.width(), s.height())

    def _index(self, od_b, od_l, ocr_t, ocr_b):
        els = []
        for i, (b, lbl) in enumerate(zip(od_b, od_l)):
            if len(b) != 4: continue
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            e = {"id": i, "bbox": list(b), "center": (cx, cy), "od_label": lbl, "ocr_text": ""}
            if ocr_t and ocr_b:
                best, bd = "", 120
                for t, ob in zip(ocr_t, ocr_b):
                    t = str(t).replace("</s>", "").replace("<s>", "").strip()
                    if len(t) < 2: continue
                    ox, oy = self._c(ob); d = math.hypot(cx - ox, cy - oy)
                    if d < bd: best, bd = t, d
                e["ocr_text"] = best
            els.append(e)
        return els

    def _c(self, b):
        if len(b) == 8: return sum(b[0:8:2]) / 4, sum(b[1:8:2]) / 4
        if len(b) == 4: return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return 0, 0

    def _timing(self, cur):
        self._prev_shots.append(cur)
        if len(self._prev_shots) > 4: self._prev_shots.pop(0)
        if len(self._prev_shots) < 3: return "first"
        samples = []
        for i in range(len(self._prev_shots) - 1):
            a, b = self._prev_shots[i], self._prev_shots[i + 1]
            if a.size != b.size: samples.append(True); continue
            d = 0
            for _ in range(100):
                x = random.randint(0, a.size[0] - 1); y = random.randint(0, a.size[1] - 1)
                if a.getpixel((x, y)) != b.getpixel((x, y)): d += 1
            samples.append(d > 5)
        if all(samples): return "loading"
        if not any(samples): return "static"
        return "changing"

    def _write_status(self, step, layer_info, result):
        try:
            os.makedirs("outputs", exist_ok=True)
            with open(self._status_file, "w", encoding="utf-8") as f:
                json.dump({"step": step, "layer": str(layer_info)[:200], "result": str(result)[:200],
                           "stats": self._layer_stats, "state": self.state.status_text, "ts": time.time()}, f, ensure_ascii=False)
        except: pass

    def _img_b64(self, img):
        buf = io.BytesIO(); img.save(buf, format="PNG"); return base64.b64encode(buf.getvalue()).decode()

    def _inject_stuck_hint(self, goal: str, target: str) -> str:
        return f"{goal}\n[Last action on \"{target}\" had no visible effect. Try a different approach.]"

    def _exec(self, act: dict) -> str:
        a = act.get("action", ""); layer = act.get("layer", "?"); target = act.get("target", "")
        if act.get("executed"): return f"{a} [{layer}]: {target[:80]}"
        if a == "click":
            bbox = act.get("bbox")
            if bbox:
                x, y = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
                pyautogui.click(x, y); return f"Click ({x},{y}) [{layer}]"
            return f"Click failed: no coords"
        elif a == "type":
            t = act.get("text", target); pyperclip.copy(t); pyautogui.hotkey("ctrl", "v"); return f"Type \"{t[:50]}\" [{layer}]"
        elif a == "press":
            pyautogui.press(act.get("key", "enter")); return f"Press {act.get('key', 'enter')}"
        elif a == "scroll":
            return f"Scroll {act.get('direction','?')} [{layer}]"
        elif a == "win_search":
            q = act.get("query", target); pyautogui.hotkey("win"); time.sleep(0.3); pyautogui.write(q); time.sleep(0.2); pyautogui.press("enter")
            return f"WinSearch \"{q}\""
        elif a == "navigate": return f"Navigate \"{target}\" [{layer}]"
        elif a == "ask": return f"Ask: {act.get('question', target)[:80]}"
        elif a == "done": return f"Done: {act.get('reason', target)[:80]}"
        return f"Unknown: {a}"

    async def close(self):
        await self.cdp.close()
