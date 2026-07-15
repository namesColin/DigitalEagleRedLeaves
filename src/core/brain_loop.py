"""
数字大脑决策循环 — JS 直驱版
① CDP 取页面摘要 → ② DeepSeek 写 JS → ③ CDP 执行 JS
"""
import time, json, os, asyncio, random, io, base64
import pyautogui


class BrainLoop:

    def __init__(self, vision_module, qwen_client=None, ds_client=None,
                 planner=None, state=None):
        self.vision = vision_module
        self.qwen = qwen_client
        self.ds = ds_client
        self.planner = planner
        self.state = state
        self.history = []
        self._prev_shots = []
        self._status_file = "outputs/agent_status.json"
        self._layer_stats = {"cdp": 0, "uia": 0, "cursor": 0, "som": 0, "text": 0}

    @property
    def cdp(self):
        return self.planner.cdp if self.planner else None

    async def run(self, goal, max_steps=20, should_abort=None):
        print(f"\n[Agent] Goal: {goal}")
        cdp = self.cdp
        use_cdp = cdp and cdp.is_connected
        if not use_cdp:
            if cdp:
                cdp_ok = await cdp.connect() or await cdp.launch()
                use_cdp = cdp_ok
            if not use_cdp:
                print("  [Agent] Cannot connect to Chrome.")
                return {"success": False, "steps": 0, "log": [],
                        "reason": "Chrome not available"}

        for s in range(1, max_steps + 1):
            if should_abort and should_abort():
                return {"success": False, "steps": s, "log": self.history,
                        "stats": self._layer_stats, "aborted": True}
            print(f"\n-- Step {s} --")
            self.state._refresh()

            # ① CDP: 取页面摘要（navigate 后等页面就绪）
            summary = {}
            if use_cdp:
                if self.history and self.history[-1].get("action") == "navigate":
                    # 一次 CDP 调用等页面加载就绪
                    ready = await cdp.wait_page_ready(timeout_sec=12)
                    print(f"  Page ready: {ready.get('ready')} "
                          f"({ready.get('elements', 0)} elements)")
                summary = await cdp.get_page_summary()
                if summary:
                    print(f"  Page: {summary.get('url','')[:80]} | "
                          f"{summary.get('title','')[:40]} | "
                          f"{len(summary.get('interactive',[]))} elements")

            # ② DeepSeek: 写 JS
            intent = await self._get_intent(goal, summary)
            if not intent:
                return {"success": False, "steps": s, "log": self.history,
                        "stats": self._layer_stats, "reason": "DS无响应"}

            action = intent.get("action", "")
            target = intent.get("target", "")
            js_code = intent.get("js", "")
            print(f"  DS: {action} \"{target}\""
                  + (f" [{len(js_code)} chars JS]" if js_code else ""))

            # ③ 执行: click用JS, type/press/navigate用CDP原生
            act = None
            if use_cdp:
                if action == "click" and js_code:
                    print(f"  JS: {js_code}")
                    result = await cdp.evaluate(js_code)
                    if not result.get("error"):
                        self._layer_stats["cdp"] += 1
                        msg = f"click [cdp-js]: {target[:80]}"
                        act = {"action": action, "layer": "cdp", "executed": True}
                    else:
                        print(f"  JS click missed, fallback to coords...")
                        elements = await cdp.get_page_elements()
                        act = await self.planner._route_action(
                            action, target, goal, s, self._layer_stats,
                            elements=elements)
                        msg = self.planner._exec(act)
                elif action in ("navigate", "type", "press", "scroll"):
                    # CDP 原生方法 — 不用 JS
                    act = await self.planner._route_action(
                        action, target, goal, s, self._layer_stats)
                    msg = self.planner._exec(act)
                elif action in ("done", "ask"):
                    act = {"action": action, "layer": "direct",
                           "question": target, "reason": target,
                           "target": target}
                    msg = self.planner._exec(act)
            if act is None:
                act = await self.planner._route_action(
                    action, target, goal, s, self._layer_stats)
                msg = self.planner._exec(act)

            print(f"  -> {msg}")

            # 验证
            if use_cdp:
                timing = "cdp"
                changed = True
            else:
                cur = pyautogui.screenshot()
                timing = self._timing(cur)
                changed = timing != "static"

            self.state.update(s, action, target, msg, changed)
            self._write_status(s, act.get("layer", "?"), msg)

            if self.state.is_stuck:
                goal = self._inject_stuck_hint(goal, target)

            self.history.append({
                "step": s, "action": action, "result": msg,
                "layer": act.get("layer", "?"), "timing": timing,
            })

            if action == "done":
                return {"success": True, "steps": s, "log": self.history,
                        "stats": self._layer_stats}
            if action == "ask":
                self._write_status(s, intent.get("question", ""), "waiting")
                ans = "skip"
                try:
                    loop = asyncio.get_event_loop()
                    f = loop.run_in_executor(
                        None, lambda: input(
                            f"\n  ? {intent.get('question', '')}\n  > "))
                    ans = await asyncio.wait_for(f, timeout=5)
                    ans = ans.strip() if ans else "skip"
                except (asyncio.TimeoutError, EOFError, RuntimeError):
                    pass
                goal = f"({goal})\nLatest feedback: {ans}"
                continue

        return {"success": False, "steps": max_steps, "log": self.history,
                "stats": self._layer_stats}

    async def _get_intent(self, goal: str, summary: dict = None) -> dict | None:
        if not self.ds:
            return None
        ctx = "\n".join([h["result"] for h in self.history[-3:]]) if self.history else "start"

        page_section = ""
        if summary:
            els = summary.get("interactive", [])[:20]
            el_lines = []
            for e in els:
                el_lines.append(f"{e['tag']}[{e.get('type','')}] {e['sel']} "
                                f"\"{e.get('placeholder') or e.get('aria') or e.get('text','')[:40]}\"")
            page_section = (
                f"URL: {summary.get('url','')}\n"
                f"Title: {summary.get('title','')}\n"
                f"Page text: {summary.get('bodyText','')[:2000]}\n"
                f"Interactive elements:\n" + "\n".join(el_lines)
            )

        try:
            resp = await self.ds.client.chat.completions.create(
                model=self.ds.model or "deepseek-v4-pro",
                messages=[{"role": "user", "content": f"""You control a Chrome browser.
Decide the next action to achieve the goal.

Goal: {goal}
{page_section}
Recent results: {ctx}

Available actions:
- click: click an element. Write JS with CSS selector from page elements.
  Example: {{"action":"click","target":"search button","js":"document.querySelector('.search-btn')?.click()"}}
- type: type text into the currently focused element.
  Example: {{"action":"type","target":"推理视频"}}
- scroll: scroll the page.
  Example: {{"action":"scroll","target":"down"}}
- navigate: open a URL.
  Example: {{"action":"navigate","target":"https://..."}}

RULES:
- After typing into an input, click the submit/search button. NEVER use press Enter.
  Correct: click(input) → type(query) → click(search-btn)
- For click, always write JS using selectors from the page elements list
- For type, just output the text, no js needed
  Example: {{"action":"navigate","target":"https://..."}}
- done: goal achieved.
  Example: {{"action":"done","target":"reason"}}

IMPORTANT for click: Only write SIMPLE one-line JS. Use selectors from the elements list.
ONLY use .click() — never .focus() or .dispatchEvent().

Output ONLY JSON: {{"action":"...","target":"...","js":"..."}}
js field is only for click actions.
"""}], stream=False)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```json"):
                raw = raw[7:].rstrip("```").strip()
            elif raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rstrip("```").strip()
            intent = json.loads(raw)
            print(f"  DS: {intent.get('action')} -> \"{intent.get('target', '')[:80]}\"")
            return intent
        except Exception as e:
            print(f"  DS error: {e}")
            return None

    # ====================================================================
    # 仅非 CDP 路径
    # ====================================================================

    def _shot(self): return pyautogui.screenshot()

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
                x = random.randint(0, a.size[0] - 1)
                y = random.randint(0, a.size[1] - 1)
                if a.getpixel((x, y)) != b.getpixel((x, y)): d += 1
            samples.append(d > 5)
        if all(samples): return "loading"
        if not any(samples): return "static"
        return "changing"

    def _write_status(self, step, layer_info, result):
        try:
            os.makedirs("outputs", exist_ok=True)
            with open(self._status_file, "w", encoding="utf-8") as f:
                json.dump({"step": step, "layer": str(layer_info)[:200],
                           "result": str(result)[:200],
                           "stats": self._layer_stats,
                           "state": self.state.status_text,
                           "ts": time.time()}, f, ensure_ascii=False)
        except Exception:
            pass

    def _img_b64(self, img):
        buf = io.BytesIO(); img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def _inject_stuck_hint(self, goal: str, target: str) -> str:
        return f"{goal}\n[Last action on \"{target}\" had no visible effect. Try a different approach.]"

    async def close(self):
        if self.planner:
            await self.planner.close()
