"""
Layer 1: UIA 控件扫描器
通过 Windows UI Automation API 获取精确控件信息。
覆盖: 原生 Windows 应用、文件资源管理器、系统对话框、Office 等
不覆盖: 浏览器网页内容、游戏、自定义渲染 UI
"""
import uiautomation as auto
from typing import Optional


class UiaScanner:
    """扫描当前桌面/窗口的 UIA 控件树，输出与 OmniParser 兼容的元素列表。"""

    def __init__(self):
        self._cache_ts = 0
        self._cache = []

    def scan_active_window(self, max_depth: int = 6) -> list[dict]:
        """扫描当前前台窗口（或最顶层可见窗口）的控件树。"""
        win = auto.GetForegroundControl()
        if not win:
            return []
        return self._scan_window(win, max_depth)

    def scan_window_by_title(self, title: str, max_depth: int = 6) -> list[dict]:
        """按窗口标题模糊匹配。"""
        win = auto.WindowControl(searchDepth=1, Name=title)
        if not win or not win.Exists(0):
            return []
        return self._scan_window(win, max_depth)

    def scan_by_criteria(
        self, name: str = "", control_type: str = "", max_depth: int = 6
    ) -> list[dict]:
        """通用搜索：按名称或控件类型。"""
        results = []
        conditions = []
        if name:
            conditions.append(lambda c: name.lower() in (c.Name or "").lower())
        if control_type:
            conditions.append(
                lambda c, ct=control_type: ct.lower() in (c.ControlTypeName or "").lower()
            )
        if not conditions:
            return []

        def _match(c):
            return all(cond(c) for cond in conditions)

        root = auto.GetRootControl()
        self._search_tree(root, _match, results, 0, max_depth)
        return results

    def find_by_name(self, name: str) -> Optional[dict]:
        """精确查找命名控件，返回最匹配的一个。"""
        results = self.scan_by_criteria(name=name)
        if not results:
            return None
        exact = [r for r in results if r["name"].lower() == name.lower()]
        return (exact or results)[0]

    def _scan_window(self, win, max_depth: int) -> list[dict]:
        """扫描单个窗口的控件树。"""
        elements = []
        try:
            win_info = self._describe(win, depth=0)
            if win_info:
                elements.append(win_info)
            for child in win.GetChildren():
                elements.extend(self._walk(child, max_depth, depth=1))
        except Exception:
            pass
        for i, e in enumerate(elements):
            e["id"] = i
        return elements

    def _walk(self, control, max_depth: int, depth: int) -> list[dict]:
        if depth > max_depth:
            return []
        results = []
        info = self._describe(control, depth)
        if info:
            results.append(info)
        try:
            for child in control.GetChildren():
                results.extend(self._walk(child, max_depth, depth + 1))
        except Exception:
            pass
        return results

    def _search_tree(self, control, match_fn, results: list, depth: int, max_depth: int):
        if depth > max_depth:
            return
        info = self._describe(control, depth)
        if info and match_fn(control):
            results.append(info)
        try:
            for child in control.GetChildren():
                self._search_tree(child, match_fn, results, depth + 1, max_depth)
        except Exception:
            pass

    def _describe(self, control, depth: int = 0) -> dict | None:
        """将 UIA 控件转为与 OmniParser 兼容的元素格式。"""
        try:
            name = control.Name or ""
            ctype = control.ControlTypeName or ""
            r = control.BoundingRectangle
            if not r:
                return None
            x, y, w, h = r.left, r.top, r.right - r.left, r.bottom - r.top
            if w <= 0 or h <= 0:
                return None

            bbox = [x, y, x + w, y + h]
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2

            label = name if name else ctype
            if name and ctype:
                label = f"{name} [{ctype}]"

            return {
                "id": -1,
                "bbox": bbox,
                "center": (cx, cy),
                "od_label": label,
                "ocr_text": name,
                "source": "uia",
                "control_type": ctype,
                "depth": depth,
            }
        except Exception:
            return None


def quick_scan():
    """快速打印前台窗口控件（调试用）。"""
    s = UiaScanner()
    elements = s.scan_active_window(max_depth=4)
    print(f"UIA: {len(elements)} elements in foreground window\n")
    for e in elements[:20]:
        b = e["bbox"]
        print(
            f"  [{e['id']}] UIA {e['control_type']:20s} "
            f"\"{e['ocr_text'][:50]}\" ({int(e['center'][0])},{int(e['center'][1])})"
        )
    return elements


if __name__ == "__main__":
    quick_scan()
