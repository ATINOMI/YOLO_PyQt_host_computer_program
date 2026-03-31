"""
数据流编排控制器

数据流：
Camera.sig_frame_ready → Pipeline._on_frame()
    ├→ YOLOEngine.infer() → Detection[]
    ├→ Quantizer.quantize() → QuantizedData
    ├→ Protocol.pack_command/pack_detection() → bytes
    └→ SerialPort.write(bytes)

SerialPort.sig_data_received → Pipeline._on_mcu_data()
    └→ sig_mcu_response.emit(bytes)
"""
import time
import cv2
import numpy as np
from typing import List
from PyQt5.QtCore import QObject, pyqtSignal

from hardware.camera import Camera
from hardware.serial_port import SerialPort
from business.yolo_engine import YOLOEngine
from business.quantizer import SimpleQuantizer, CommandQuantizer,ScallopQuantizer
from business.protocol import Protocol
from business.types import Detection


class DataPipeline(QObject):
    """数据流编排器"""

    sig_processed_frame = pyqtSignal(np.ndarray)
    sig_detections = pyqtSignal(list)  # List[Detection]
    sig_mcu_response = pyqtSignal(bytes)
    sig_camera_fps = pyqtSignal(float)
    sig_detect_fps = pyqtSignal(float)
    sig_error = pyqtSignal(str)

    def __init__(self, config: dict):
        """
        Args:
            config: 配置字典，包含：
                - camera_index: 摄像头索引
                - camera_fps: 摄像头帧率
                - detect_fps: 检测帧率
                - model_path: YOLO 模型路径
                - conf_threshold: 置信度阈值
                - serial_port: 串口号
                - baudrate: 波特率
                - bytesize: 数据位（可选，默认 8）
                - parity: 校验位（可选，默认 'N'）
                - stopbits: 停止位（可选，默认 1）
                - quantizer_mode: 量化模式（可选，'bbox' 或 'command'，默认 'command'）
        """
        super().__init__()

        # 初始化各模块
        self.camera = Camera(config['camera_index'], config.get('camera_fps', 30))
        self.yolo = YOLOEngine(
            config['model_path'],
            config.get('conf_threshold', 0.45),
            config.get('detect_fps', 10)
        )

        # 根据模式选择量化器
        self.quantizer_mode = config.get('quantizer_mode', 'command')
        if self.quantizer_mode == 'bbox':
            self.quantizer = SimpleQuantizer(img_width=640, img_height=480)
        elif self.quantizer_mode == 'scallop':
            self.quantizer =ScallopQuantizer(img_width=640)
        else:
            self.quantizer =CommandQuantizer()

        self.serial = SerialPort()

        # 配置串口
        self.serial.configure(
            config['serial_port'],
            config['baudrate'],
            config.get('bytesize', 8),
            config.get('parity', 'N'),
            config.get('stopbits', 1)
        )

        # 连接信号
        self.camera.sig_frame_ready.connect(self._on_frame)
        self.camera.sig_fps.connect(self.sig_camera_fps.emit)
        self.camera.sig_error.connect(self.sig_error.emit)
        self.serial.sig_data_received.connect(self._on_mcu_data)
        self.serial.sig_error.connect(self.sig_error.emit)

        # 内部状态
        self._latest_detections = []
        self._detect_fps_counter = 0
        self._detect_fps_timer = time.time()

    def start(self):
        """启动数据流"""
        # 先打开串口
        if not self.serial.open_port():
            self.sig_error.emit("串口打开失败，继续运行但无法发送数据")

        # 启动摄像头
        self.camera.start()

    def stop(self):
        """停止数据流"""
        self.camera.stop()
        self.serial.close_port()

    def _on_frame(self, frame: np.ndarray, frame_id: int):
        """
        相机帧回调

        Args:
            frame: BGR 格式的图像帧
            frame_id: 帧 ID
        """
        # 判断是否需要推理
        if self.yolo.should_infer():
            detections = self.yolo.infer(frame)
            self._latest_detections = detections

            # 发送检测结果
            self.sig_detections.emit(detections)

            # 量化并发送到串口
            if self.serial.is_open():
                try:
                    quantized = self.quantizer.quantize(detections)

                    # 根据量化模式选择封装方法
                    if self.quantizer_mode == 'bbox':
                        # bbox 模式：只有检测结果时才发送完整协议包
                        if detections:
                            packet = Protocol.pack_detection(quantized)
                            self.serial.write(packet)
                    else:  # 'command' 模式
                        # command 模式：直接发送单字节命令（不封装协议）
                        if quantized.objects and 'command' in quantized.objects[0]:
                            command_byte = bytes([quantized.objects[0]['command'] & 0xFF])
                            self.serial.write(command_byte)
                except Exception as e:
                    self.sig_error.emit(f"数据发送失败: {e}")

            # 统计检测 FPS
            self._detect_fps_counter += 1
            if time.time() - self._detect_fps_timer >= 1.0:
                self.sig_detect_fps.emit(self._detect_fps_counter)
                self._detect_fps_counter = 0
                self._detect_fps_timer = time.time()

        # 绘制检测框（复用 hello_qt.py 第 253-259 行）
        display_frame = self._draw_detections(frame, self._latest_detections)
        self.sig_processed_frame.emit(display_frame)

    def _draw_detections(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """
        绘制检测框

        Args:
            frame: 原始帧
            detections: 检测结果列表

        Returns:
            绘制后的帧
        """
        frame_copy = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = (0, 255, 0)

            # 绘制矩形框
            cv2.rectangle(frame_copy, (x1, y1), (x2, y2), color, 2)

            # 绘制标签
            label = f"{det.class_name} {det.confidence:.2f}"
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(frame_copy, (x1, y1 - 20), (x1 + w, y1), color, -1)
            cv2.putText(frame_copy, label, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

        return frame_copy

    def _on_mcu_data(self, data: bytes):
        """
        MCU 数据回调（MVP: 直接透传）

        Args:
            data: MCU 返回的字节数据
        """
        self.sig_mcu_response.emit(data)

    def update_detect_fps(self, fps: float):
        """更新检测帧率"""
        self.yolo.update_detect_fps(fps)

    def update_conf_threshold(self, threshold: float):
        """更新置信度阈值"""
        self.yolo.update_conf_threshold(threshold)
