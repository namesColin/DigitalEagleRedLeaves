"""
光标探索器 — 移动鼠标到大致位置，截图小区域让 Qwen 验证是否可交互。
模拟人类"先悬停看光标变化"的操作方式。
"""
import io, base64, asyncio, json, re
from typing import Optional
import pyautogui
from PIL import Image

pyautogui.FAILSAFE = False


class CursorExplorer:
    """光标探索式交互：先悬停探测，确认可交互后再点击。"""

    def __init__(self, qwen_client=None):
        self.qwen = qwen_client
        self._hover_radius = 60

    async def probe(self, x: int, y: int, goal: str = "") -> Optional[dict]:
        """在 (x, y) 处悬停并探测是否可交互。"""
        pyautogui.moveTo(x, y, duration=0.15)
        await asyncio.sleep(0.2)

        region = (
            max(0, x - self._hover_radius),
            max(0, y - self._hover_radius),
            self._hover_radius * 2,
            self._hover_radius * 2,
        )
        img = pyautogui.screenshot(region=region)

        if not self.qwen:
            return {"element": "unknown", "clickable": True, "adjust": "none"}

        b64 = self._img_b64(img)
        try:
            resp = await self.qwen.chat.completions.create(
                model="qwen3-vl-plus",
                extra_body={"enable_thinking": True, "thinking_budget": 1024},
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": (
                        f"截图中心是鼠标光标所在位置。目标: {goal}\n"
                        f"回答:\n"
                        f"1. 光标下面是什么？（按钮/输入框/链接/纯文本/图标/空白）\n"
                        f"2. 点击这里能推进目标吗？（yes/no/maybe）\n"
                        f"3. 如果不能，往哪个方向找？（left/right/up/down/none）\n"
                        f'输出 JSON: {{"element":"...","clickable":true/false,"adjust":"left/right/up/down/none"}}'
                    )},
                ]}], stream=False, timeout=20,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rstrip("```").strip()
            result = json.loads(raw)
            print(f"  [cursor] ({x},{y}): {result.get('element','?')} clickable={result.get('clickable')}")
            return result
        except Exception as e:
            print(f"  [cursor] error: {e}")
            return None

    async def explore_region(
        self, center_x: int, center_y: int, goal: str = "", radius: int = 80
    ) -> Optional[dict]:
        """在区域内九宫格采样探测，返回最佳可点击位置。"""
        offsets = [
            (0, 0), (-radius, 0), (radius, 0),
            (0, -radius), (0, radius),
            (-radius, -radius), (radius, -radius),
            (-radius, radius), (radius, radius),
        ]
        w, h = pyautogui.size()
        for dx, dy in offsets:
            px = max(10, min(w - 10, center_x + dx))
            py = max(10, min(h - 10, center_y + dy))
            result = await self.probe(px, py, goal)
            if result and result.get("clickable"):
                return {"x": px, "y": py, "element": result.get("element", ""), "source": "cursor"}
            if result and result.get("adjust") != "none":
                direction = result["adjust"]
                adjust_map = {"left": (-30, 0), "right": (30, 0), "up": (0, -30), "down": (0, 30)}
                adj = adjust_map.get(direction, (0, 0))
                nx = max(10, min(w - 10, px + adj[0]))
                ny = max(10, min(h - 10, py + adj[1]))
                result2 = await self.probe(nx, ny, goal)
                if result2 and result2.get("clickable"):
                    return {"x": nx, "y": ny, "element": result2.get("element", ""), "source": "cursor"}
        return None

    def _img_b64(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
