"""
视觉 Agent：Qwen 看图说话 + DeepSeek 文本匹配 + OmniParser 精确定位
不设白名单——两个模型各做各擅长的事。
"""
import time, math, random, re, io, base64, json, asyncio
import pyautogui, pyperclip


class VisionAgent:
    def __init__(self, vision_module, qwen_client=None, ds_client=None):
        self.vision = vision_module
        self.qwen = qwen_client
        self.ds = ds_client
        self.history = []
        self._prev_shots = []
        self._status_file = "outputs/agent_status.json"

    async def run(self, goal, max_steps=20):
        print(f"\n🎯 Agent: {goal}")
        expected = "（首次）"
        for s in range(1, max_steps+1):
            print(f"\n─ Step {s} ─")
            img = self._shot()
            # 并行 OD + OCR
            od, ocr = await asyncio.gather(
                self.vision.analyze(img, "<OD>"),
                self.vision.analyze(img, "<OCR_WITH_REGION>"),
            )
            els = self._index(od.get("boxes",[]), od.get("labels",[]),
                              ocr.get("labels",[]), ocr.get("boxes",[]))

            act = await self._decide(goal, els, img, s, expected)
            msg = self._exec(act, els)
            print(f"  → {msg}")
            time.sleep(1)

            # 写状态文件（供独立浮窗工具读取）
            self._write_status(s, act.get("qwen_desc",""),
                               f"{act.get('action')}: {act.get('reason','')}", msg)

            # 因果追踪
            if self.qwen and act.get("action") not in ("ask","done"):
                try:
                    cur = self._shot(); b64 = self._img_b64(cur)
                    er = await self.qwen.chat.completions.create(
                        model="qwen3.7-plus",
                        messages=[{"role":"user","content":[
                            {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}},
                            {"type":"text","text":f"我刚做了: {msg}\n上一步预期: {expected}\n看截图简短描述: 1.实际发生了什么 2.接下来预期看到什么（一句话）"},
                        ]}], stream=False, timeout=30)
                    expected = er.choices[0].message.content.strip()
                except Exception:
                    expected = "（未知）"

            cur = self._shot(); t = self._timing(cur)
            self.history.append({"step":s,"action":act.get("action"),"result":msg,"timing":t,"expected":expected})

            if act.get("action")=="done": return {"success":True,"steps":s,"log":self.history}
            if act.get("action")=="ask":
                self._write_status(s, act["question"], "需要回答", "")
                ans = input(f"\n  🤔 {act['question']}\n  → ").strip()
                if not ans: ans = "跳过"
                goal = f"原始任务: {goal.split(chr(10))[0]}\n当前指令: {ans}"
                expected = f"用户指示: {ans}"; continue
            if t=="static" and act.get("action")=="click": print("  ⚠ 画面未变化")
        return {"success":False,"steps":max_steps,"log":self.history}

    def _shot(self): return pyautogui.screenshot()

    def _index(self, od_b, od_l, ocr_t, ocr_b):
        els=[]
        for i,(b,lbl) in enumerate(zip(od_b,od_l)):
            if len(b)!=4: continue
            cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2
            e={"id":i,"bbox":list(b),"center":(cx,cy),"od_label":lbl,"ocr_text":""}
            if ocr_t and ocr_b:
                best,bd="",120
                for t,ob in zip(ocr_t,ocr_b):
                    t=str(t).replace("</s>","").replace("<s>","").strip()
                    if len(t)<2: continue
                    ox,oy=self._c(ob); d=math.hypot(cx-ox,cy-oy)
                    if d<bd: best,bd=t,d
                e["ocr_text"]=best
            els.append(e)
        return els

    def _c(self,b):
        if len(b)==8: return sum(b[0:8:2])/4,sum(b[1:8:2])/4
        if len(b)==4: return (b[0]+b[2])/2,(b[1]+b[3])/2
        return 0,0

    def _timing(self, cur):
        self._prev_shots.append(cur)
        if len(self._prev_shots)>4: self._prev_shots.pop(0)
        if len(self._prev_shots)<3: return "first"
        samples=[]
        for i in range(len(self._prev_shots)-1):
            a,b=self._prev_shots[i],self._prev_shots[i+1]
            if a.size!=b.size: samples.append(True); continue
            d=0
            for _ in range(100):
                x=random.randint(0,a.size[0]-1); y=random.randint(0,a.size[1]-1)
                if a.getpixel((x,y))!=b.getpixel((x,y)): d+=1
            samples.append(d>5)
        if all(samples): return "loading"
        if not any(samples): return "static"
        return "changing"

    async def _decide(self, goal, els, img, step, expected="（首次）"):
        # 元素文本
        et=""
        for e in els:
            t=e["ocr_text"] or e["od_label"]
            et+=f"  [{e['id']}] \"{t}\" ({int(e['center'][0])},{int(e['center'][1])})\n"
        ctx="\n".join([h["result"] for h in self.history[-3:]]) if self.history else "开始"

        # Qwen: 看图说人话（缩小图片加速推理）
        qwen_desc = "（视觉模型未配置）"
        if self.qwen:
            try:
                half = img.resize((img.width//2, img.height//2))
                b64=self._img_b64(half)
                qr=await self.qwen.chat.completions.create(
                    model="qwen3.7-plus",
                    messages=[{"role":"user","content":[
                        {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}},
                        {"type":"text","text":f"你是桌面操作员。看截图简短描述:\n1.当前屏幕状态\n2.关键元素和位置\n3.基于目标「{goal}」的建议\n回复自然语言，不要JSON。"},
                    ]}], stream=False, timeout=60)
                qwen_desc=qr.choices[0].message.content.strip()
                print(f"  Qwen: {qwen_desc[:150]}")
            except Exception as e:
                qwen_desc=f"视觉模型异常:{e}"
                print(f"  Qwen异常: {e}")

        # DeepSeek: 文本匹配→结构化JSON
        if self.ds:
            try:
                dr=await self.ds.client.chat.completions.create(
                    model=self.ds.model or "deepseek-v4-pro",
                    messages=[{"role":"user","content":f"""根据视觉描述和元素列表，匹配下一步操作。

【视觉描述】{qwen_desc}
【元素列表】{et}
【目标】{goal}
【历史】{ctx}
【上一步预期】{expected}

⚠️ 如果实际画面和上一步预期不一致（如预期打开Chrome却弹出了恢复会话窗口），应优先处理意外状态。

找出与描述最匹配的元素编号。操作: click(N), type("text"), press("enter"), win_search("词"), ask("问题"), done("原因")

只输出JSON:
{{"action":"click","element_id":3,"reason":"Colin在元素3"}}
{{"action":"win_search","query":"chrome","reason":"桌面无Chrome"}}
{{"action":"type","text":"bilibili.com","reason":"输入网址"}}
{{"action":"click","element_id":5,"reason":"预期打开Chrome但弹出恢复会话，点否关掉"}}
{{"action":"done","reason":"已看到bilibili"}}"""}], stream=False)
                raw=dr.choices[0].message.content.strip()
                if raw.startswith("```"): raw=raw.split("\n",1)[1].rstrip("```").strip()
                act=json.loads(raw)
                print(f"  DS: {act.get('action')} — {act.get('reason','')[:80]}")
                act["qwen_desc"] = qwen_desc
                return act
            except Exception as e:
                print(f"  DS异常: {e}")

        # 兜底：OCR文本匹配
        kw=[w for w in re.split(r'[，,、\s]+', goal) if len(w)>=2]
        for k in kw:
            ms=[e for e in els if k.lower() in e["ocr_text"].lower()]
            if ms:
                e=max(ms,key=lambda x:(x["bbox"][2]-x["bbox"][0])*(x["bbox"][3]-x["bbox"][1]))
                return {"action":"click","element_id":e["id"],
                        "reason":f"OCR匹配「{k}」→[{e['id']}]「{e['ocr_text']}」"}

        preview="\n".join(f"  [{e['id']}] {e['ocr_text'] or e['od_label'][:40]}" for e in els[:12])
        return {"action":"ask","question":f"第{step}步: 「{goal}」\n当前:\n{preview}\n→ 指示编号或搜索词"}

    def _write_status(self, step, qwen_desc, ds_action, result):
        """写状态JSON文件，供独立浮窗工具读取。"""
        try:
            import os
            os.makedirs("outputs", exist_ok=True)
            with open(self._status_file, "w", encoding="utf-8") as f:
                json.dump({"step":step,"qwen":qwen_desc[:300],
                           "ds":ds_action[:200],"result":result[:200],
                           "ts":time.time()}, f, ensure_ascii=False)
        except Exception: pass

    def _img_b64(self, img):
        buf=io.BytesIO(); img.save(buf,format="PNG"); return base64.b64encode(buf.getvalue()).decode()

    def _exec(self, act, els):
        a=act.get("action","")
        if a=="click":
            eid=act.get("element_id")
            if eid is not None and 0<=eid<len(els):
                b=els[eid]["bbox"]; pyautogui.click((b[0]+b[2])//2,(b[1]+b[3])//2)
                return f"点[{eid}]「{els[eid]['ocr_text'] or els[eid]['od_label']}」"
            return f"click id={eid}无效"
        elif a=="win_search":
            q=act.get("query",""); pyautogui.hotkey("win"); time.sleep(0.3)
            pyautogui.write(q); time.sleep(0.2); pyautogui.press("enter")
            return f"Win搜「{q}」"
        elif a=="type":
            t=act.get("text",""); pyperclip.copy(t); pyautogui.hotkey("ctrl","v")
            return f"输入「{t}」"
        elif a=="press":
            pyautogui.press(act.get("key","enter")); return f"按{act.get('key','enter')}"
        elif a=="ask": return f"问:{act.get('question','')}"
        elif a=="done": return f"完成:{act.get('reason','')}"
        return f"未知:{a}"
