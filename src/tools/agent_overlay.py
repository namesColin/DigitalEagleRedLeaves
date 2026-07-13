"""
Agent 浮动监控窗 —— 完全独立，不导入项目模块。
读取 outputs/agent_status.json 每 200ms 刷新。

用法: python src/tools/agent_overlay.py
"""
import sys, json, os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

STATUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "outputs", "agent_status.json")


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("红叶 Agent")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet("""
            QWidget#main { background: rgba(18,18,22,210); border: 1px solid rgba(255,255,255,20); border-radius: 10px; }
            QLabel#t { font-size:13px; font-weight:bold; color:#4ec9b0; padding:2px; }
            QLabel#s { color:#569cd6; font-weight:bold; font-size:13px; }
            QLabel#q { color:#dcdcaa; font-size:11px; padding:1px; word-wrap:true; }
            QLabel#d { color:#c586c0; font-size:11px; }
            QLabel#r { color:#6a9955; font-size:11px; }
        """)

        self.setObjectName("main")
        container = QWidget(self); container.setObjectName("main")
        l = QVBoxLayout(container); l.setContentsMargins(10,6,10,6); l.setSpacing(2)
        l.addWidget(QLabel("🎯 红叶 Agent", objectName="t"))
        self.step_l = QLabel("等待..."); self.step_l.setObjectName("s"); l.addWidget(self.step_l)
        self.qwen_l = QLabel(""); self.qwen_l.setObjectName("q"); l.addWidget(self.qwen_l)
        self.ds_l = QLabel(""); self.ds_l.setObjectName("d"); l.addWidget(self.ds_l)
        self.res_l = QLabel(""); self.res_l.setObjectName("r"); l.addWidget(self.res_l)
        self.resize(380, 160)
        s = QApplication.primaryScreen().availableGeometry()
        self.move(s.width()-400, 40)
        container.resize(self.size())
        self._drag_pos = None

        self.timer = QTimer(); self.timer.timeout.connect(self._tick); self.timer.start(200)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def resizeEvent(self, e):
        self.findChild(QWidget, "main").resize(self.size())

    def _tick(self):
        try:
            with open(STATUS, "r", encoding="utf-8") as f: d = json.load(f)
            s = d.get("step", -1)
            self.step_l.setText(f"{'✅ 完成' if s==-1 else ('⏳ 加载' if s==0 else f'Step {s}')}")
            self.qwen_l.setText((d.get("qwen","") or "")[:300])
            self.ds_l.setText((d.get("ds","") or "")[:200])
            self.res_l.setText((d.get("result","") or "")[:150])
        except Exception: pass


def main():
    app = QApplication(sys.argv)
    w = Overlay(); w.show()
    print("监控窗已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
