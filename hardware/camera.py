"""
摄像头采集模块（纯采集，不含推理）
"""
import time
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal


class Camera(QThread):
    """摄像头采集线程"""
    sig_frame_ready = pyqtSignal(np.ndarray, int)  # (frame, frame_id)
    sig_fps = pyqtSignal(float)
    sig_error = pyqtSignal(str)

    def __init__(self, camera_index: int, target_fps: int = 30):
        super().__init__()
        self.camera_index = camera_index
        self.target_fps = target_fps
        self._running = False
        self._frame_counter = 0

    def run(self):
        """采集主循环"""
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.sig_error.emit(f"无法打开摄像头 {self.camera_index}")
            return

        last_time = time.time()

        while self._running:
            ret, frame = cap.read()
            if not ret:
                self.sig_error.emit("摄像头读取失败")
                break

            # 计算 FPS（复用 hello_qt.py 第 186-189 行逻辑）
            current_time = time.time()
            fps = 1.0 / (current_time - last_time) if (current_time - last_time) > 0 else 0.0
            last_time = current_time
            self.sig_fps.emit(fps)

            # 发送帧
            self._frame_counter += 1
            self.sig_frame_ready.emit(frame, self._frame_counter)

            # 控制采集帧率
            if self.target_fps > 0:
                time.sleep(1.0 / self.target_fps)

        cap.release()

    def start(self):
        """启动采集"""
        self._running = True
        super().start()

    def stop(self):
        """停止采集"""
        self._running = False
        self.wait()
