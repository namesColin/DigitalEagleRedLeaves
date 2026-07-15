"""
桌面状态追踪器 — 在每个 step 之间维护系统状态。
所有字段通过系统查询填充，不硬编码任何应用名。
"""
import pyautogui


class DesktopState:
    """跨 step 持久化的桌面状态。"""

    def __init__(self):
        self.step = 0
        self.foreground_window = ""
        self.foreground_process = ""
        self.window_rect = (0, 0, 0, 0)
        self.screen_size = pyautogui.size()
        self.cursor_pos = (0, 0)

        self.last_action = ""
        self.last_target = ""
        self.last_click_pos = (0, 0)
        self.last_result = ""
        self.last_changed = True

        self.same_click_count = 0
        self.total_steps = 0

    def update(self, step: int, action: str, target: str = "",
               result: str = "", changed: bool = True, click_pos: tuple = (0, 0)):
        self.step = step
        self.total_steps = step
        self.last_action = action
        self.last_target = target
        self.last_result = result
        self.last_changed = changed

        if action == "click" and click_pos != (0, 0):
            if (abs(click_pos[0] - self.last_click_pos[0]) < 10 and
                abs(click_pos[1] - self.last_click_pos[1]) < 10):
                self.same_click_count += 1
            else:
                self.same_click_count = 0
            self.last_click_pos = click_pos
        else:
            self.same_click_count = 0

        self._refresh()

    def _refresh(self):
        self.cursor_pos = pyautogui.position()
        try:
            import uiautomation as auto
            win = auto.GetForegroundControl()
            if win:
                self.foreground_window = win.Name or ""
                try:
                    r = win.BoundingRectangle
                    if r:
                        self.window_rect = (r.left, r.top, r.width(), r.height())
                except Exception:
                    pass
                try:
                    pid = win.ProcessId
                    if pid:
                        import psutil
                        self.foreground_process = psutil.Process(pid).name()
                except Exception:
                    self.foreground_process = ""
        except Exception:
            try:
                win = pyautogui.getActiveWindow()
                if win:
                    self.foreground_window = win.title
            except Exception:
                self.foreground_window = ""

    @property
    def is_stuck(self) -> bool:
        return self.same_click_count >= 2 and not self.last_changed

    @property
    def status_text(self) -> str:
        return (
            f"Step{self.step} | FG: {self.foreground_window[:40]} | "
            f"Last: {self.last_action}({self.last_target[:30]}) | "
            f"Changed: {self.last_changed} | Stuck: {self.is_stuck}"
        )
