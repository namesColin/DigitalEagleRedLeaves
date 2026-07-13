"""
Agent 浮动监控窗 —— 大窗滚动 + 可拖拽 + 实时刷新。

用法: python src/tools/agent_overlay.py
"""
import sys, json, os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                                QLabel, QScrollArea, QFrame, QSizePolicy)

STATUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "outputs", "agent_status.json")


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("红叶 Agent")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # 主容器
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(self)
        frame.setObjectName("main")
        frame.setStyleSheet("""
            QFrame#main { background: rgba(15,15,20,235); border: 1px solid rgba(78,201,176,40); border-radius: 10px; }
            QLabel#t { font-size:15px; font-weight:bold; color:#4ec9b0; padding:4px; }
            QLabel#s { font-size:14px; font-weight:bold; color:#569cd6; padding:2px 4px; }
            QLabel#q { font-size:11px; color:#c8c8c8; padding:2px 4px; line-height:1.5; word-wrap:true; }
            QLabel#d { font-size:11px; color:#c586c0; padding:2px 4px; font-weight:bold; }
            QLabel#r { font-size:11px; color:#6a9955; padding:2px 4px; }
            QLabel#sep { color:#3c3c3c; padding:0 4px; font-size:10px; }
        """)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollBar:vertical { width:6px; background:transparent; } QScrollBar::handle:vertical { background:rgba(255,255,255,30); border-radius:3px; }")

        self.content = QWidget()
        self.content.setObjectName("content")
        self.content.setStyleSheet("background:transparent;")
        self.c_layout = QVBoxLayout(self.content)
        self.c_layout.setContentsMargins(8, 6, 8, 6)
        self.c_layout.setSpacing(4)

        # 标题
        self.c_layout.addWidget(QLabel("🎯 红叶 Agent", objectName="t"))

        # 当前步骤
        self.step_l = QLabel("等待 Agent 启动...")
        self.step_l.setObjectName("s")
        self.step_l.setWordWrap(True)
        self.c_layout.addWidget(self.step_l)

        # Qwen 描述区
        self.c_layout.addWidget(QLabel("━━ 画面理解 ━━", objectName="sep"))
        self.qwen_l = QLabel("")
        self.qwen_l.setObjectName("q")
        self.qwen_l.setWordWrap(True)
        self.c_layout.addWidget(self.qwen_l)

        # DeepSeek 决策
        self.c_layout.addWidget(QLabel("━━ 操作决策 ━━", objectName="sep"))
        self.ds_l = QLabel("")
        self.ds_l.setObjectName("d")
        self.ds_l.setWordWrap(True)
        self.c_layout.addWidget(self.ds_l)

        # 执行结果
        self.res_l = QLabel("")
        self.res_l.setObjectName("r")
        self.res_l.setWordWrap(True)
        self.c_layout.addWidget(self.res_l)

        scroll.setWidget(self.content)
        outer.addWidget(frame)
        self._frame = frame

        # 内布局
        inner = QVBoxLayout(frame); inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(scroll)

        self.resize(420, 320)
        s = QApplication.primaryScreen().availableGeometry()
        self.move(s.width() - 440, 40)
        self._drag_pos = None

        self.timer = QTimer(); self.timer.timeout.connect(self._tick); self.timer.start(300)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e): self._drag_pos = None

    def resizeEvent(self, e):
        self._frame.resize(self.size())

    def _tick(self):
        try:
            with open(STATUS, "r", encoding="utf-8") as f: d = json.load(f)
            s = d.get("step", -1)
            if s == -1:
                self.step_l.setText("✅ 任务完成")
            elif s == 0:
                self.step_l.setText("⏳ 模型加载中...")
            else:
                self.step_l.setText(f"Step {s}")
            self.qwen_l.setText((d.get("qwen", "") or "")[:600])
            self.ds_l.setText((d.get("ds", "") or "")[:300])
            self.res_l.setText((d.get("result", "") or "")[:200])
        except Exception: pass


def main():
    app = QApplication(sys.argv)
    w = Overlay(); w.show()
    print("监控窗已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
