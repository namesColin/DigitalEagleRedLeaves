# python
import sys
import psutil
import collections
import subprocess
import shutil
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QPushButton, QDialog, QCheckBox, QScrollArea, QFrame, QComboBox)
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
        if width <= 0:
            return

        step = width / (len(self.data) - 1)
        path_points = [QPoint(i * step, height - (v / 100.0 * height)) for i, v in enumerate(self.data)]

        if len(path_points) > 1:
            painter.setPen(QPen(self.line_color, 1.5))
            for i in range(len(path_points) - 1):
                painter.drawLine(path_points[i], path_points[i + 1])


# python
# python

# python
class SettingsDialog(QDialog):
    def __init__(self, parent, configs):
        super().__init__(parent)
        self.model_combo = None
        self.checks = None
        self.cb_monitor_model = None
        self.setWindowTitle("监控设置")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.configs = configs
        self.parent_widget = parent
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
            # use toggled(bool) (emits a Python bool) and keep a reference to the checkbox
            cb_show.toggled.connect(lambda checked, k=key: self.update_cfg(k, 'show', checked))

            cb_chart = QCheckBox("显示图表")
            cb_chart.setChecked(cfg['show_chart'])
            cb_chart.toggled.connect(lambda checked, k=key: self.update_cfg(k, 'show_chart', checked))

            h_lay.addWidget(cb_show)
            h_lay.addWidget(cb_chart)
            layout.addWidget(group)

            # keep references so Python wrappers aren't GC'd while dialog is open
            self.checks[key] = {'show': cb_show, 'chart': cb_chart}

        model_group = QFrame()
        model_lay = QHBoxLayout(model_group)
        model_lay.setContentsMargins(0, 5, 0, 5)

        self.cb_monitor_model = QCheckBox("监控 Ollama 模型")
        self.cb_monitor_model.setChecked(getattr(self.parent_widget, "model_monitor_enabled", False))
        self.cb_monitor_model.stateChanged.connect(self.toggle_model_monitor)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        self.refresh_models()
        current = getattr(self.parent_widget, "model_monitor_name", "") or ""
        if current and current in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
            self.model_combo.setCurrentText(current)
        self.model_combo.currentTextChanged.connect(self.update_selected_model)

        btn_run = QPushButton("启动模型")
        btn_run.clicked.connect(self.run_model)

        btn_refresh = QPushButton("刷新列表")
        btn_refresh.clicked.connect(self.refresh_models)

        model_lay.addWidget(self.cb_monitor_model)
        model_lay.addWidget(self.model_combo)
        model_lay.addWidget(btn_run)
        model_lay.addWidget(btn_refresh)
        layout.addWidget(model_group)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_close = QPushButton("确定")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        btn_quit = QPushButton("退出应用")
        btn_quit.clicked.connect(self.quit_app)
        btn_row.addWidget(btn_quit)

        layout.addLayout(btn_row)

    def update_cfg(self, key, field, state):
        # coerce incoming state (could be bool from toggled or int from stateChanged)
        try:
            if isinstance(state, bool):
                val = state
            else:
                val = (state == Qt.Checked)
            self.configs[key][field] = bool(val)
        except Exception:
            pass
        try:
            self.parent_widget.apply_settings()
        except Exception:
            pass

    def toggle_model_monitor(self, state):
        # accept either bool (from toggled) or int (from stateChanged)
        try:
            enabled = state if isinstance(state, bool) else (state == Qt.Checked)
            self.parent_widget.model_monitor_enabled = bool(enabled)
            self.parent_widget.apply_settings()
        except Exception:
            pass

    def update_selected_model(self, text):
        try:
            self.parent_widget.model_monitor_name = text
            self.parent_widget.apply_settings()
        except Exception:
            pass

    def refresh_models(self):
        self.model_combo.clear()
        if not shutil.which("ollama"):
            print("未找到 ollama 命令，无法列出模型。")
            return
        try:
            out = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                name = parts[0]
                if name.lower() in ("name", "---"):
                    continue
                if name not in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
                    self.model_combo.addItem(name)
        except Exception as e:
            print("获取 ollama 模型列表失败:", e)

    # python
    def run_model(self):
        import threading, time, os
        model = self.model_combo.currentText()
        if not model:
            print("未选择模型")
            return

        ollama_path = shutil.which("ollama")
        if not ollama_path:
            print("未找到 `ollama` 命令，请确认 PATH（在 cmd 中运行 `where ollama`）")
            return

        try:
            # 启动子进程，保留 stdout/stderr 并以文本模式读取
            creationflags = 0
            if sys.platform == "win32":
                # 尽量使用无窗口/新进程组标志
                CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                DETACHED_PROCESS = 0x00000008
                creationflags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS

            proc = subprocess.Popen(
                [ollama_path, "run", model],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                creationflags=creationflags
            )

            # 后台线程逐行读取并打印到控制台
            def _stream_output(pipe, pid):
                try:
                    print(f"ollama run 已启动，pid={pid}，开始转发输出：")
                    for line in iter(pipe.readline, ""):
                        if not line:
                            break
                        # 直接打印到运行控制台
                        print(line.rstrip())
                except Exception as e:
                    print("读取子进程输出失败:", e)
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass
                    print(f"ollama run pid={pid} 输出流已结束。")

            t = threading.Thread(target=_stream_output, args=(proc.stdout, proc.pid), daemon=True)
            t.start()

            # 保存引用以防被 gc，方便后续检查或关闭
            try:
                self._ollama_proc = proc
                self._output_thread = t
            except Exception:
                pass

            print(f"已发出启动请求，pid={getattr(proc, 'pid', 'n/a')}")

            # 立即把选择设为监控并生效（如有需要）
            try:
                self.parent_widget.model_monitor_name = model
                self.parent_widget.model_monitor_enabled = True
                self.parent_widget.apply_settings()
                self.cb_monitor_model.setChecked(True)
            except Exception:
                pass

        except Exception as e:
            print("启动模型失败:", e)

    def accept(self):
        try:
            self.parent_widget.model_monitor_enabled = self.cb_monitor_model.isChecked()
            self.parent_widget.model_monitor_name = self.model_combo.currentText() or ""
            self.parent_widget.apply_settings()
        except Exception:
            pass
        super().accept()

    def quit_app(self):
        try:
            parent = self.parent()
            if parent is not None:
                parent.close()
            QApplication.instance().quit()
        except Exception as e:
            print("退出应用失败:", e)


# python
class MonitorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.checks = None
        self.model_label = None
        self.widgets = None
        self.layout = None
        self.set_btn = None
        self.main_container = None
        self.settings_dialog = None

        # Ollama 模型监控配置：默认开启
        self.model_monitor_enabled = True
        self.model_monitor_name = ""

        # 记录上次尝试启动模型的时间（节流，秒）
        self._model_last_start_attempt = 0
        self._model_start_cooldown = 10  # 秒

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

        # 尝试在启动时选择一个默认模型（如果系统上有 ollama 且有模型）
        try:
            models = self._get_available_models()
            if models:
                self.model_monitor_name = models[0]
        except Exception as e:
            print("获取默认模型失败:", e)
            pass

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)
        self._drag_pos = None

    def init_ui(self):
        from PySide6.QtGui import QFontDatabase, QFont

        def make_smooth_font(preferred_families, point_size=10, weight=QFont.Medium):
            # 使用类方法获取系统字体族，避免实例化 QFontDatabase()
            try:
                families = QFontDatabase.families()
            except Exception:
                families = []  # 兼容性回退

            family = None
            for f in preferred_families:
                if f in families:
                    family = f
                    break
            if family is None:
                family = QFont().defaultFamily()
            font = QFont(family, point_size, weight)
            # 尝试启用抗锯齿的渲染策略（若可用）
            try:
                font.setStyleStrategy(QFont.PreferAntialias)
            except Exception:
                try:
                    font.setStyleStrategy(QFont.PreferAntialiasing)
                except Exception:
                    pass
            # 轻微增加字间距让显示更圆润（按需调整）
            try:
                font.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
            except Exception:
                pass
            return font

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

        # 顶部栏：将模型标签放在左侧、设置按钮放在右侧（同一高度）
        top_bar = QHBoxLayout()
        # 模型状态标签（放左上）
        self.model_label = QLabel("")
        self.model_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.model_label.setFixedHeight(24)
        self.model_label.setStyleSheet("color: #FFD580; font-size: 11px;")

        # 应用平滑字体：优先尝试常见的圆润/可变字体
        preferred = ["Segoe UI Variable", "Inter", "Segoe UI", "Microsoft YaHei", "Arial"]
        smooth_font = make_smooth_font(preferred, point_size=11, weight=QFont.DemiBold)
        self.model_label.setFont(smooth_font)

        top_bar.addWidget(self.model_label)

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

    def update_cfg(self, key, field, state):
         """从复选框回调更新 configs 并刷新显示"""
         try:
            # accept bool (toggled) or int (stateChanged)
            if isinstance(state, bool):
                val = state
            else:
                val = (state == Qt.Checked)
            self.configs[key][field] = bool(val)
            self.apply_settings()
         except Exception:
             pass

    def _get_available_models(self):
        """返回 ollama list 的模型名列表，失败时返回空列表"""
        if not shutil.which("ollama"):
            return []
        try:
            out = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.DEVNULL)
            models = []
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                name = parts[0]
                if name.lower() in ("name", "---"):
                    continue
                models.append(name)
            return models
        except Exception:
            return []

    def apply_settings(self):
        visible_count = 0
        for key, cfg in self.configs.items():
            w = self.widgets[key]
            w['row'].setVisible(cfg['show'])
            w['chart'].setVisible(cfg['show_chart'])
            if cfg['show']:
                visible_count += 1

        new_height = 40 + (
            visible_count * 55 if any(c['show_chart'] for c in self.configs.values()) else visible_count * 30)
        self.setFixedHeight(max(new_height, 60))
        self.main_container.setFixedHeight(self.height())

        # 模型监控显示：仅当启用且有选择模型时显示，并立即尝试更新状态文本
        if getattr(self, "model_monitor_enabled", False) and getattr(self, "model_monitor_name", ""):
            try:
                running = self._is_model_running(self.model_monitor_name)
                if running:
                    self.model_label.setText(f"{self.model_monitor_name}：正在运行")
                    self.model_label.setStyleSheet("color: #7CFF9E; font-size: 11px;")
                else:
                    self.model_label.setText(f"{self.model_monitor_name}：未运行（将尝试自动启动）")
                    self.model_label.setStyleSheet("color: #FFB3B3; font-size: 11px;")
                self.model_label.setVisible(True)
            except Exception:
                self.model_label.setVisible(False)
        else:
            self.model_label.setVisible(False)

    def show_settings(self):
        try:
            self.settings_dialog = SettingsDialog(self, self.configs)
            self.settings_dialog.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            main_geo = self.geometry()
            self.settings_dialog.move(main_geo.left() - 250, main_geo.top())
            self.settings_dialog.exec()
            self.apply_settings()
        except Exception as e:
            print(f"弹出失败: {e}")

    def _is_model_running(self, model_name: str) -> bool:
        if not model_name:
            return False
        if not shutil.which("ollama"):
            return False
        try:
            out = subprocess.check_output(["ollama", "ps"], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if model_name in line.split():
                    return True
            return False
        except Exception:
            return False

    def update_stats(self):
        import time
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
                self.widgets['cuda']['lbl'].setText(f"CUDA Load: {u.gpu}%")
                self.widgets['cuda']['chart'].add_value(u.gpu)
            except Exception as e:
                print("NVML 读取失败:", e)
                pass

        # 3. Ollama 模型监控（每秒检查一次），若未运行则按节流尝试自动启动
        try:
            if getattr(self, "model_monitor_enabled", False) and getattr(self, "model_monitor_name", ""):
                model = self.model_monitor_name
                running = self._is_model_running(model)
                now = time.time()
                if running:
                    self.model_label.setText(f"{model}：正在运行")
                    self.model_label.setStyleSheet("color: #7CFF9E; font-size: 11px;")
                else:
                    # 未运行，先更新状态文本
                    self.model_label.setText(f"{model}：未运行（自动启动中）")
                    self.model_label.setStyleSheet("color: #FFB3B3; font-size: 11px;")
                    # 仅在超过冷却时间后尝试自动启动一次
                    if (now - self._model_last_start_attempt) >= self._model_start_cooldown:
                        self._model_last_start_attempt = now
                        try:
                            if not shutil.which("ollama"):
                                self.model_label.setText(f"{model}：未找到 ollama")
                                self.model_label.setStyleSheet("color: #FFB3B3; font-size: 11px;")
                            else:
                                if sys.platform == "win32":
                                    detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | detached | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                                    process = subprocess.Popen(
                                        ["ollama", "run", model],
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        creationflags=creationflags
                                    )
                                else:
                                    process = subprocess.Popen(
                                        ["ollama", "run", model],
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        start_new_session=True
                                    )
                                print(f"✅ 已发起自动启动指令: {model}")
                        except Exception as e:
                            print(f"❌ 自动启动失败: {e}")
                self.model_label.setVisible(True)
            else:
                self.model_label.setVisible(False)
        except Exception as e:
            self.model_label.setVisible(False)
            print("模型监控检查出错:", e)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MonitorWidget()
    w.show()
    sys.exit(app.exec())
