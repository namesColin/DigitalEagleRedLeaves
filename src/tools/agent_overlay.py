"""Agent 浮动窗：右上角透明窗口，显示进度 + 提问，不干扰截屏。"""
import sys, time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QHBoxLayout,
)


class AgentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self._answer = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("红叶 Agent")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setStyleSheet("""
            AgentOverlay { background: rgba(25,25,30,230); border-radius:10px; }
            QLabel#t { font-size:14px; font-weight:bold; color:#4ec9b0; padding:2px; }
            QLabel#s { color:#569cd6; font-weight:bold; }
            QLabel#q { color:#dcdcaa; word-wrap:true; }
            QLineEdit { background:#3c3c3c; border:1px solid #569cd6; border-radius:4px;
                        padding:4px; color:#e0e0e0; }
            QPushButton { background:#569cd6; color:#fff; border-radius:4px; padding:4px 10px; }
        """)
        l = QVBoxLayout(self); l.setContentsMargins(10,6,10,6); l.setSpacing(3)
        l.addWidget(QLabel("🎯 红叶 Agent", objectName="t"))
        self.step_l = QLabel(""); self.step_l.setObjectName("s"); l.addWidget(self.step_l)
        self.qwen_l = QLabel(""); self.qwen_l.setObjectName("q"); l.addWidget(self.qwen_l)
        self.ds_l = QLabel(""); self.ds_l.setStyleSheet("color:#c586c0"); l.addWidget(self.ds_l)
        self.res_l = QLabel(""); self.res_l.setStyleSheet("color:#6a9955"); l.addWidget(self.res_l)
        self.ask_ct = QWidget(); al = QHBoxLayout(self.ask_ct); al.setContentsMargins(0,0,0,0)
        self.ask_in = QLineEdit(); self.ask_in.setPlaceholderText("回答...")
        self.ask_in.returnPressed.connect(self._submit)
        b = QPushButton("发送"); b.clicked.connect(self._submit)
        al.addWidget(self.ask_in); al.addWidget(b); self.ask_ct.hide(); l.addWidget(self.ask_ct)
        self.resize(380, 200)
        s = QApplication.primaryScreen().availableGeometry()
        self.move(s.width()-400, 40)

    def update(self, step, qwen, ds, res):
        self.step_l.setText(f"Step {step}")
        self.qwen_l.setText((qwen or "")[:200])
        self.ds_l.setText((ds or "")[:150])
        self.res_l.setText((res or "")[:100])
        self.ask_ct.hide()
        QApplication.processEvents()

    def ask(self, q, timeout=90):
        self._answer = None; self.qwen_l.setText(q)
        self.ask_in.clear(); self.ask_ct.show(); self.ask_in.setFocus()
        for _ in range(timeout * 10):
            if self._answer is not None: break
            QApplication.processEvents(); time.sleep(0.1)
        self.ask_ct.hide()
        return self._answer or ""

    def _submit(self):
        self._answer = self.ask_in.text().strip() or "跳过"


_inst = None


def get_overlay():
    global _inst
    if _inst is None:
        app = QApplication.instance() or QApplication(sys.argv)
        _inst = AgentOverlay(); _inst.show()
    return _inst
