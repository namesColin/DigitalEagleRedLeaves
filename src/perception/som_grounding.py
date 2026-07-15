"""
Layer 2: Set-of-Mark 视觉定位
在截图上画编号框 → Qwen 直接看图选号 → 返回坐标
不做文字描述中转，视觉直接定位。
"""
import io, base64, re
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


class SomGrounding:
    """
    Set-of-Mark 视觉定位器。

    思路：不给 Qwen 看 80 个框，而是把截图裁剪到目标区域，
    只标注 ~10-20 个候选框，让 Qwen 直接说出编号。
    视觉 → 数字，不经过文字描述。
    """

    def __init__(self, qwen_client=None):
        self.qwen = qwen_client

    async def ground(
        self,
        img: Image.Image,
        elements: list[dict],
        goal: str,
        crop_region: tuple | None = None,
        context_hint: str = "",
    ) -> Optional[dict]:
        """
        img: 原始截图
        elements: [{id, bbox, od_label, ocr_text, ...}]
        goal: 任务目标
        crop_region: (x, y, w, h) 可选裁剪
        context_hint: 额外上下文提示（如 UIA 给出的窗口信息）
        returns: 选中的 element 或 None
        """
        if not self.qwen or not elements:
            return None

        # 1. 裁剪
        if crop_region is not None:
            cx, cy, cw, ch = crop_region
            img = img.crop((cx, cy, cx + cw, cy + ch))
            adj_elements = []
            for e in elements:
                bx, by = e["bbox"][0], e["bbox"][1]
                bw = e["bbox"][2] - e["bbox"][0]
                bh = e["bbox"][3] - e["bbox"][1]
                # 完全在裁剪区域内
                if bx >= cx and by >= cy and bx + bw <= cx + cw and by + bh <= cy + ch:
                    nb = [bx - cx, by - cy, bx - cx + bw, by - cy + bh]
                    nc = (nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2
                    adj_elements.append({**e, "bbox": nb, "center": nc})
                else:
                    # 部分在裁剪区域内
                    nb = [
                        max(0, bx - cx),
                        max(0, by - cy),
                        min(cw, bx - cx + bw),
                        min(ch, by - cy + bh),
                    ]
                    if nb[2] > nb[0] and nb[3] > nb[1]:
                        nc = (nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2
                        adj_elements.append({**e, "bbox": nb, "center": nc})
            elements = adj_elements

        if not elements:
            return None

        # 2. 限制数量
        if len(elements) > 25:
            elements = sorted(
                elements,
                key=lambda e: (e["bbox"][2] - e["bbox"][0]) * (e["bbox"][3] - e["bbox"][1]),
                reverse=True,
            )[:25]
            elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))

        # 3. 画编号框
        annotated = self._draw_boxes(img, elements)

        # 4. 缩放
        w, h = annotated.size
        if max(w, h) > 1600:
            scale = 1600 / max(w, h)
            annotated = annotated.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        # 5. Qwen 直选
        b64 = self._img_b64(annotated)

        prompt = (
            f"图片上的编号框是可选元素。请选出最符合目标的元素。\n"
            f"目标: {goal}\n"
        )
        if context_hint:
            prompt += f"上下文: {context_hint}\n"
        prompt += "\n只输出一个数字，例如: 5\n如果没有合适的元素，输出: none"

        try:
            resp = await self.qwen.chat.completions.create(
                model="qwen3-vl-plus",
                extra_body={"enable_thinking": True, "thinking_budget": 2048},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                stream=False,
                timeout=30,
            )
            raw = resp.choices[0].message.content.strip()
            print(f"  SoM Qwen → \"{raw[:120]}\"")
            nums = re.findall(r"\d+", raw)
            if not nums:
                return None
            eid = int(nums[0])
            for e in elements:
                if e["id"] == eid:
                    return e
            return None
        except Exception as exc:
            print(f"  SoM error: {exc}")
            return None

    def _draw_boxes(self, img: Image.Image, elements: list[dict]) -> Image.Image:
        """在图像上画彩色编号框。"""
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas)
        colors = [
            "#FF4444", "#44FF44", "#4488FF", "#FFAA00",
            "#FF44FF", "#00CCCC", "#FF8888", "#88FF88",
        ]
        try:
            font = ImageFont.truetype("consola.ttf", size=16)
        except Exception:
            font = ImageFont.load_default()

        for i, e in enumerate(elements):
            b = e["bbox"]
            color = colors[i % len(colors)]
            x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            label = f"[{e['id']}]"
            try:
                tw = draw.textlength(label, font=font)
            except Exception:
                tw = 40
            draw.rectangle(
                [x1, max(0, y1 - 20), x1 + int(tw) + 8, y1],
                fill=color,
            )
            draw.text((x1 + 2, max(0, y1 - 20)), label, fill="#FFFFFF", font=font)
        return canvas

    def _img_b64(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
