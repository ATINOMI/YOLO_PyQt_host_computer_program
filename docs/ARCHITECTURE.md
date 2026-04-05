# YOLO 串口上位机架构文档

本文档如实记录项目当前的架构现状，包括模块划分、职责边界、数据流和训练工具。

---

## 项目概述

本项目是一个基于 YOLO 的视觉检测上位机应用，实现摄像头采集、目标检测、结果量化、串口通信的完整数据流。

**技术栈**：

- GUI 框架：PyQt5
- 视觉处理：OpenCV、Ultralytics YOLO
- 串口通信：PySerial
- 数据处理：NumPy

---

## 目录结构

```
项目根目录/
├── main.py                        # 应用入口
├── hardware/                      # 硬件接口层
│   ├── camera.py                  # 摄像头采集模块
│   └── serial_port.py             # 串口收发模块
├── business/                      # 业务逻辑层
│   ├── types.py                   # 数据类型定义
│   ├── yolo_engine.py             # YOLO 推理引擎
│   ├── quantizer.py               # 检测结果量化器
│   └── protocol.py                # 二进制协议封装
├── controller/                    # 控制器层
│   └── pipeline.py                # 数据流编排控制器
├── ui/                           # 用户界面层
│   ├── styles.py                  # QSS 样式定义
│   └── main_window.py             # 主窗口
├── my_train.py                    # 模型训练脚本（独立工具）
├── mypredit.py                    # 模型预测脚本（独立工具）
├── hands&fists/                   # 训练数据集目录
│   └── hands&fists/
│       ├── hd.yaml                # 数据集配置
│       ├── images/                # 图像数据（train/val/test）
│       └── labels/                # 标注数据
├── test_modules.py                # 模块单元测试
├── yolo11n.pt                     # YOLO 预训练模型
├── best.pt                        # 训练后的最佳模型
└── runs/                          # 训练输出目录
```

---

## 模块划分与职责

### 1. 硬件接口层 (hardware/)

**职责**：封装硬件设备的底层操作，提供统一的接口给上层调用。

#### hardware/camera.py

- **类**：`Camera(QThread)`
- **职责**：摄像头采集，不包含任何推理逻辑
- **功能**：
  - 打开/关闭摄像头（`cv2.VideoCapture`）
  - 连续采集视频帧（在独立线程中运行）
  - 计算并发送摄像头 FPS
  - 控制采集帧率
- **信号**：
  - `sig_frame_ready(np.ndarray, int)` - 发送采集到的帧和帧 ID
  - `sig_fps(float)` - 发送摄像头 FPS
  - `sig_error(str)` - 发送错误信息
- **依赖**：OpenCV (`cv2`)

#### hardware/serial_port.py

- **类**：`SerialPort(QThread)`
- **职责**：串口收发和参数配置
- **功能**：
  - 配置串口参数（波特率、数据位、校验位、停止位）
  - 打开/关闭串口
  - 异步发送数据（使用队列 `self.write_queue`）
  - 异步接收数据（收到数据直接 emit，无分包处理）
  - 列出可用串口（`serial.tools.list_ports`）
- **信号**：
  - `sig_data_received(bytes)` - 发送接收到的数据包
  - `sig_port_opened(str)` - 串口打开成功
  - `sig_port_closed()` - 串口关闭
  - `sig_error(str)` - 发送错误信息
- **依赖**：PySerial (`serial`)

---

### 2. 业务逻辑层 (business/)

**职责**：处理核心业务逻辑，不涉及硬件操作和 UI 显示。

#### business/types.py

- **职责**：定义核心数据类型
- **数据类**：
  - `Detection` - 单个检测对象
    - `class_id: int` - 类别 ID
    - `class_name: str` - 类别名称
    - `confidence: float` - 置信度
    - `bbox: Tuple[int, int, int, int]` - 边界框 (x1, y1, x2, y2)
  - `QuantizedData` - 量化后的检测数据
    - `count: int` - 对象数量
    - `objects: List[Dict[str, int]]` - 量化后的对象列表
  - `Packet` - 二进制协议包
    - `frame_type: int` - 帧类型
    - `payload: bytes` - 有效载荷
    - `checksum: int` - 校验和

#### business/yolo_engine.py

- **类**：`YOLOEngine`
- **职责**：YOLO 模型推理和频率控制
- **功能**：
  - 加载 YOLO 模型（`ultralytics.YOLO`）
  - 执行推理（输入 BGR 图像，输出 `Detection` 列表）
  - 根据 `detect_fps` 控制推理频率（`should_infer()` 方法）
  - 应用置信度阈值过滤
  - 动态更新置信度阈值和检测帧率
- **方法**：
  - `should_infer() -> bool` - 判断是否需要推理（基于时间间隔）
  - `infer(frame) -> List[Detection]` - 执行推理
  - `update_conf_threshold(threshold)` - 更新置信度阈值
  - `update_detect_fps(fps)` - 更新检测帧率
- **依赖**：Ultralytics YOLO

#### business/quantizer.py

- **类**：
  - `CommandQuantizer` - 命令量化器
  - `SimpleQuantizer` - 简单量化器
  - `ScallopQuantizer`- 贝柱位置量化器 

##### CommandQuantizer

- **职责**：将检测结果映射为控制指令
- **量化策略**：
  - 检测到 "open" → `0xF0`
  - 检测到 "close" → `0x30`
  - 未检测到或其他 → `0x00`（默认）
- **方法**：
  - `quantize(detections) -> QuantizedData` - 执行量化
  - `update_command_map(class_name, command)` - 更新命令映射表

##### SimpleQuantizer

- **职责**：将检测结果量化为整数（便于二进制传输）
- **量化策略**：
  - bbox 中心点坐标归一化到 0-255（1 字节）
  - bbox 宽高归一化到 0-255
  - confidence 映射到 0-100（百分比）
- **方法**：
  - `quantize(detections) -> QuantizedData` - 执行量化
  - `update_image_size(width, height)` - 更新图像尺寸

##### ScallopQuantizer

- 职责：将检测结果映射为指令

- 量化策略：
  
  - bbox中心点坐标求解
  
  - 优先选择confidence最高的检测结果
  
  - 中心点坐标比较img_w

- 方法：
  
  - `quantize(detections) -> QuantizedData` - 执行量化

#### business/protocol.py

- **类**：`Protocol`

- **职责**：二进制协议的封装和解析

- **协议格式**（大端序）：
  
  ```
  [帧头 2B] [类型 1B] [长度 2B] [Payload] [校验和 1B] [帧尾 1B]
   0xAA55     0x01/02  N bytes    数据      Sum&0xFF    0x0A
  ```

- **帧类型**：
  
  - `0x01` - 检测数据（详细 bbox）
  - `0x02` - 控制命令（单字节）

- **Payload 结构**（检测数据）：
  
  ```
  [对象数 1B] [对象1 6B] [对象2 6B] ...
  每个对象：[class_id 1B][conf 1B][cx 1B][cy 1B][w 1B][h 1B]
  ```

- **Payload 结构**（控制命令）：
  
  ```
  [命令 1B]  # 如 0xF0=open, 0x30=close
  ```

- **方法**：
  
  - `pack_detection(data) -> bytes` - 封装检测数据为二进制包
  - `pack_command(data) -> bytes` - 封装命令数据为二进制包
  - `parse_mcu_response(data) -> dict` - 解析 MCU 响应（当前返回 hex 字符串）
  - `validate_packet(packet) -> bool` - 验证数据包有效性

---

### 3. 控制器层 (controller/)

**职责**：编排数据流，连接各个模块，协调整体流程。

#### controller/pipeline.py

- **类**：`DataPipeline(QObject)`
- **职责**：数据流的核心编排器
- **功能**：
  - 初始化和管理所有模块（Camera、YOLOEngine、Quantizer、SerialPort）
  - 连接各模块的信号与槽
  - 编排完整数据流（相机 → 推理 → 量化 → 协议封装 → 串口）
  - 统计检测 FPS
  - 绘制检测框（`_draw_detections()`）
- **配置参数**（通过 `config` 字典传入）：
  - `camera_index` - 摄像头索引
  - `camera_fps` - 摄像头帧率
  - `detect_fps` - 检测帧率
  - `model_path` - YOLO 模型路径
  - `conf_threshold` - 置信度阈值
  - `serial_port` - 串口号
  - `baudrate` - 波特率
  - `bytesize` - 数据位
  - `parity` - 校验位
  - `stopbits` - 停止位
  - `quantizer_mode` - 量化模式（'bbox' 或 'command'）
- **信号**：
  - `sig_processed_frame(np.ndarray)` - 发送处理后的帧（带检测框）
  - `sig_detections(list)` - 发送检测结果
  - `sig_mcu_response(bytes)` - 转发 MCU 响应
  - `sig_camera_fps(float)` - 转发摄像头 FPS
  - `sig_detect_fps(float)` - 发送检测 FPS
  - `sig_error(str)` - 发送错误信息
- **方法**：
  - `start()` - 启动数据流
  - `stop()` - 停止数据流
  - `_on_frame(frame, frame_id)` - 相机帧回调（核心数据流处理）
  - `_draw_detections(frame, detections)` - 绘制检测框
  - `_on_mcu_data(data)` - MCU 数据回调
  - `update_detect_fps(fps)` - 更新检测帧率
  - `update_conf_threshold(threshold)` - 更新置信度阈值

---

### 4. 用户界面层 (ui/)

**职责**：提供图形化用户界面，接收用户输入，显示处理结果。

#### ui/styles.py

- **职责**：定义 QSS 样式
- **内容**：`DARK_THEME_QSS` - 深色主题样式字符串

#### ui/main_window.py

- **类**：`MainWindow(QMainWindow)`
- **职责**：主窗口界面
- **功能**：
  - 显示实时视频流（左侧，640x480）
  - 提供参数配置界面（右侧控制面板）
  - 显示状态信息（Camera FPS、Detect FPS）
  - 显示 MCU 回显数据（hex 格式）
  - 加载 YOLO 模型文件（`QFileDialog`）
- **UI 组件**：
  - 视频显示区（`QLabel`）
  - 按钮组：
    - "启动检测" - 创建 `DataPipeline` 并启动
    - "停止" - 停止 `DataPipeline`
    - "加载模型" - 选择模型文件
  - 参数配置组：
    - 串口号（`QComboBox`，自动扫描可用串口，含"刷新"按钮）
    - 波特率（`QComboBox`，默认 9600）
    - 数据位（`QComboBox`，默认 8）
    - 校验位（`QComboBox`，默认 None）
    - 停止位（`QComboBox`，默认 1）
    - 检测 FPS（`QSpinBox`，默认 10）
    - 量化模式（`QComboBox`，默认命令模式）
  - 状态信息组：
    - Camera FPS 显示
    - Detect FPS 显示
  - MCU 回显区（`QTextEdit`，只读，显示 hex 数据）
- **方法**：
  - `_on_start()` - 启动按钮点击事件
  - `_on_stop()` - 停止按钮点击事件
  - `_on_load_model()` - 加载模型按钮点击事件
  - `_update_video(frame)` - 更新视频显示
  - `_update_mcu_response(data)` - 显示 MCU 回显
  - `_on_error(msg)` - 错误信息显示

#### main.py

- **职责**：应用入口
- **功能**：
  - 创建 `QApplication`
  - 应用 QSS 样式（`DARK_THEME_QSS`）
  - 创建并显示主窗口（`MainWindow`）
  - 启动事件循环（`app.exec_()`)

---

## 核心数据流

### 主数据流（相机 → 检测 → 串口）

```
1. Camera 采集（30 fps）
   ↓ sig_frame_ready(frame, frame_id)
2. Pipeline._on_frame()
   ├→ YOLOEngine.should_infer() - 判断是否需要推理（基于 detect_fps）
   ├→ YOLOEngine.infer(frame) - 执行推理
   │   └→ 返回 Detection[]
   ├→ Quantizer.quantize(detections) - 量化
   │   └→ 返回 QuantizedData
   ├→ 根据量化模式选择封装方法：
   │   ├→ bbox 模式：Protocol.pack_detection(quantized) → bytes
   │   └→ command 模式：直接提取命令字节 → bytes
   ├→ SerialPort.write(bytes) - 发送到串口
   ├→ _draw_detections() - 绘制检测框
   └→ sig_processed_frame.emit() - 发送到 UI
       ↓
3. MainWindow._update_video() - 更新显示
```

### 串口接收数据流（MCU → UI）

```
1. SerialPort 接收数据（在独立线程中）
   ├→ 读取串口数据
   ├→ 按 \n 分包
   └→ sig_data_received(bytes)
       ↓
2. Pipeline._on_mcu_data()
   └→ sig_mcu_response.emit(bytes)
       ↓
3. MainWindow._update_mcu_response() - 显示 hex 数据
```

### FPS 统计数据流

```
# 摄像头 FPS
Camera 计算 FPS（每秒统计一次）
↓ sig_fps(float)
Pipeline 转发
↓ sig_camera_fps(float)
MainWindow 更新显示

# 检测 FPS
Pipeline 统计推理次数（每秒统计一次）
↓ sig_detect_fps(float)
MainWindow 更新显示
```

---

## 模块职责边界

### 职责分离原则

1. **硬件层**只负责硬件操作，不包含业务逻辑
   
   - `Camera` 不执行推理，只采集原始帧
   - `SerialPort` 不解析协议内容，只收发字节流

2. **业务层**不依赖 UI 和硬件细节
   
   - `YOLOEngine` 只做推理，不涉及采集和显示
   - `Quantizer` 只做数学运算，不依赖特定硬件
   - `Protocol` 只处理协议格式，不涉及串口操作

3. **控制器层**负责模块协调，不重复实现业务逻辑
   
   - `Pipeline` 编排数据流，但不直接实现推理、量化、协议封装

4. **UI 层**只负责显示和交互，不包含业务逻辑
   
   - `MainWindow` 接收 `Pipeline` 信号并更新显示
   - `MainWindow` 不直接调用 `Camera`、`YOLO` 等模块

### 数据类型边界

- **原始数据**：`np.ndarray`（图像帧）、`bytes`（串口数据）
- **业务数据**：`Detection`（检测结果）、`QuantizedData`（量化数据）
- **通信数据**：`bytes`（二进制协议包或单字节命令）

### 信号通信边界

- 跨线程通信使用 PyQt 信号（QThread 安全）
- 所有异步操作通过信号传递结果
- 不使用共享内存或全局变量传递数据

---

## 量化模式

项目支持两种量化模式，通过 UI 配置选择：

### 1. 命令模式（Command Mode）

- **量化器**：`CommandQuantizer`
- **输出**：单字节命令（如 `0xF0`, `0x30`）
- **映射规则**：
  - 检测到 "open" → `0xF0`
  - 检测到 "close" → `0x30`
  - 未检测到 → `0x00`
- **串口发送**：直接发送单字节命令，不封装协议包
- **适用场景**：简单的开关控制、状态切换

### 2. Bbox 模式（Bounding Box Mode）

- **量化器**：`SimpleQuantizer`
- **输出**：完整的检测数据包（类别、置信度、坐标）
- **量化策略**：
  - bbox 中心点坐标归一化到 0-255
  - bbox 宽高归一化到 0-255
  - confidence 映射到 0-100
- **串口发送**：封装为完整协议包（`AA 55 01 ...`）
- **适用场景**：需要精确位置信息的应用

### 3. 贝柱模式（Scallop Mode）

- **量化器**： `ScallopQuantizer`
- **输出**： 单字节命令（如`0x01`,`0x02`,`0x03`）
- **量化映射策略**：
  - bbox中点坐标获取
  - 中点坐标比较img_w:
    - 小于3/8img_w -> 0x01(right)
    - 大于5/8img_w -> 0x02(left)
    - 3/8~5/8img_w -> 0x03(stop)

---

## 训练工具与数据集

### 训练脚本（独立工具）

#### my_train.py

- **职责**：训练 YOLO 模型
- **功能**：
  - 加载预训练模型（`yolo11n.pt`）
  - 使用自定义数据集训练（`hands&fists/hands&fists/hd.yaml`）
  - 训练参数：
    - epochs: 100
    - imgsz: 640
    - batch: -1（自动）
    - cache: ram
    - workers: 1
- **输出**：
  - 训练后的模型保存在 `runs/` 目录
  - 最佳模型：`best.pt`
- **与主应用的关系**：独立工具，不是主应用架构的一部分

#### mypredit.py

- **职责**：模型预测脚本
- **与主应用的关系**：独立工具，用于测试模型

### 数据集目录

#### hands&fists/hands&fists/

- **结构**：
  
  ```
  hands&fists/hands&fists/
  ├── hd.yaml          # 数据集配置文件
  ├── images/          # 图像数据
  │   ├── train/       # 训练集
  │   ├── val/         # 验证集
  │   └── test/        # 测试集
  └── labels/          # 标注数据（YOLO 格式）
  ```

- **配置文件**（hd.yaml）：
  
  ```yaml
  path: E:/deeplearning/qt - 副本/hands&fists/hands&fists
  train: images/train
  val: images/val
  test: images/test
  
  names:
    - open
    - close
  ```

- **类别**：
  
  - 0: open
  - 1: close

- **与主应用的关系**：训练数据集，不是主应用运行时依赖

---

## 配置管理

### 运行时配置

配置通过 `DataPipeline.__init__()` 的 `config` 字典传入：

```python
config = {
    'camera_index': int,        # 摄像头索引
    'camera_fps': int,          # 摄像头目标帧率
    'detect_fps': float,        # 检测帧率
    'model_path': str,          # YOLO 模型路径
    'conf_threshold': float,    # 置信度阈值
    'serial_port': str,         # 串口号
    'baudrate': int,            # 波特率
    'bytesize': int,            # 数据位
    'parity': str,              # 校验位（'N', 'E', 'O'）
    'stopbits': float,          # 停止位
    'quantizer_mode': str       # 量化模式（'bbox' 或 'command'）
}
```

### 默认配置

- 串口：COM3
- 波特率：115200
- 数据位：8
- 校验位：None
- 停止位：1
- 检测 FPS：10
- 模型：yolo11n.pt
- 置信度阈值：0.45
- 量化模式：command

---

## 依赖关系图

```
main.py
  └→ ui/main_window.py
      └→ controller/pipeline.py
          ├→ hardware/camera.py
          ├→ hardware/serial_port.py
          ├→ business/yolo_engine.py
          │   └→ business/types.py
          ├→ business/quantizer.py
          │   └→ business/types.py
          └→ business/protocol.py
              └→ business/types.py
```

**说明**：

- `controller/pipeline.py` 是核心枢纽，依赖所有其他模块
- `business/types.py` 是基础数据类型，被业务层各模块依赖
- `hardware/` 层模块不依赖业务层和 UI 层
- `business/` 层模块不依赖硬件层和 UI 层
- `ui/` 层只依赖 `controller/` 层

---

## 技术选型说明

### 为什么使用 QThread

- **需求**：摄像头采集、串口收发需要在后台线程运行，避免阻塞 UI
- **选择**：PyQt5 的 QThread 提供线程安全的信号机制
- **优势**：信号/槽机制自动处理跨线程通信，无需手动加锁

### 为什么使用大端序

- **需求**：与 MCU 通信的协议格式
- **选择**：帧头和长度字段使用大端序（网络字节序）
- **实现**：`struct.pack('>H', ...)` 中的 `>` 表示大端序

### 为什么使用 `\n` 作为分包符

- **需求**：串口接收存在粘包问题
- **选择**：使用 `\n` (0x0A) 作为帧尾，便于分包
- **优势**：简单可靠，大多数串口工具支持换行符显示

---

## 当前实现状态

### 已实现功能

- ✅ 实时摄像头采集（可配置帧率）
- ✅ YOLO 目标检测（可配置推理频率）
- ✅ 检测结果量化（两种模式：bbox 和 command）
- ✅ 二进制协议封装（bbox 模式）
- ✅ 单字节命令发送（command 模式）
- ✅ 完整串口配置（波特率、数据位、校验位、停止位）
- ✅ 串口收发（异步、粘包处理）
- ✅ MCU 回显显示（hex 格式）
- ✅ FPS 统计（摄像头 FPS、检测 FPS）
- ✅ 实时视频显示（带检测框和标签）
- ✅ 模型训练工具（my_train.py）
- ✅ 自定义数据集（hands&fists）

### 当前限制

1. **协议解析未完整实现**：`Protocol.parse_mcu_response()` 目前只返回 hex 字符串，未实现完整的协议解析逻辑
2. **配置不持久化**：配置参数不保存到文件，每次启动需重新输入
3. **单摄像头支持**：只支持单个摄像头，摄像头索引在配置中指定
4. **无日志记录**：检测结果和串口数据不记录到文件
5. **错误处理简化**：错误信息只显示在 MCU 回显区，无独立错误日志

---

## 版本信息

- **版本**：MVP（Minimum Viable Product）
- **状态**：核心功能已实现并通过单元测试
- **原始版本**：`hello_qt.py`（670 行单文件，功能堆叠）
- **重构版本**：模块化架构，分层清晰，职责明确

---

## 文档变更记录

- 2026-03-12：更新架构文档，如实记录当前实现状态，包括训练工具和数据集
- 2026-03-26: 更新架构文档，记录新增内容：scallop量化器
- 2026-03-xx: 串口接收改为直接透传（无分包）；串口号控件改为 QComboBox + 刷新按钮；默认波特率改为 9600
