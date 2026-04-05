"""
主窗口 UI
"""
import time
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QTextEdit,
    QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QSpinBox, QFileDialog
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt

from controller.pipeline import DataPipeline
from hardware.serial_port import SerialPort


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.pipeline = None
        self._model_path = 'yolo11n.pt'

        # UI 组件
        self.video_label = QLabel()
        self.btn_start = QPushButton("启动检测")
        self.btn_stop = QPushButton("停止")
        self.btn_load_model = QPushButton("加载模型")

        # 串口号：下拉列表 + 刷新按钮
        self.input_serial_port = QComboBox()
        self.btn_refresh_ports = QPushButton("刷新")
        self.btn_refresh_ports.setFixedWidth(48)

        # 波特率：默认改为 9600
        self.input_baudrate = QComboBox()
        self.input_baudrate.addItems(['9600', '19200', '38400', '57600', '115200', '256000'])
        self.input_baudrate.setCurrentText('9600')

        self.input_detect_fps = QSpinBox()
        self.input_detect_fps.setRange(1, 60)
        self.input_detect_fps.setValue(10)

        self.input_bytesize = QComboBox()
        self.input_bytesize.addItems(['8', '7', '6', '5'])
        self.input_bytesize.setCurrentText('8')

        self.input_parity = QComboBox()
        self.input_parity.addItems(['None', 'Even', 'Odd'])
        self.input_parity.setCurrentText('None')

        self.input_stopbits = QComboBox()
        self.input_stopbits.addItems(['1', '1.5', '2'])
        self.input_stopbits.setCurrentText('1')

        self.input_quantizer_mode = QComboBox()
        self.input_quantizer_mode.addItems(['命令模式 (open/close→0xF0/0x30)', 'bbox模式 (详细坐标)', '贝柱模式'])
        self.input_quantizer_mode.setCurrentIndex(2)

        # 状态显示
        self.label_camera_fps = QLabel("Camera FPS: 0")
        self.label_detect_fps = QLabel("Detect FPS: 0")
        self.text_mcu_response = QTextEdit()
        self.text_mcu_response.setReadOnly(True)
        self.text_mcu_response.setMaximumHeight(150)

        self._refresh_ports()   # 启动时自动扫描一次
        self._init_ui()
        self._connect_signals()

    def _refresh_ports(self):
        """扫描当前可用串口并填充下拉列表"""
        current = self.input_serial_port.currentText()
        ports = SerialPort.list_ports()         # [(device, description), ...]
        self.input_serial_port.clear()
        for device, desc in ports:
            self.input_serial_port.addItem(f"{device} - {desc}", userData=device)
        # 如果之前选的串口还在，保持选中
        if current:
            idx = self.input_serial_port.findText(current, Qt.MatchStartsWith)
            if idx >= 0:
                self.input_serial_port.setCurrentIndex(idx)

    def _current_port(self) -> str:
        """取当前选中的串口设备名（如 'COM3'）"""
        return self.input_serial_port.currentData() or self.input_serial_port.currentText()

    def _init_ui(self):
        """初始化 UI 布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 左侧：视频显示
        video_group = QGroupBox("实时视频")
        video_layout = QVBoxLayout()
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("background-color: #000; border: 1px solid #444;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("等待启动...")
        video_layout.addWidget(self.video_label)
        video_group.setLayout(video_layout)

        # 右侧：控制面板
        control_group = QGroupBox("控制面板")
        control_layout = QVBoxLayout()

        # 按钮行
        btn_layout = QHBoxLayout()
        self.btn_start.setObjectName("BtnStart")
        self.btn_stop.setObjectName("BtnStop")
        self.btn_stop.setEnabled(False)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_load_model)
        control_layout.addLayout(btn_layout)

        # 参数配置
        param_group = QGroupBox("参数配置")
        param_layout = QFormLayout()

        # 串口号行：下拉 + 刷新按钮并排
        port_row = QHBoxLayout()
        port_row.addWidget(self.input_serial_port)
        port_row.addWidget(self.btn_refresh_ports)
        port_row.setContentsMargins(0, 0, 0, 0)
        port_widget = QWidget()
        port_widget.setLayout(port_row)
        param_layout.addRow("串口号:", port_widget)

        param_layout.addRow("波特率:", self.input_baudrate)
        param_layout.addRow("数据位:", self.input_bytesize)
        param_layout.addRow("校验位:", self.input_parity)
        param_layout.addRow("停止位:", self.input_stopbits)
        param_layout.addRow("检测FPS:", self.input_detect_fps)
        param_layout.addRow("量化模式:", self.input_quantizer_mode)
        param_group.setLayout(param_layout)
        control_layout.addWidget(param_group)

        # 状态显示
        status_group = QGroupBox("状态信息")
        status_layout = QVBoxLayout()
        status_layout.addWidget(self.label_camera_fps)
        status_layout.addWidget(self.label_detect_fps)
        status_group.setLayout(status_layout)
        control_layout.addWidget(status_group)

        # MCU 回显区
        mcu_group = QGroupBox("MCU 回显数据")
        mcu_layout = QVBoxLayout()
        mcu_layout.addWidget(self.text_mcu_response)
        mcu_group.setLayout(mcu_layout)
        control_layout.addWidget(mcu_group)

        control_layout.addStretch()
        control_group.setLayout(control_layout)

        main_layout.addWidget(video_group, stretch=70)
        main_layout.addWidget(control_group, stretch=30)

    def _connect_signals(self):
        """连接信号槽"""
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_load_model.clicked.connect(self._on_load_model)
        self.btn_refresh_ports.clicked.connect(self._refresh_ports)

    def _on_start(self):
        """启动按钮点击事件"""
        parity_map = {'None': 'N', 'Even': 'E', 'Odd': 'O'}
        parity = parity_map.get(self.input_parity.currentText(), 'N')
        stopbits = float(self.input_stopbits.currentText())

        index = self.input_quantizer_mode.currentIndex()
        if index == 0:
            quantizer_mode = 'command'
        elif index == 1:
            quantizer_mode = 'bbox'
        else:
            quantizer_mode = 'scallop'

        config = {
            'camera_index': 0,
            'camera_fps': 30,
            'detect_fps': self.input_detect_fps.value(),
            'model_path': self._model_path,
            'serial_port': self._current_port(),
            'baudrate': int(self.input_baudrate.currentText()),
            'bytesize': int(self.input_bytesize.currentText()),
            'parity': parity,
            'stopbits': stopbits,
            'conf_threshold': 0.45,
            'quantizer_mode': quantizer_mode
        }

        try:
            self.pipeline = DataPipeline(config)
            self.pipeline.sig_processed_frame.connect(self._update_video)
            self.pipeline.sig_mcu_response.connect(self._update_mcu_response)
            self.pipeline.sig_camera_fps.connect(
                lambda fps: self.label_camera_fps.setText(f"Camera FPS: {fps:.1f}")
            )
            self.pipeline.sig_detect_fps.connect(
                lambda fps: self.label_detect_fps.setText(f"Detect FPS: {fps:.1f}")
            )
            self.pipeline.sig_error.connect(self._on_error)

            self.pipeline.start()
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.video_label.setText("正在启动...")

        except Exception as e:
            self._on_error(f"启动失败: {e}")

    def _on_stop(self):
        """停止按钮点击事件"""
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None

        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.video_label.setText("已停止")
        self.label_camera_fps.setText("Camera FPS: 0")
        self.label_detect_fps.setText("Detect FPS: 0")

    def _on_load_model(self):
        """加载模型按钮点击事件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件",  r"E:\deeplearning/qt - 副本/yolo", "YOLO Models (*.pt);;All Files (*)"
        )
        if path:
            self._model_path = path
            self._on_error(f"模型已设置: {path}")

    def _update_video(self, frame: np.ndarray):
        """更新视频显示"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.video_label.setPixmap(scaled)

    def _update_mcu_response(self, data: bytes):
        """显示 MCU 回显（hex 格式）"""
        hex_str = ' '.join(f'{b:02X}' for b in data)
        timestamp = time.strftime("%H:%M:%S")
        self.text_mcu_response.append(f"[{timestamp}] << {hex_str}")

        doc = self.text_mcu_response.document()
        if doc.lineCount() > 100:
            cursor = self.text_mcu_response.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def _on_error(self, msg: str):
        """错误信息显示"""
        timestamp = time.strftime("%H:%M:%S")
        self.text_mcu_response.append(f"[{timestamp}] ERROR: {msg}")

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.pipeline:
            self.pipeline.stop()
        event.accept()