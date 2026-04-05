"""
检测结果量化模块
"""
from typing import List, Optional
from business.types import Detection, QuantizedData


class CommandQuantizer:
    """
    命令量化器：将检测结果映射为控制指令

    映射规则：
    - 检测到 "open" → 0xF0
    - 检测到 "close" → 0x30
    - 未检测到或其他 → 0x00（默认）
    """

    def __init__(self):
        """初始化命令映射表"""
        self.command_map = {
            'open': 0xF0,
            'close': 0x30
        }
        self.default_command = 0x00

    def quantize(self, detections: List[Detection]) -> QuantizedData:
        """
        量化检测结果为控制指令

        Args:
            detections: 检测结果列表

        Returns:
            量化后的数据（包含单个命令字节）
        """
        # 默认命令
        command = self.default_command

        # 遍历检测结果，查找第一个匹配的类别
        for det in detections:
            class_name = det.class_name.lower()  # 转小写以支持大小写不敏感匹配
            if class_name in self.command_map:
                command = self.command_map[class_name]
                break  # 找到第一个匹配就退出

        # 返回统一的 QuantizedData 格式
        # objects 中只包含一个命令字典
        return QuantizedData(
            count=1,
            objects=[{'command': command}]
        )

    def update_command_map(self, class_name: str, command: int):
        """
        更新命令映射表

        Args:
            class_name: 类别名称
            command: 对应的命令字节（0-255）
        """
        self.command_map[class_name.lower()] = command & 0xFF


class SimpleQuantizer:
    """
    简单量化器：将检测结果量化为整数（便于二进制传输）

    量化策略：
    - bbox 中心点坐标归一化到 0-255（1 字节）
    - bbox 宽高归一化到 0-255
    - confidence 映射到 0-100（百分比）
    """

    def __init__(self, img_width: int = 640, img_height: int = 480):
        """
        Args:
            img_width: 图像宽度（用于归一化）
            img_height: 图像高度（用于归一化）
        """
        self.img_w = img_width
        self.img_h = img_height

    def quantize(self, detections: List[Detection]) -> QuantizedData:
        """
        量化检测结果

        Args:
            detections: 检测结果列表

        Returns:
            量化后的数据
        """
        objects = []
        for det in detections:
            x1, y1, x2, y2 = det.bbox

            # 计算中心点
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            w = x2 - x1
            h = y2 - y1

            # 归一化到 0-255
            cx_norm = int((cx / self.img_w) * 255)
            cy_norm = int((cy / self.img_h) * 255)
            w_norm = int((w / self.img_w) * 255)
            h_norm = int((h / self.img_h) * 255)
            conf_norm = int(det.confidence * 100)

            # 限制范围
            cx_norm = max(0, min(255, cx_norm))
            cy_norm = max(0, min(255, cy_norm))
            w_norm = max(0, min(255, w_norm))
            h_norm = max(0, min(255, h_norm))
            conf_norm = max(0, min(100, conf_norm))

            objects.append({
                'class_id': det.class_id,
                'conf': conf_norm,
                'cx': cx_norm,
                'cy': cy_norm,
                'w': w_norm,
                'h': h_norm
            })

        return QuantizedData(count=len(objects), objects=objects)

    def update_image_size(self, width: int, height: int):
        """更新图像尺寸"""
        self.img_w = width
        self.img_h = height

class ScallopQuantizer:
    """
    贝柱量化器:根据贝柱水平位置输出左/右/停命令
    """

    def __init__(self,img_width: int=640):
        self.img_w =img_width

    def quantize(self ,detections:List[Detection]) ->QuantizedData:
        if not detections:
            #没检测到，停止
            return QuantizedData(count=1,objects=[{'command':0x00}])
        
        #1.选置信度最高的
        best =max(detections,key=lambda d: d.confidence)
        
        #2.算中心 x
        x1,y1,x2,y2=best.bbox
        cx=(x1+x2)//2
        
        if cx < self.img_w*3/8:
            command = 0x11 #left

        elif cx > self.img_w*5/8:
            command=0x12 #right

        else:
            command=0x13 #stop

        return QuantizedData(count=1,objects=[{'command':command}])
