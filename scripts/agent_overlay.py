"""
Agent 浮动监控窗 —— 完全独立，不导入项目模块。
读取 outputs/agent_status.json 每 0.5s 刷新。

用法: python scripts/agent_overlay.py  （另开终端运行）
"""
import sys, json
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

STATUS = "outputs/agent_status.json"


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("红叶 Agent")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setStyleSheet("""
            Overlay { background: rgba(20,20,25,230); border-radius:10px; }
            QLabel#t { font-size:14px; font-weight:bold; color:#4ec9b0; padding:2px; }
            QLabel#s { color:#569cd6; font-weight:bold; font-size:13px; }
            QLabel#q { color:#dcdcaa; font-size:12px; padding:2px; word-wrap:true; }
            QLabel#d { color:#c586c0; font-size:12px; }
            QLabel#r { color:#6a9955; font-size:12px; }
        """)
        l = QVBoxLayout(self); l.setContentsMargins(10,6,10,6); l.setSpacing(2)
        l.addWidget(QLabel("🎯 红叶 Agent", objectName="t"))
        self.step_l = QLabel("等待..."); self.step_l.setObjectName("s"); l.addWidget(self.step_l)
        self.qwen_l = QLabel(""); self.qwen_l.setObjectName("q"); l.addWidget(self.qwen_l)
        self.ds_l = QLabel(""); self.ds_l.setObjectName("d"); l.addWidget(self.ds_l)
        self.res_l = QLabel(""); self.res_l.setObjectName("r"); l.addWidget(self.res_l)
        self.resize(400, 170)
        s = QApplication.primaryScreen().availableGeometry()
        self.move(s.width()-420, 40)
        self.timer = QTimer(); self.timer.timeout.connect(self._tick); self.timer.start(500)

    def _tick(self):
        try:
            with open(STATUS, "r", encoding="utf-8") as f: d = json.load(f)
            s = d.get("step", -1)
            self.step_l.setText(f"{'✅ 完成' if s==-1 else ('⏳ 加载' if s==0 else f'Step {s}')}")
            self.qwen_l.setText(d.get("qwen","")[:250])
            self.ds_l.setText(d.get("ds","")[:180])
            self.res_l.setText(d.get("result","")[:120])
        except Exception: pass


def main():
    app = QApplication(sys.argv)
    w = Overlay(); w.show()
    print("监控窗已启动，等待 Agent 写入状态...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
