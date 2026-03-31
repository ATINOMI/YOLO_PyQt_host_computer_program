# yolo_gui_modern.py
# 改进版：增加了详细注释、参数化配置面板、AI 模型选择、检测频率控制、
# STM32 串口数据接口（可选）、以及更清晰的代码结构，方便初学者修改。
# 布局优化版：右侧控制区更紧凑，日志窗口更大。

import sys
import time
import json
import threading
import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow,
    QLabel, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QGroupBox, QSplitter,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit, QFileDialog
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# ultralytics YOLO（注意：需要提前 pip install ultralytics）
from ultralytics import YOLO

# 串口通信（可选）：pyserial。没有时程序会以没有串口功能运行
try:
    import serial

    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False

# ====================== 可配置参数区（初学者建议只在这里修改） ======================
# 把常用的参数集中放在这里，程序其它地方通过 "config[...]" 访问，方便修改。
config = {
    # 摄像头和帧率
    "CAMERA_INDEX": 0,  # 摄像头索引（0 通常是内置/默认摄像头）
    "CAMERA_CAPTURE_FPS": 30,  # 摄像头理论采集帧率（仅为参考，真实由摄像头与驱动决定）

    # YOLO 与推理设置
    "MODEL_PATH": "yolo11n.pt",  # 默认模型文件路径（可替换为你训练的模型）
    "MODEL_LIST": ["yolo11n.pt", "yolov8n.pt", "yolov8s.pt"],
    "CONF_THRESHOLD": 0.45,  # 置信度阈值，低于此值的检测结果会被丢弃

    # 控制推理频率：检测频率（Hz），独立于摄像头采集频率
    "DETECTION_FPS": 10.0,  # YOLO 每秒执行多少次推理（例如 10 表示每 0.1s 推理一次）

    # 是否在检测时绘制边框（耗 GPU/CPU）
    "DRAW_BOX": True,

    # 串口（STM32）通信默认设置（若需开启，请在 UI 中启用）
    "SERIAL_ENABLED": False,
    "SERIAL_PORT": "COM3",  # Windows 示例: COM3；Linux 示例: /dev/ttyUSB0
    "SERIAL_BAUDRATE": 115200,
    # 串口消息格式："text" 或 "binary"（示例中默认 text）
    "SERIAL_FORMAT": "text",

    # 日志保留条数（UI 内存控制）
    "LOG_MAX_LINES": 1000,
}
# ================================================================================


# ========================= QSS（界面样式） ======================================
STYLESHEET = """
QMainWindow { background-color: #1e1e1e; }
QLabel { color: #e0e0e0; font-family: "Microsoft YaHei"; font-size: 13px; }
QLabel#TitleLabel { font-size: 20px; font-weight: bold; color: #00aaff; padding: 5px; }
QFrame#VideoFrame { background-color: #2d2d2d; border: 1px solid #3e3e3e; border-radius: 10px; }
QLabel#VideoLabel { background-color: #000; border: 1px solid #444; border-radius: 5px; color: #666; }
QFrame#ControlPanel { background-color: #252526; border-left: 1px solid #3e3e3e; min-width: 340px; } /* 稍微加宽一点右侧以容纳双列参数 */
QGroupBox { color: #00aaff; font-weight: bold; border: 1px solid #3e3e3e; border-radius: 6px; margin-top: 8px; padding-top: 12px; font-size: 12px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 3px; }
QPushButton { background-color: #3e3e42; color: white; border: none; border-radius: 4px; padding: 6px; font-weight: bold; font-size: 12px; }
QPushButton:hover { background-color: #505055; }
QPushButton#BtnStart { background-color: #0e639c; }
QPushButton#BtnStop { background-color: #c53030; }
QTextEdit { background-color: #151515; border: 1px solid #3e3e3e; border-radius: 4px; color: #00ff00; font-family: "Consolas"; font-size: 11px; padding: 4px; }
/* 紧凑型输入框样式 */
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
    background-color: #333; color: #eee; border: 1px solid #555; border-radius: 3px; padding: 2px;
}
"""


# ========================= 串口发送线程（将检测数据异步发送到 STM32） =========================
class SerialSenderThread(QThread):
    """
    专门负责打开串口并发送检测数据，避免 GUI 阻塞。
    如果系统没有安装 pyserial，则该线程不会被创建。
    """
    send_log_signal = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int, fmt: str = "text"):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.fmt = fmt
        self._running = True
        self._queue = []
        self.lock = threading.Lock()
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
            self.send_log_signal.emit(f"Serial opened: {self.port}@{self.baudrate}")
        except Exception as e:
            self.send_log_signal.emit(f"Serial open failed: {e}")
            return

        while self._running:
            # 处理队列里的数据
            msg = None
            with self.lock:
                if self._queue:
                    msg = self._queue.pop(0)
            if msg is not None:
                try:
                    if self.fmt == "text":
                        if isinstance(msg, bytes):
                            self.ser.write(msg)
                        else:
                            self.ser.write(str(msg).encode("utf-8"))
                    else:
                        # binary
                        self.ser.write(msg)
                except Exception as e:
                    self.send_log_signal.emit(f"Serial send error: {e}")
            else:
                self.msleep(10)  # 等待 10ms

        # 退出前关闭串口
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.send_log_signal.emit("Serial closed")
        except Exception:
            pass

    def enqueue(self, data):
        with self.lock:
            self._queue.append(data)

    def stop(self):
        self._running = False
        self.wait()


# ========================= 摄像头 + YOLO 推理子线程 =================================
class VideoThread(QThread):
    # 信号定义：
    raw_frame_signal = pyqtSignal(np.ndarray)  # 原始摄像头帧（用于展示）
    processed_frame_signal = pyqtSignal(np.ndarray)  # 推理后画面（带框）
    detect_info_signal = pyqtSignal(list)  # 推理结果（list of dict）
    fps_signal = pyqtSignal(float)  # 实时摄像头帧率（显示）

    # 允许外部线程请求加载模型
    model_loaded_signal = pyqtSignal(str)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.running = True
        self.model = None
        self.last_infer_time = 0.0
        self.last_processed = None
        self._reload_model_path = None

    def run(self):
        # 模型延迟加载，避免 UI 卡顿：首次需要推理时再加载
        cap = cv2.VideoCapture(self.cfg["CAMERA_INDEX"])
        if not cap.isOpened():
            self.detect_info_signal.emit([{"error": "无法打开摄像头"}])
            return

        last_time = time.time()

        while self.running:
            ret, frame = cap.read()
            if not ret:
                break

            # 计算并发送摄像头帧率（供 UI 显示）
            current_time = time.time()
            cam_fps = 1.0 / (current_time - last_time) if (current_time - last_time) > 0 else 0.0
            last_time = current_time
            self.fps_signal.emit(cam_fps)

            # 先发送原始帧（用于实时预览）
            self.raw_frame_signal.emit(frame)

            # 支持外部请求重新加载模型（安全地在循环内处理）
            if self._reload_model_path is not None:
                try:
                    new_path = self._reload_model_path
                    self.model = YOLO(new_path)
                    self.model_loaded_signal.emit(f"Model loaded: {new_path}")
                except Exception as e:
                    self.model_loaded_signal.emit(f"Model load failed: {e}")
                self._reload_model_path = None

            # 如果模型还未加载，则延迟加载
            if self.model is None:
                try:
                    self.model = YOLO(self.cfg["MODEL_PATH"])
                    self.model_loaded_signal.emit(f"Model loaded: {self.cfg['MODEL_PATH']}")
                except Exception as e:
                    self.detect_info_signal.emit([{"error": f"模型加载失败: {e}"}])
                    # 等待一会儿再重试
                    time.sleep(1.0)
                    continue

            # 根据设置的检测频率决定是否执行推理
            now = time.time()
            if now - self.last_infer_time < (1.0 / max(0.0001, self.cfg["DETECTION_FPS"])):
                # 如果不做新推理，也仍可把上次处理后的画面发回以保证展示流畅
                if self.last_processed is not None:
                    self.processed_frame_signal.emit(self.last_processed)
                # 稍作让步（防止 CPU 飙升）
                time.sleep(0.001)
                continue

            self.last_infer_time = now

            # 执行 YOLO 推理（注意：这里传入的是 BGR 的 numpy 图片，ultralytics 支持）
            try:
                results = self.model(frame, verbose=False)[0]
            except Exception as e:
                self.detect_info_signal.emit([{"error": f"推理失败: {e}"}])
                time.sleep(0.1)
                continue

            processed = frame.copy()
            detect_infos = []

            for box in results.boxes:
                conf = float(box.conf[0])
                if conf < self.cfg["CONF_THRESHOLD"]:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls = int(box.cls[0])
                name = self.model.names.get(cls, str(cls))

                detect_infos.append({
                    "class_name": name,
                    "confidence": conf,
                    "box": (x1, y1, x2, y2)
                })

                if self.cfg["DRAW_BOX"]:
                    color = (0, 255, 0)
                    cv2.rectangle(processed, (x1, y1), (x2, y2), color, 2)
                    label = f"{name} {conf:.2f}"
                    (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                    cv2.rectangle(processed, (x1, y1 - 20), (x1 + w, y1), color, -1)
                    cv2.putText(processed, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

            # 保存并发送
            self.last_processed = processed
            self.processed_frame_signal.emit(processed)
            self.detect_info_signal.emit(detect_infos)

        cap.release()

    # 外部请求：在子线程里安全地重新加载模型
    def request_reload_model(self, model_path: str):
        self._reload_model_path = model_path

    def stop(self):
        self.running = False
        self.quit()
        self.wait()


# ========================= 主窗口（包含参数面板与串口设置） =========================
class ModernWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YOLO 智能视觉检测终端 - 紧凑布局版")
        self.resize(1450, 850)
        self.setStyleSheet(STYLESHEET)

        # 保存线程引用
        self.video_thread: VideoThread | None = None
        self.serial_thread: SerialSenderThread | None = None

        # UI 初始化
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ------------------ 左侧：视频展示区 ------------------
        video_container = QFrame()
        video_container.setObjectName("VideoFrame")
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(10, 10, 10, 10)  # 减小边距

        title_label = QLabel("👁️ YOLO 实时检测系统 (v2.1 Compact)")
        title_label.setObjectName("TitleLabel")
        video_layout.addWidget(title_label)

        # 原始与处理后视频并排
        video_grid = QGridLayout()
        video_grid.setSpacing(10)

        self.label_raw = QLabel("原始视频信号未接入")
        self.label_raw.setObjectName("VideoLabel")
        self.label_raw.setAlignment(Qt.AlignCenter)
        self.label_raw.setMinimumSize(480, 360)

        self.label_processed = QLabel("AI 处理画面待机中...")
        self.label_processed.setObjectName("VideoLabel")
        self.label_processed.setAlignment(Qt.AlignCenter)
        self.label_processed.setMinimumSize(480, 360)

        video_grid.addWidget(QLabel("RAW CAMERA"), 0, 0)
        video_grid.addWidget(QLabel("AI INFERENCE"), 0, 1)
        video_grid.addWidget(self.label_raw, 1, 0)
        video_grid.addWidget(self.label_processed, 1, 1)

        video_grid.setColumnStretch(0, 1)
        video_grid.setColumnStretch(1, 1)
        video_layout.addLayout(video_grid)

        main_layout.addWidget(video_container, stretch=70)  # 左侧占 70%

        # ------------------ 右侧：控制面板（优化布局） ------------------
        control_panel = QFrame()
        control_panel.setObjectName("ControlPanel")
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(10, 15, 10, 15)
        control_layout.setSpacing(8)  # 减小组件间距

        # 1. 顶部状态与控制合一 (最紧凑设计)
        top_group = QGroupBox("系统控制与状态")
        top_layout = QVBoxLayout()
        top_layout.setSpacing(5)

        # 第一行：状态显示
        status_layout = QHBoxLayout()
        self.lbl_fps = QLabel("FPS: --")
        self.lbl_fps.setStyleSheet("color: #00ff00; font-weight: bold;")
        self.lbl_count = QLabel("Count: 0")
        self.lbl_count.setStyleSheet("color: #ffcc00; font-weight: bold;")
        status_layout.addWidget(self.lbl_fps)
        status_layout.addWidget(self.lbl_count)
        status_layout.addStretch()
        top_layout.addLayout(status_layout)

        # 第二行：按钮 (Start/Stop/Reload)
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 启动检测")
        self.btn_start.setObjectName("BtnStart")
        self.btn_start.clicked.connect(self.start_detection)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setObjectName("BtnStop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_detection)

        self.btn_reload_model = QPushButton("⤻ 重载模型")
        self.btn_reload_model.clicked.connect(self.reload_model_from_ui)

        btn_layout.addWidget(self.btn_start, stretch=2)
        btn_layout.addWidget(self.btn_stop, stretch=1)
        btn_layout.addWidget(self.btn_reload_model, stretch=1)
        top_layout.addLayout(btn_layout)

        top_group.setLayout(top_layout)
        control_layout.addWidget(top_group)

        # 2. 参数设置区 (使用网格布局双列显示，极大节省空间)
        group_params = QGroupBox("参数配置")
        params_layout = QGridLayout()
        params_layout.setSpacing(6)

        # Col 0: Labels, Col 1: Widgets, Col 2: Labels, Col 3: Widgets

        # Row 0: Cam Index | Cam FPS
        params_layout.addWidget(QLabel("摄像机ID:"), 0, 0)
        self.spin_cam_index = QSpinBox();
        self.spin_cam_index.setRange(0, 10);
        self.spin_cam_index.setValue(config["CAMERA_INDEX"])
        params_layout.addWidget(self.spin_cam_index, 0, 1)

        params_layout.addWidget(QLabel("采集FPS:"), 0, 2)
        self.spin_cam_fps = QSpinBox();
        self.spin_cam_fps.setRange(1, 120);
        self.spin_cam_fps.setValue(config["CAMERA_CAPTURE_FPS"])
        params_layout.addWidget(self.spin_cam_fps, 0, 3)

        # Row 1: Detect FPS | Conf Thresh
        params_layout.addWidget(QLabel("检测FPS:"), 1, 0)
        self.spin_detect_fps = QDoubleSpinBox();
        self.spin_detect_fps.setRange(0.1, 60.0);
        self.spin_detect_fps.setValue(config["DETECTION_FPS"])
        params_layout.addWidget(self.spin_detect_fps, 1, 1)

        params_layout.addWidget(QLabel("置信度:"), 1, 2)
        self.spin_conf = QDoubleSpinBox();
        self.spin_conf.setRange(0.0, 1.0);
        self.spin_conf.setSingleStep(0.05);
        self.spin_conf.setValue(config["CONF_THRESHOLD"])
        params_layout.addWidget(self.spin_conf, 1, 3)

        # Row 2: Draw Box | Model List
        params_layout.addWidget(QLabel("画框:"), 2, 0)
        self.chk_draw = QCheckBox();
        self.chk_draw.setChecked(config["DRAW_BOX"])
        params_layout.addWidget(self.chk_draw, 2, 1)

        params_layout.addWidget(QLabel("选择模型:"), 2, 2)
        self.cmb_model = QComboBox();
        self.cmb_model.addItems(config["MODEL_LIST"])
        params_layout.addWidget(self.cmb_model, 2, 3)

        # Row 3: Model Path (Full Width)
        path_layout = QHBoxLayout()
        self.edit_model_path = QLineEdit(config["MODEL_PATH"])
        self.edit_model_path.setPlaceholderText("自定义模型路径...")
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(30)
        btn_browse.clicked.connect(self.browse_model_file)
        path_layout.addWidget(self.edit_model_path)
        path_layout.addWidget(btn_browse)

        # Span across all columns
        params_layout.addLayout(path_layout, 3, 0, 1, 4)

        group_params.setLayout(params_layout)
        control_layout.addWidget(group_params)

        # 3. 串口设置 (一行内显示关键参数)
        group_serial = QGroupBox("STM32 串口通信")
        serial_layout = QGridLayout()
        serial_layout.setSpacing(6)

        self.chk_serial_enable = QCheckBox("启用")
        self.chk_serial_enable.setChecked(config["SERIAL_ENABLED"])
        serial_layout.addWidget(self.chk_serial_enable, 0, 0)

        self.edit_serial_port = QLineEdit(config["SERIAL_PORT"])
        self.edit_serial_port.setPlaceholderText("端口(如COM3)")
        serial_layout.addWidget(self.edit_serial_port, 0, 1)

        self.spin_baud = QSpinBox();
        self.spin_baud.setRange(1200, 1000000);
        self.spin_baud.setValue(config["SERIAL_BAUDRATE"])
        serial_layout.addWidget(self.spin_baud, 0, 2)

        self.cmb_serial_fmt = QComboBox();
        self.cmb_serial_fmt.addItems(["text", "binary"])
        serial_layout.addWidget(self.cmb_serial_fmt, 0, 3)

        self.btn_serial_test = QPushButton("测试串口连接")
        self.btn_serial_test.clicked.connect(self.test_serial_open)
        serial_layout.addWidget(self.btn_serial_test, 1, 0, 1, 4)

        group_serial.setLayout(serial_layout)
        control_layout.addWidget(group_serial)

        # 4. 日志区域 (使用 stretch=10 强行占用剩余所有空间)
        group_log = QGroupBox("系统日志 (Log)")
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(5, 12, 5, 5)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setPlaceholderText("系统就绪...")
        log_layout.addWidget(self.info_text)

        group_log.setLayout(log_layout)
        control_layout.addWidget(group_log, stretch=10)  # 关键：让日志区占据剩余空间

        main_layout.addWidget(control_panel, stretch=30)  # 右侧占 30%

    # 浏览自定义模型路径
    def browse_model_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select model file", "", "PyTorch model (*.pt);;All files (*)")
        if path:
            self.edit_model_path.setText(path)

    # 启动检测线程
    def start_detection(self):
        # 将 UI 值写回配置 dict
        config["CAMERA_INDEX"] = int(self.spin_cam_index.value())
        config["CAMERA_CAPTURE_FPS"] = int(self.spin_cam_fps.value())
        config["DETECTION_FPS"] = float(self.spin_detect_fps.value())
        config["CONF_THRESHOLD"] = float(self.spin_conf.value())
        config["DRAW_BOX"] = bool(self.chk_draw.isChecked())

        # 模型路径可以选择下拉或者自定义输入框
        chosen = self.cmb_model.currentText()
        custom = self.edit_model_path.text().strip()
        model_path = custom if custom else chosen
        config["MODEL_PATH"] = model_path

        # 串口配置
        config["SERIAL_ENABLED"] = bool(self.chk_serial_enable.isChecked())
        config["SERIAL_PORT"] = self.edit_serial_port.text().strip()
        config["SERIAL_BAUDRATE"] = int(self.spin_baud.value())
        config["SERIAL_FORMAT"] = self.cmb_serial_fmt.currentText()

        # 启动串口线程（如果需要）
        if config["SERIAL_ENABLED"]:
            if not SERIAL_AVAILABLE:
                self.append_log("pyserial 未安装，串口功能不可用。请使用: pip install pyserial")
            else:
                if self.serial_thread is None:
                    self.serial_thread = SerialSenderThread(config["SERIAL_PORT"], config["SERIAL_BAUDRATE"],
                                                            config["SERIAL_FORMAT"])
                    self.serial_thread.send_log_signal.connect(self.append_log)
                    self.serial_thread.start()

        # 启动视频线程
        if self.video_thread is None:
            self.video_thread = VideoThread(config)
            self.video_thread.raw_frame_signal.connect(self.update_raw_image)
            self.video_thread.processed_frame_signal.connect(self.update_processed_image)
            self.video_thread.detect_info_signal.connect(self.update_log)
            self.video_thread.fps_signal.connect(self.update_fps)
            self.video_thread.model_loaded_signal.connect(self.append_log)
            self.video_thread.start()

        # UI 状态切换
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.append_log(
            f">>> 系统已启动。Model={config['MODEL_PATH']}, DetFPS={config['DETECTION_FPS']}, Conf={config['CONF_THRESHOLD']:.2f}"
        )

    # 停止检测并清理线程
    def stop_detection(self):
        if self.video_thread:
            self.video_thread.stop()
            self.video_thread = None
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None

        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.label_raw.clear();
        self.label_raw.setText("已停止")
        self.label_processed.clear();
        self.label_processed.setText("已停止")
        self.lbl_fps.setText("FPS: --")
        self.lbl_count.setText("Count: 0")
        self.append_log(">>> 系统已停止")

    # 重新加载模型（不重启线程）
    def reload_model_from_ui(self):
        path = self.edit_model_path.text().strip() or self.cmb_model.currentText()
        if not path:
            self.append_log("请先选择或输入模型路径")
            return
        if self.video_thread:
            self.video_thread.request_reload_model(path)
            self.append_log(f"请求子线程重新加载模型: {path}")
        else:
            # 更新配置，下一次启动时会加载
            config["MODEL_PATH"] = path
            self.append_log(f"模型路径已设置，将在下次启动时加载: {path}")

    # 串口打开测试（仅测试能否打开）
    def test_serial_open(self):
        if not SERIAL_AVAILABLE:
            self.append_log("pyserial 未安装：pip install pyserial")
            return
        port = self.edit_serial_port.text().strip()
        baud = int(self.spin_baud.value())
        try:
            s = serial.Serial(port, baud, timeout=0.5)
            s.close()
            self.append_log(f"串口测试成功: {port}@{baud}")
        except Exception as e:
            self.append_log(f"串口测试失败: {e}")

    # UI: 显示原始帧
    def update_raw_image(self, frame):
        self._display_image(self.label_raw, frame)

    # UI: 显示处理后帧
    def update_processed_image(self, frame):
        self._display_image(self.label_processed, frame)

    # 通用图片显示函数
    def _display_image(self, label_widget, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        scaled_pixmap = pixmap.scaled(label_widget.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label_widget.setPixmap(scaled_pixmap)

    # 更新 UI 上的实时 FPS
    def update_fps(self, fps):
        self.lbl_fps.setText(f"FPS: {fps:.1f}")

    # 格式化并发送检测日志（同时把要发给 STM32 的数据放入串口线程队列）
    def update_log(self, infos):
        # 如果子线程发来错误信息
        if isinstance(infos, list) and len(infos) > 0 and "error" in infos[0]:
            self.append_log(f"ERROR: {infos[0]['error']}")
            return

        # 更新计数显示
        count = len(infos) if isinstance(infos, list) else 0
        self.lbl_count.setText(f"Count: {count}")

        # 当前时间戳（可改为毫秒）
        current_time = time.strftime("%H:%M:%S")

        # 格式化每个检测对象的日志行
        for obj in infos:
            line = f"[{current_time}] {obj['class_name']:<12} Conf:{obj['confidence']:.2f} Box:{obj['box']}"
            self.append_log(line)

        # 发送给串口（如果启用）
        if config.get("SERIAL_ENABLED") and self.serial_thread:
            packet = self.format_for_stm32(infos)
            self.serial_thread.enqueue(packet)

    # 简单的打包函数：把检测数据打成一行文本（CSV-like），示例：
    # D,TIMESTAMP,COUNT,cls1,conf1,x1,y1,x2,y2;cls2,conf2,...\n
    def format_for_stm32(self, infos: list) -> bytes:
        """
        目的：给 STM32 一个简单稳定的文本数据格式，便于在 STM32 端用串口解析。
        - 优点：简单、可读、容易用 scanf / strtok 在 STM32 端解析
        - 如果你需要二进制协议，可以在这里改成定长二进制包
        """
        try:
            ts = int(time.time() * 1000)  # ms
            parts = ["D", str(ts), str(len(infos))]
            for obj in infos:
                cls = obj['class_name']
                conf = f"{obj['confidence']:.2f}"
                x1, y1, x2, y2 = obj['box']
                parts.append(f"{cls},{conf},{x1},{y1},{x2},{y2}")
            line = ",".join(parts) + "\n"
            return line.encode("utf-8")
        except Exception as e:
            self.append_log(f"Packet format error: {e}")
            return b""

    # 日志追加（并控制最大行数以避免内存过大）
    def append_log(self, text: str):
        self.info_text.append(text)
        # 保持日志行数
        doc = self.info_text.document()
        if doc.blockCount() > config.get("LOG_MAX_LINES", 1000):
            # 简单地裁剪：移除最老的 200 行
            cursor = self.info_text.textCursor()
            cursor.movePosition(cursor.Start)
            for _ in range(200):
                cursor.select(cursor.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()  # remove newline


# ========================= 运行入口 =================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ModernWindow()
    win.show()
    # 依赖提示（初学者友好）
    win.append_log("依赖提示: ultralytics, opencv-python, PyQt5. 若需串口功能请安装 pyserial。")
    win.append_log("示例安装: pip install ultralytics opencv-python PyQt5 pyserial")
    sys.exit(app.exec_())