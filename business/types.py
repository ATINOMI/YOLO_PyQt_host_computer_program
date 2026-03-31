"""
核心数据类型定义
"""
from dataclasses import dataclass
from typing import List, Tuple, Dict


@dataclass
class Detection:
    """单个检测对象"""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)


@dataclass
class QuantizedData:
    """量化后的检测数据（用于二进制传输）"""
    count: int
    objects: List[Dict[str, int]]  # [{class_id, conf, cx, cy, w, h}, ...]


@dataclass
class Packet:
    """二进制协议包"""
    frame_type: int
    payload: bytes
    checksum: int
