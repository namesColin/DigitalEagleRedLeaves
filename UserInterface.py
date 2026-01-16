import sys
import psutil
import collections
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QPushButton, QDialog, QCheckBox, QScrollArea, QFrame)
from PySide6.QtCore import Qt, QTimer, QPoint, QSize
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QAction

# 尝试初始化 NVML
try:
    import pynvml

    pynvml.nvmlInit()
    NVML_ENABLED = True
except Exception as e:
    print("NVML 初始化失败，GPU 监控不可用:", e)
    NVML_ENABLED = False


class Sparkline(QWidget):
    """微型实时折线图组件"""

    def __init__(self, parent=None, color=QColor(0, 255, 255)):
        super().__init__(parent)
        self.data = collections.deque([0] * 40, maxlen=40)
        self.line_color = color
        self.setFixedHeight(25)

    def add_value(self, val):
        self.data.append(val)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        if width <= 0: return

        step = width / (len(self.data) - 1)
        path_points = [QPoint(i * step, height - (v / 100.0 * height)) for i, v in enumerate(self.data)]

        if len(path_points) > 1:
            painter.setPen(QPen(self.line_color, 1.5))
            for i in range(len(path_points) - 1):
                painter.drawLine(path_points[i], path_points[i + 1])


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent, configs):
        super().__init__(parent)
        self.setWindowTitle("监控设置")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.configs = configs  # 引用父类的配置字典
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.checks = {}

        for key, cfg in self.configs.items():
            group = QFrame()
            h_lay = QHBoxLayout(group)
            h_lay.setContentsMargins(0, 5, 0, 5)

            cb_show = QCheckBox(f"显示 {cfg['name']}")
            cb_show.setChecked(cfg['show'])
            cb_show.stateChanged.connect(lambda state, k=key: self.update_cfg(k, 'show', state))

            cb_chart = QCheckBox("显示图表")
            cb_chart.setChecked(cfg['show_chart'])
            cb_chart.stateChanged.connect(lambda state, k=key: self.update_cfg(k, 'show_chart', state))

            h_lay.addWidget(cb_show)
            h_lay.addWidget(cb_chart)
            layout.addWidget(group)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_close = QPushButton("确定")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        btn_quit = QPushButton("退出应用")
        btn_quit.clicked.connect(self.quit_app)
        btn_row.addWidget(btn_quit)

        layout.addLayout(btn_row)

    def update_cfg(self, key, field, state):
        self.configs[key][field] = (state == Qt.Checked.value)
        self.parent().apply_settings()

    def quit_app(self):
        try:
            # 先关闭父窗口（若需要），再退出应用
            parent = self.parent()
            if parent is not None:
                parent.close()
            QApplication.instance().quit()
        except Exception as e:
            print("退出应用失败:", e)


class MonitorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.widgets = None
        self.layout = None
        self.set_btn = None
        self.main_container = None
        self.settings_dialog = None
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 默认配置
        self.configs = {
            'cpu': {'name': 'CPU', 'color': QColor(0, 200, 255), 'show': True, 'show_chart': True},
            'mem': {'name': 'MEM', 'color': QColor(150, 255, 100), 'show': True, 'show_chart': True},
            'gpu': {'name': 'GPU Core', 'color': QColor(255, 100, 100), 'show': True, 'show_chart': True},
            'vram': {'name': 'VRAM', 'color': QColor(255, 180, 50), 'show': True, 'show_chart': True},
            'cuda': {'name': 'CUDA', 'color': QColor(180, 100, 255), 'show': True, 'show_chart': True}
        }

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)
        self._drag_pos = None

    def init_ui(self):
        self.setFixedSize(260, 350)  # 预留足够高度
        self.main_container = QWidget(self)
        self.main_container.setObjectName("bg")
        self.main_container.setGeometry(0, 0, 260, 350)
        self.main_container.setStyleSheet("""
            QWidget#bg { background: rgba(20, 20, 20, 200); border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); }
            QLabel { color: white; font-family: 'Segoe UI'; font-size: 12px; }
            QPushButton#set_btn { background: rgba(255,255,255,20); border-radius: 5px; color: gray; font-size: 10px; }
            QPushButton#set_btn:hover { background: rgba(255,255,255,50); color: white; }
        """)

        self.layout = QVBoxLayout(self.main_container)
        self.layout.setContentsMargins(15, 10, 15, 15)

        # 顶部栏：设置按钮
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.set_btn = QPushButton("⚙", self.main_container)
        self.set_btn.setObjectName("set_btn")
        self.set_btn.setFixedSize(24, 24)
        self.set_btn.clicked.connect(self.show_settings)
        top_bar.addWidget(self.set_btn)
        self.layout.addLayout(top_bar)

        # 动态生成的监控行字典
        self.widgets = {}
        for key, cfg in self.configs.items():
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(2)

            lbl = QLabel(f"{cfg['name']}: ---")
            chart = Sparkline(self, cfg['color'])

            row_layout.addWidget(lbl)
            row_layout.addWidget(chart)
            self.layout.addWidget(row_widget)

            self.widgets[key] = {'row': row_widget, 'lbl': lbl, 'chart': chart}

        self.apply_settings()

    def apply_settings(self):
        """根据配置更新界面显示/隐藏，并自适应窗口高度"""
        visible_count = 0
        for key, cfg in self.configs.items():
            w = self.widgets[key]
            w['row'].setVisible(cfg['show'])
            w['chart'].setVisible(cfg['show_chart'])
            if cfg['show']:
                visible_count += 1

        # 动态调整窗口高度 (基础高度 + 每个显示行的高度)
        new_height = 40 + (
            visible_count * 55 if any(c['show_chart'] for c in self.configs.values()) else visible_count * 30)
        self.setFixedHeight(max(new_height, 60))
        self.main_container.setFixedHeight(self.height())

    def show_settings(self):
        try:
            print("正在打开设置...")
            # 1. 创建对话框时确保传入 self 作为 parent
            self.settings_dialog = SettingsDialog(self, self.configs)

            # 2. 移除 WindowStaysOnTopHint，或者确保它拥有和父类一样的置顶属性
            # 有时显式设置这个能解决被挡住的问题
            self.settings_dialog.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

            # 3. 将位置设置在主窗口的左边（避免重叠）
            main_geo = self.geometry()
            self.settings_dialog.move(main_geo.left() - 250, main_geo.top())

            # 4. 使用 exec() 运行。这会阻塞主窗口交互，直到设置完成，最稳妥
            print("设置窗口以模态方式弹出")
            self.settings_dialog.exec()

        except Exception as e:
            print(f"弹出失败: {e}")

    def update_stats(self):
        # 1. CPU/MEM
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        self.widgets['cpu']['lbl'].setText(f"CPU: {cpu:.0f}%")
        self.widgets['cpu']['chart'].add_value(cpu)
        self.widgets['mem']['lbl'].setText(f"MEM: {mem:.1f}%")
        self.widgets['mem']['chart'].add_value(mem)

        # 2. GPU (NVML)
        if NVML_ENABLED:
            try:
                h = pynvml.nvmlDeviceGetHandleByIndex(0)
                u = pynvml.nvmlDeviceGetUtilizationRates(h)
                m = pynvml.nvmlDeviceGetMemoryInfo(h)
                t = pynvml.nvmlDeviceGetTemperature(h, 0)
                vram = (m.used / m.total) * 100

                self.widgets['gpu']['lbl'].setText(f"GPU Core: {u.gpu}%  {t}°C")
                self.widgets['gpu']['chart'].add_value(u.gpu)
                self.widgets['vram']['lbl'].setText(f"VRAM: {vram:.1f}%")
                self.widgets['vram']['chart'].add_value(vram)
                self.widgets['cuda']['lbl'].setText(f"CUDA Load: {u.gpu}%")  # 近似
                self.widgets['cuda']['chart'].add_value(u.gpu)
            except Exception as e:
                print("NVML 读取失败:", e)
                pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MonitorWidget()
    w.show()
    sys.exit(app.exec())