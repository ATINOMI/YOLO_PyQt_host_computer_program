# 量化策略修改指南

本文档说明如何修改量化策略和调整参数，以适应不同的应用场景。

## 目录
- [量化器概述](#量化器概述)
- [命令模式调参](#命令模式调参)
- [Bbox模式调参](#bbox模式调参)
- [添加新的量化器](#添加新的量化器)
- [常见场景示例](#常见场景示例)

---

## 量化器概述

项目包含两种量化器，位于 `business/quantizer.py`：

### 1. CommandQuantizer（命令模式）
- **用途**：将检测结果映射为单字节控制指令
- **输出**：单字节命令（如 `0xF0`, `0x30`）
- **适用场景**：简单的开关控制、状态切换

### 2. SimpleQuantizer（Bbox模式）
- **用途**：将检测框坐标量化为 0-255 范围的整数
- **输出**：完整的检测数据包（类别、置信度、坐标）
- **适用场景**：需要精确位置信息的应用

---

## 命令模式调参

### 修改命令映射

**文件位置**：`business/quantizer.py` → `CommandQuantizer.__init__()`

#### 场景 1：修改现有命令字节

```python
def __init__(self):
    """初始化命令映射表"""
    self.command_map = {
        'open': 0xF0,    # 修改为其他值，如 0x01
        'close': 0x30    # 修改为其他值，如 0x02
    }
    self.default_command = 0x00  # 未检测到时的默认命令
```

**示例**：改为简单的 0x01/0x02
```python
self.command_map = {
    'open': 0x01,
    'close': 0x02
}
```

#### 场景 2：添加新的类别映射

```python
def __init__(self):
    self.command_map = {
        'open': 0xF0,
        'close': 0x30,
        'stop': 0x00,      # 新增：停止命令
        'forward': 0xA0,   # 新增：前进命令
        'backward': 0xB0   # 新增：后退命令
    }
    self.default_command = 0x00
```

#### 场景 3：运行时动态修改映射

在 UI 或其他地方调用：

```python
# 在 pipeline 初始化后
pipeline.quantizer.update_command_map('open', 0x01)
pipeline.quantizer.update_command_map('close', 0x02)
```

### 修改默认命令

当没有检测到任何目标时发送的命令：

```python
self.default_command = 0xFF  # 改为 0xFF 表示"无目标"
```

### 修改匹配逻辑

**文件位置**：`business/quantizer.py` → `CommandQuantizer.quantize()`

#### 当前逻辑：匹配第一个识别到的类别

```python
def quantize(self, detections: List[Detection]) -> QuantizedData:
    command = self.default_command

    for det in detections:
        class_name = det.class_name.lower()
        if class_name in self.command_map:
            command = self.command_map[class_name]
            break  # 找到第一个就退出

    return QuantizedData(count=1, objects=[{'command': command}])
```

#### 修改为：优先级匹配（按置信度）

```python
def quantize(self, detections: List[Detection]) -> QuantizedData:
    command = self.default_command
    max_confidence = 0.0

    # 选择置信度最高的匹配类别
    for det in detections:
        class_name = det.class_name.lower()
        if class_name in self.command_map and det.confidence > max_confidence:
            command = self.command_map[class_name]
            max_confidence = det.confidence

    return QuantizedData(count=1, objects=[{'command': command}])
```

#### 修改为：多目标组合命令

```python
def quantize(self, detections: List[Detection]) -> QuantizedData:
    # 检测多个目标，生成组合命令
    has_open = any(d.class_name.lower() == 'open' for d in detections)
    has_close = any(d.class_name.lower() == 'close' for d in detections)

    if has_open and has_close:
        command = 0xFF  # 同时检测到 open 和 close，发送特殊命令
    elif has_open:
        command = 0xF0
    elif has_close:
        command = 0x30
    else:
        command = 0x00

    return QuantizedData(count=1, objects=[{'command': command}])
```

---

## Bbox模式调参

### 修改图像尺寸

**文件位置**：`business/quantizer.py` → `SimpleQuantizer.__init__()`

```python
def __init__(self, img_width: int = 640, img_height: int = 480):
    self.img_w = img_width
    self.img_h = img_height
```

**运行时更新**（当摄像头分辨率改变时）：

```python
# 在 pipeline 中
pipeline.quantizer.update_image_size(1920, 1080)
```

### 修改量化范围

#### 当前策略：归一化到 0-255

```python
cx_norm = int((cx / self.img_w) * 255)
cy_norm = int((cy / self.img_h) * 255)
w_norm = int((w / self.img_w) * 255)
h_norm = int((h / self.img_h) * 255)
conf_norm = int(det.confidence * 100)  # 置信度 0-100
```

#### 修改为：归一化到 0-100

```python
cx_norm = int((cx / self.img_w) * 100)
cy_norm = int((cy / self.img_h) * 100)
w_norm = int((w / self.img_w) * 100)
h_norm = int((h / self.img_h) * 100)
conf_norm = int(det.confidence * 100)
```

#### 修改为：使用绝对像素值（需要 2 字节）

```python
# 注意：需要同时修改 protocol.py 的封装格式
cx_norm = cx  # 直接使用像素值
cy_norm = cy
w_norm = w
h_norm = h
conf_norm = int(det.confidence * 100)
```

### 添加置信度过滤

在量化前过滤低置信度目标：

```python
def quantize(self, detections: List[Detection]) -> QuantizedData:
    # 过滤置信度低于 0.5 的目标
    filtered = [d for d in detections if d.confidence >= 0.5]

    objects = []
    for det in filtered:
        # ... 量化逻辑
```

### 限制最大目标数

```python
def quantize(self, detections: List[Detection]) -> QuantizedData:
    # 只保留前 5 个目标
    detections = detections[:5]

    objects = []
    for det in detections:
        # ... 量化逻辑
```

---

## 添加新的量化器

### 示例：区域量化器（将画面分为 9 宫格）

在 `business/quantizer.py` 中添加：

```python
class RegionQuantizer:
    """
    区域量化器：将检测框映射到 3x3 网格区域

    输出：区域编号（0-8）
    0 1 2
    3 4 5
    6 7 8
    """

    def __init__(self, img_width: int = 640, img_height: int = 480):
        self.img_w = img_width
        self.img_h = img_height

    def quantize(self, detections: List[Detection]) -> QuantizedData:
        if not detections:
            return QuantizedData(count=1, objects=[{'region': 4}])  # 默认中心

        # 取第一个目标的中心点
        det = detections[0]
        x1, y1, x2, y2 = det.bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        # 计算所在区域
        col = min(2, cx // (self.img_w // 3))  # 0, 1, 2
        row = min(2, cy // (self.img_h // 3))  # 0, 1, 2
        region = row * 3 + col

        return QuantizedData(count=1, objects=[{'region': region}])

    def update_image_size(self, width: int, height: int):
        self.img_w = width
        self.img_h = height
```

### 在 pipeline.py 中使用新量化器

修改 `controller/pipeline.py`：

```python
from business.quantizer import SimpleQuantizer, CommandQuantizer, RegionQuantizer

# 在 __init__ 中
self.quantizer_mode = config.get('quantizer_mode', 'command')
if self.quantizer_mode == 'bbox':
    self.quantizer = SimpleQuantizer(img_width=640, img_height=480)
elif self.quantizer_mode == 'region':
    self.quantizer = RegionQuantizer(img_width=640, img_height=480)
else:  # 'command' 模式
    self.quantizer = CommandQuantizer()
```

### 在 UI 中添加选项

修改 `ui/main_window.py`：

```python
self.input_quantizer_mode.addItems([
    '命令模式 (open/close→0xF0/0x30)',
    'bbox模式 (详细坐标)',
    '区域模式 (3x3网格)'  # 新增
])
```

```python
# 在 _on_start() 中
quantizer_mode_map = {
    0: 'command',
    1: 'bbox',
    2: 'region'  # 新增
}
quantizer_mode = quantizer_mode_map.get(
    self.input_quantizer_mode.currentIndex(),
    'command'
)
```

---

## 常见场景示例

### 场景 1：机械臂控制（需要精确坐标）

使用 **SimpleQuantizer**，调整归一化范围：

```python
# 机械臂工作空间 800x600mm
quantizer = SimpleQuantizer(img_width=640, img_height=480)

# 修改量化逻辑，映射到实际工作空间
def quantize(self, detections):
    # ...
    # 映射到 0-800mm 和 0-600mm
    cx_mm = int((cx / self.img_w) * 800)
    cy_mm = int((cy / self.img_h) * 600)
```

### 场景 2：智能门锁（只需开/关）

使用 **CommandQuantizer**，简化命令：

```python
self.command_map = {
    'face': 0x01,      # 检测到人脸 → 开锁
    'unknown': 0x00    # 未知 → 保持锁定
}
```

### 场景 3：自动跟踪（需要方向指令）

使用 **RegionQuantizer** 或自定义：

```python
class DirectionQuantizer:
    """输出方向命令：上下左右"""

    def quantize(self, detections):
        if not detections:
            return QuantizedData(count=1, objects=[{'direction': 0x00}])  # 停止

        det = detections[0]
        cx = (det.bbox[0] + det.bbox[2]) // 2
        cy = (det.bbox[1] + det.bbox[3]) // 2

        # 判断目标在画面的哪个区域
        if cx < self.img_w // 3:
            direction = 0x01  # 左
        elif cx > self.img_w * 2 // 3:
            direction = 0x02  # 右
        elif cy < self.img_h // 3:
            direction = 0x03  # 上
        elif cy > self.img_h * 2 // 3:
            direction = 0x04  # 下
        else:
            direction = 0x00  # 中心，停止

        return QuantizedData(count=1, objects=[{'direction': direction}])
```

### 场景 4：多目标优先级（选择最大/最近的目标）

修改 `CommandQuantizer.quantize()`：

```python
def quantize(self, detections: List[Detection]) -> QuantizedData:
    if not detections:
        return QuantizedData(count=1, objects=[{'command': self.default_command}])

    # 选择面积最大的目标
    largest = max(detections, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))

    class_name = largest.class_name.lower()
    command = self.command_map.get(class_name, self.default_command)

    return QuantizedData(count=1, objects=[{'command': command}])
```

---

## 调试技巧

### 1. 打印量化结果

在 `controller/pipeline.py` 的 `_on_frame()` 中添加：

```python
quantized = self.quantizer.quantize(detections)
print(f"量化结果: {quantized}")  # 调试输出
```

### 2. 验证命令映射

在 Python 交互式环境中测试：

```python
from business.types import Detection
from business.quantizer import CommandQuantizer

det = Detection(class_id=0, class_name='open', confidence=0.85, bbox=(100, 100, 200, 200))
quantizer = CommandQuantizer()
result = quantizer.quantize([det])
print(f"命令字节: {hex(result.objects[0]['command'])}")
```

### 3. 监控串口数据

在 `ui/main_window.py` 的 `_update_mcu_response()` 中查看实际发送的数据。

---

## 快速参考

| 需求 | 使用量化器 | 修改位置 |
|------|-----------|---------|
| 修改命令字节 | CommandQuantizer | `quantizer.py` → `__init__()` |
| 添加新类别 | CommandQuantizer | `quantizer.py` → `command_map` |
| 修改坐标范围 | SimpleQuantizer | `quantizer.py` → `quantize()` |
| 改变图像尺寸 | SimpleQuantizer | `quantizer.py` → `__init__()` |
| 添加新量化器 | 自定义类 | `quantizer.py` + `pipeline.py` + `main_window.py` |
| 修改匹配逻辑 | CommandQuantizer | `quantizer.py` → `quantize()` |

---

## 注意事项

1. **修改后需要重启程序**：量化器在 `DataPipeline` 初始化时创建，修改代码后需要重启应用。

2. **协议兼容性**：如果修改了量化输出格式（如从 1 字节改为 2 字节），需要同步修改 `business/protocol.py` 的封装逻辑。

3. **MCU 端同步**：修改命令字节后，确保 MCU 固件中的命令解析逻辑也相应更新。

4. **测试验证**：使用 `test_modules.py` 或串口回环测试验证修改后的量化逻辑。

5. **性能考虑**：复杂的量化逻辑会增加处理时间，注意保持检测 FPS。
