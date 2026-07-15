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
                        model="qwen3-vl-plus",
                        extra_body={"enable_thinking": True, "thinking_budget": 2048},
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
        # 元素文本（含几何特征）
        et=""
        for e in els:
            t=e["ocr_text"] or e["od_label"]
            w=e["bbox"][2]-e["bbox"][0]; h=e["bbox"][3]-e["bbox"][1]
            shape=""
            if w>300 and h<80: shape=" [宽输入框]"
            elif w<50 and h<50: shape=" [小图标]"
            elif h>w*1.5: shape=" [竖向]"
            et+=f"  [{e['id']}] {w:.0f}x{h:.0f}{shape} \"{t}\" ({int(e['center'][0])},{int(e['center'][1])})\n"
        ctx="\n".join([h["result"] for h in self.history[-3:]]) if self.history else "开始"

        # Qwen: 看图说人话（缩小图片加速推理）
        qwen_desc = "（视觉模型未配置）"
        if self.qwen:
            try:
                half = img.resize((img.width//2, img.height//2))
                b64=self._img_b64(half)
                qr=await self.qwen.chat.completions.create(
                    model="qwen3-vl-plus",
                    extra_body={"enable_thinking": True, "thinking_budget": 4096},
                    messages=[{"role":"user","content":[
                        {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}},
                        {"type":"text","text":f"描述截图:\n1.当前状态(桌面/浏览器/IDE/开始菜单?)\n2.关键元素在哪个区域(顶部/底部/左侧/中间/右上角)+外观特征(长条/图标/按钮/文字)\n3.基于目标「{goal}」的下一步建议\n用自然语言回复，描述位置时要说清区域。"},
                    ]}], stream=False, timeout=60)
                qwen_desc=qr.choices[0].message.content.strip()
                print(f"  Qwen: {qwen_desc[:150]}")
                self._write_status(step, qwen_desc, "DeepSeek思考中...", "")
            except Exception as e:
                qwen_desc=f"视觉模型异常:{e}"
                print(f"  Qwen异常: {e}")

        # 根据Qwen描述过滤候选（80→~10）
        candidates, candidate_text = self._filter_candidates(qwen_desc, els)
        print(f"  候选: {len(candidates)}/{len(els)} 个")

        if self.ds:
            try:
                dr=await self.ds.client.chat.completions.create(
                    model=self.ds.model or "deepseek-v4-pro",
                    messages=[{"role":"user","content":"""
从候选元素中选最佳。目标:{goal} 描述:{qwen_desc} 历史:{ctx}

候选:
{candidates}

操作: click(N)|type("text")|press("key")|win_search("词")|ask("问题")|done("原因")
只输出JSON: {{"action":"click","element_id":3}}
""".format(goal=goal, qwen_desc=qwen_desc, candidates=candidate_text, ctx=ctx)
                    }], stream=False)
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

    def _filter_candidates(self, qwen_desc, els):
        """根据Qwen的空间描述过滤候选元素。"""
        desc = qwen_desc.lower()
        sw, sh = pyautogui.size()
        # 解析区域关键词
        regions = []
        if any(w in desc for w in ["顶部","上方","右上角","左上角","上部","顶端"]): regions.append("top")
        if any(w in desc for w in ["底部","下方","右下角","左下角","下部","底端","任务栏"]): regions.append("bottom")
        if any(w in desc for w in ["左侧","左边","左部"]): regions.append("left")
        if any(w in desc for w in ["右侧","右边","右部"]): regions.append("right")
        if any(w in desc for w in ["中间","中央","中部","中心","正中"]): regions.append("center")
        if not regions: regions = ["all"]

        # 筛选
        filtered = []
        for e in els:
            cx, cy = e["center"]
            xr, yr = cx/sw, cy/sh
            match = False
            if "all" in regions: match = True
            if "top" in regions and yr < 0.3: match = True
            if "bottom" in regions and yr > 0.7: match = True
            if "left" in regions and xr < 0.3: match = True
            if "right" in regions and xr > 0.7: match = True
            if "center" in regions and 0.25 < xr < 0.75 and 0.25 < yr < 0.75: match = True
            if match: filtered.append(e)

        if not filtered: filtered = els  # 全不匹配？回退全部

        # 生成候选文本
        txt = ""
        for e in filtered:
            t = e["ocr_text"] or e["od_label"]
            w = e["bbox"][2]-e["bbox"][0]; h = e["bbox"][3]-e["bbox"][1]
            s = ""
            if w>300 and h<80: s="[宽输入框]"
            elif w<50 and h<50: s="[小图标]"
            txt += f"  [{e['id']}] {w:.0f}x{h:.0f}{s} \"{t}\"\n"

        return filtered, txt

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
