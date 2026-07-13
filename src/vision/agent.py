"""
视觉 Agent：接收目标 → 自闭环执行 → 返回结果。
不依赖 VLM——用 OmniParser 检测 + OCR 文字 + 几何匹配。
"""
import time, math, random
import pyautogui
import pyperclip


class VisionAgent:
    def __init__(self, vision_module):
        self.vision = vision_module
        self.history = []

    async def run(self, goal: str, max_steps: int = 20) -> dict:
        print(f"\n🎯 Agent: {goal}")
        prev = None

        for step in range(1, max_steps + 1):
            print(f"\n─ Step {step} ─")

            # ① 截屏 + 检测
            img = self._shot()
            od = await self.vision.analyze(img, "<OD>")
            ocr = await self.vision.analyze(img, "<OCR_WITH_REGION>")
            els = self._index(
                od.get("boxes", []), od.get("labels", []),
                ocr.get("labels", []), ocr.get("boxes", []),
            )

            # ② 决策：OCR 文字匹配 + 关键词 + 几何推断
            act = self._decide(goal, els, step)

            # ③ 执行
            msg = self._exec(act, els)
            print(f"  → {msg}")

            # ④ 验证
            time.sleep(2)
            cur = self._shot()
            changed = self._changed(prev, cur)
            prev = cur
            self.history.append({"step": step, "action": act.get("action"),
                                  "target": act.get("target", ""), "result": msg,
                                  "changed": changed})

            if act.get("action") == "done":
                print(f"\n✅ {msg}")
                return {"success": True, "steps": step, "log": self.history}
            if act.get("action") == "ask":
                ans = input(f"\n  🤔 {act['question']}\n  → ").strip()
                goal = f"{goal}（补充：{ans}）"
                continue
            if not changed and act.get("action") == "click":
                print("  ⚠ 点击后画面未变——可能点错")

        return {"success": False, "steps": max_steps, "log": self.history}

    # ─── 内部 ───

    def _shot(self): return pyautogui.screenshot()

    def _index(self, od_b, od_l, ocr_t, ocr_b):
        els = []
        for i, (b, lbl) in enumerate(zip(od_b, od_l)):
            if len(b) != 4: continue
            cx, cy = (b[0]+b[2])/2, (b[1]+b[3])/2
            e = {"id": i, "bbox": list(b), "center": (cx, cy), "od_label": lbl, "ocr_text": ""}
            if ocr_t and ocr_b:
                best, bd = "", 120
                for t, ob in zip(ocr_t, ocr_b):
                    t = str(t).replace("</s>","").replace("<s>","").strip()
                    if len(t) < 2: continue
                    ox, oy = self._c(ob); d = math.hypot(cx-ox, cy-oy)
                    if d < bd: best, bd = t, d
                e["ocr_text"] = best
            els.append(e)
        return els

    def _c(self, box):
        if len(box) == 8: return sum(box[0:8:2])/4, sum(box[1:8:2])/4
        if len(box) == 4: return (box[0]+box[2])/2, (box[1]+box[3])/2
        return 0, 0

    def _decide(self, goal, els, step):
        import re
        gl = goal.lower()

        # 1. OCR 文字精确匹配
        kw = re.split(r'[，,、\s]+', goal)
        for k in kw:
            if len(k) < 2: continue
            ms = [e for e in els if k.lower() in e["ocr_text"].lower()]
            if ms:
                e = max(ms, key=lambda x: (x["bbox"][2]-x["bbox"][0])*(x["bbox"][3]-x["bbox"][1]))
                return {"action": "click", "element_id": e["id"],
                        "target": f"OCR「{k}」→[{e['id']}]「{e['ocr_text']}」"}

        # 2. OD 标签匹配
        for k in kw:
            if len(k) < 2: continue
            for e in els:
                if k.lower() in e["od_label"].lower():
                    return {"action": "click", "element_id": e["id"],
                            "target": f"标签「{k}」→[{e['id']}]「{e['od_label']}」"}

        # 3. 特殊意图
        if any(w in gl for w in ["打开","启动","chrome","浏览器"]):
            for e in els:
                if "chrome" in e["ocr_text"].lower():
                    return {"action":"click","element_id":e["id"],"target":f"OCR Chrome→[{e['id']}]"}
            return {"action":"win_search","query":"chrome","target":"未找到Chrome，Win搜索"}
        if any(w in gl for w in ["输入","网址","地址栏","bilibili","搜索框","主页"]):
            for e in els:
                w = e["bbox"][2]-e["bbox"][0]
                if w > 300 and e["bbox"][3]-e["bbox"][1] < 80:
                    return {"action":"click","element_id":e["id"],"target":f"宽输入框{w}px→[{e['id']}]"}
            # 有地址栏但没匹配到宽输入框 → 试试关键词
            for e in els:
                if any(w in e["ocr_text"].lower() for w in ["http","www","bilibili","com"]):
                    return {"action":"click","element_id":e["id"],"target":f"OCR网址→[{e['id']}]"}
            return {"action":"type","text":"bilibili.com","target":"输入网址"}
        if any(w in gl for w in ["bilibili","b站"]):
            for e in els:
                if "bilibili" in e["ocr_text"].lower():
                    return {"action":"click","element_id":e["id"],"target":f"OCR bilibili→[{e['id']}]"}
        if any(w in gl for w in ["登录","登录","进入"]):
            for e in els:
                if any(w in e["ocr_text"].lower() for w in ["登录","sign in","continue","进入","确定","确认"]):
                    return {"action":"click","element_id":e["id"],"target":f"OCR登录→[{e['id']}]"}

        # 4. 兜底
        return {"action":"ask","question":f"第{step}步无法自动匹配。目标:「{goal}」请指示"}

    def _exec(self, act, els):
        a = act.get("action","")
        if a == "click":
            eid = act.get("element_id")
            if eid is not None and 0 <= eid < len(els):
                b = els[eid]["bbox"]
                pyautogui.click((b[0]+b[2])//2, (b[1]+b[3])//2)
                return f"点[{eid}]「{els[eid]['ocr_text'] or els[eid]['od_label']}」"
            return f"click id={eid}无效"
        elif a == "win_search":
            q = act.get("query",""); pyautogui.hotkey("win"); time.sleep(0.3)
            pyautogui.write(q); time.sleep(0.2); pyautogui.press("enter")
            return f"Win搜「{q}」"
        elif a == "type":
            t = act.get("text",""); pyperclip.copy(t); pyautogui.hotkey("ctrl","v")
            return f"输入「{t}」"
        elif a == "press":
            pyautogui.press(act.get("key","enter")); return f"按{act.get('key','enter')}"
        elif a == "ask": return f"问:{act.get('question','')}"
        elif a == "done": return f"完成:{act.get('reason','')}"
        return f"未知:{a}"

    def _changed(self, prev, cur):
        if prev is None: return True
        if abs(prev.size[0]-cur.size[0])>5 or abs(prev.size[1]-cur.size[1])>5: return True
        for _ in range(200):
            x = random.randint(0, prev.size[0]-1); y = random.randint(0, prev.size[1]-1)
            if prev.getpixel((x,y)) != cur.getpixel((x,y)): return True
        return False
