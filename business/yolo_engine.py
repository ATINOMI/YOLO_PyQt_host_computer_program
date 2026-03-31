"""
YOLO 推理引擎（纯推理 + 频率控制）
"""
import time
import numpy as np
from typing import List
from ultralytics import YOLO
from business.types import Detection


class YOLOEngine:
    """YOLO 推理引擎"""

    def __init__(self, model_path: str, conf_threshold: float = 0.45, detect_fps: float = 10.0):
        """
        Args:
            model_path: YOLO 模型路径
            conf_threshold: 置信度阈值
            detect_fps: 检测帧率（控制推理频率）
        """
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.detect_fps = detect_fps
        self.last_infer_time = 0.0

    def should_infer(self) -> bool:
        """
        根据 detect_fps 判断是否需要推理
        复用 hello_qt.py 第 217-223 行的频率控制逻辑
        """
        now = time.time()
        interval = 1.0 / max(0.0001, self.detect_fps)
        return (now - self.last_infer_time) >= interval

    def infer(self, frame: np.ndarray) -> List[Detection]:
        """
        执行 YOLO 推理
        复用 hello_qt.py 第 228-259 行的推理逻辑

        Args:
            frame: BGR 格式的图像帧

        Returns:
            检测结果列表
        """
        self.last_infer_time = time.time()

        try:
            results = self.model(frame, verbose=False)[0]
        except Exception as e:
            print(f"YOLO inference failed: {e}")
            return []

        detections = []
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls = int(box.cls[0])
            name = self.model.names.get(cls, str(cls))

            detections.append(Detection(
                class_id=cls,
                class_name=name,
                confidence=conf,
                bbox=(x1, y1, x2, y2)
            ))

        return detections

    def update_conf_threshold(self, threshold: float):
        """更新置信度阈值"""
        self.conf_threshold = threshold

    def update_detect_fps(self, fps: float):
        """更新检测帧率"""
        self.detect_fps = fps
