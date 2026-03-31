# YOLO 串口上位机 MVP 阶段性验证指南

## 验证环境

- Python 3.x
- 依赖库: PyQt5, opencv-python, ultralytics, pyserial, numpy

## 阶段 1: 相机 → UI（无推理）

**目标**: 验证相机采集和 UI 显示功能

**步骤**:
1. 临时修改 `controller/pipeline.py` 的 `_on_frame` 方法，注释推理相关代码
2. 运行 `python main.py`
3. 点击"启动检测"按钮

**验证点**:
- UI 显示实时视频流
- Camera FPS 显示正常（接近 30 fps）
- 视频流畅无卡顿

**修改示例**（暂时注释推理部分）:
```python
def _on_frame(self, frame: np.ndarray, frame_id: int):
    # 暂时注释推理逻辑，直接显示原始帧
    # if self.yolo.should_infer():
    #     detections = self.yolo.infer(frame)
    #     ...

    display_frame = frame.copy()  # 直接使用原始帧
    self.sig_processed_frame.emit(display_frame)
```

---

## 阶段 2: 相机 → YOLO → UI（有推理，无串口）

**目标**: 验证 YOLO 推理和检测框绘制

**步骤**:
1. 恢复 `controller/pipeline.py` 的推理逻辑
2. 临时注释串口发送部分（在 `_on_frame` 方法中）
3. 运行 `python main.py`
4. 点击"启动检测"按钮

**验证点**:
- UI 显示实时视频流
- 检测框和标签显示正常
- Detect FPS 显示正常（接近设置的检测帧率，如 10 fps）
- Camera FPS 和 Detect FPS 分别统计正确

**修改示例**（暂时注释串口发送）:
```python
# 量化并发送到串口
# if detections and self.serial.is_open():
#     try:
#         quantized = self.quantizer.quantize(detections)
#         packet = Protocol.pack_detection(quantized)
#         self.serial.write(packet)
#     except Exception as e:
#         self.sig_error.emit(f"协议封装失败: {e}")
```

---

## 阶段 3: 完整流程（含串口回环）

**目标**: 验证串口收发和协议封装

**步骤**:
1. 恢复所有代码（无需注释）
2. 使用串口回环测试（TX 接 RX）或虚拟串口工具
   - Windows: 使用 com0com 或 Virtual Serial Port Driver
   - Linux: `socat -d -d pty,raw,echo=0 pty,raw,echo=0`
3. 运行 `python main.py`
4. 配置串口（如 COM3 或虚拟串口）
5. 点击"启动检测"按钮

**验证点**:
- MCU 回显区能看到发送的 hex 数据
- 数据格式符合协议规范：`AA 55 01 00 0D ...`
- 检测到对象时能看到完整的数据包
- 串口配置（波特率、数据位、校验位、停止位）生效

**手动验证协议格式**:
- 帧头: `AA 55`
- 类型: `01`
- 长度: `00 XX` (小端序)
- 对象数: 1 字节
- 每个对象: 6 字节（class_id, conf, cx, cy, w, h）
- 校验和: 1 字节（payload 字节和 & 0xFF）
- 帧尾: `0A` (\n)

---

## 阶段 4: 真实 MCU 对接

**目标**: 与真实 STM32 或其他 MCU 通信

**前提条件**:
- MCU 固件已烧录协议解析代码
- 串口连接正确（TX→RX, RX→TX, GND→GND）

**步骤**:
1. 连接 MCU 串口
2. 配置正确的串口号和波特率
3. 运行 `python main.py`
4. 点击"启动检测"按钮
5. 观察 MCU 响应

**验证点**:
- MCU 正确解析数据包
- MCU 回传 ACK/NACK 响应
- MCU 回显区显示回传数据
- 使用示波器/逻辑分析仪验证波形

**调试工具**:
- 串口调试助手（查看原始数据）
- 逻辑分析仪（验证波形和时序）
- MCU UART 中断/DMA 调试

---

## 快速运行（无修改）

如果您想直接运行完整程序:

```bash
cd E:/deeplearning/ultralytics11/qt
python main.py
```

**默认配置**:
- 串口: COM3
- 波特率: 115200
- 数据位: 8
- 校验位: None
- 停止位: 1
- 检测 FPS: 10
- 模型: yolo11n.pt

---

## 常见问题

### 1. 串口打开失败
- 检查串口号是否正确
- 检查串口是否被其他程序占用
- Windows: 检查设备管理器中的端口号
- Linux: 检查权限 `sudo chmod 666 /dev/ttyUSB0`

### 2. 摄像头打开失败
- 检查摄像头是否连接
- 尝试更改 `camera_index`（0, 1, 2...）
- 检查摄像头是否被其他程序占用

### 3. 模型加载失败
- 检查 `yolo11n.pt` 是否存在
- 尝试重新下载模型
- 点击"加载模型"按钮选择正确的模型文件

### 4. 检测框不显示
- 检查置信度阈值是否过高
- 检查检测 FPS 是否设置合理
- 检查模型是否适合检测场景

---

## 协议调试示例

假设检测到 1 个对象（class_id=0, conf=80%, cx=100, cy=100, w=32, h=24）:

```
AA 55        # 帧头（小端序 0xAA55）
01           # 类型（检测数据）
00 07        # 长度（小端序，payload 7 字节）
01           # 对象数（1 个对象）
00           # class_id = 0
50           # conf = 80 (0x50)
64           # cx = 100 (0x64)
64           # cy = 100 (0x64)
20           # w = 32 (0x20)
18           # h = 24 (0x18)
DB           # 校验和 (0x01+0x00+0x50+0x64+0x64+0x20+0x18) & 0xFF = 0xDB
0A           # 帧尾 (\n)
```

完整包（hex）: `AA 55 01 00 07 01 00 50 64 64 20 18 DB 0A`

---

## 下一步优化（后续迭代）

1. **协议解析**: 实现 `Protocol.parse_mcu_response` 完整解析逻辑
2. **配置持久化**: 保存/加载串口和检测参数
3. **多摄像头支持**: 下拉选择摄像头
4. **日志记录**: 记录检测结果和串口数据到文件
5. **性能优化**: 使用 YOLO TensorRT 加速推理
6. **EventBus**: 解耦模块间通信
7. **完整 UI 状态机**: 更好的启动/停止/错误处理
