# 故障修理与更新记录

## BUG-001 MCU 回显区无数据显示

**日期**：2026-03-xx  
**文件**：`hardware/serial_port.py`

### 故障原因

`SerialPort.run()` 的接收逻辑以 `\n`（0x0A）为分包符，数据必须包含 `\n` 才会触发 `sig_data_received` 信号。MCU 回传的是纯回显字节（如 `0x33`），没有 `\n` 结尾，导致数据一直积压在 `_rx_buffer` 中，永远不触发信号，UI 回显区空白。

### 修复方法

删除基于 `\n` 的分包逻辑，改为收到数据直接 emit。

```python
# 修复前
self._rx_buffer.extend(chunk)
while b'\n' in self._rx_buffer:
    idx = self._rx_buffer.index(b'\n')
    packet = bytes(self._rx_buffer[:idx])
    self._rx_buffer = self._rx_buffer[idx+1:]
    if packet:
        self.sig_data_received.emit(packet)

# 修复后
if chunk:
    self.sig_data_received.emit(chunk)
```

同时删除 `__init__` 中的 `self._rx_buffer = bytearray()` 和 `import time`（不再使用）。

### 注意事项

若后续 MCU 固件改为发送结构化协议帧，需要重新添加分包逻辑。分包方式根据帧格式选择：
- 固定长度帧 → 按固定字节数切割
- 带帧头的变长帧（如 `AA 55` 开头）→ 按帧头定位切割
- 带换行符的文本帧 → 恢复原 `\n` 分包逻辑

---

## UPD-001 串口号改为下拉列表 + 自动扫描

**日期**：2026-03-xx  
**文件**：`ui/main_window.py`

### 更新原因

原来串口号是 `QLineEdit`，需要手动输入，且没有提示当前可用的串口，使用不便。

### 更新内容

1. `input_serial_port` 从 `QLineEdit` 改为 `QComboBox`
2. 新增 `btn_refresh_ports`（"刷新"按钮，宽度固定 48px），与下拉列表并排显示
3. 新增 `_refresh_ports()` 方法：调用 `SerialPort.list_ports()` 扫描可用串口，填充下拉列表，显示格式为 `COM3 - USB Serial Device`，`userData` 存储纯设备名
4. 新增 `_current_port()` 方法：从下拉列表取当前选中的设备名
5. 窗口初始化时自动调用一次 `_refresh_ports()`
6. 刷新时保留之前选中的串口（如果还存在）

### 修改方法（如需手动合并）

在 `__init__` 中：
```python
# 替换
self.input_serial_port = QLineEdit("COM3")
# 为
self.input_serial_port = QComboBox()
self.btn_refresh_ports = QPushButton("刷新")
self.btn_refresh_ports.setFixedWidth(48)
```

在 `_init_ui` 的参数配置区，替换串口号那一行：
```python
# 替换
param_layout.addRow("串口号:", self.input_serial_port)
# 为
port_row = QHBoxLayout()
port_row.addWidget(self.input_serial_port)
port_row.addWidget(self.btn_refresh_ports)
port_row.setContentsMargins(0, 0, 0, 0)
port_widget = QWidget()
port_widget.setLayout(port_row)
param_layout.addRow("串口号:", port_widget)
```

在 `_connect_signals` 中新增：
```python
self.btn_refresh_ports.clicked.connect(self._refresh_ports)
```

在 `_on_start` 中，`config['serial_port']` 从：
```python
self.input_serial_port.text()
# 改为
self._current_port()
```

imports 中新增：
```python
from hardware.serial_port import SerialPort
```

---

## UPD-002 默认波特率改为 9600

**日期**：2026-03-xx  
**文件**：`ui/main_window.py`

### 更新原因

项目实际使用波特率为 9600，原默认值 115200 每次启动都需要手动修改。

### 修改方法

```python
# 修改前
self.input_baudrate.setCurrentText('115200')
# 修改后
self.input_baudrate.setCurrentText('9600')
```

---

## 后续调试指引

### 串口收发问题排查顺序

1. 用串口助手（HEX 模式）确认 MCU 是否有数据发出
2. 确认 MCU 数据末尾字节格式（有无 `\n` / 固定长度 / 帧头）
3. 根据格式选择 `serial_port.py` 中的分包策略（见 BUG-001 注意事项）
4. 信号链：`SerialPort.sig_data_received` → `Pipeline._on_mcu_data()` → `Pipeline.sig_mcu_response` → `MainWindow._update_mcu_response()`，逐段排查

### 新增量化模式

在 `business/quantizer.py` 新增量化器类后，需同步修改以下位置：

1. `controller/pipeline.py` — `__init__` 中的 `elif` 分支，实例化新量化器
2. `ui/main_window.py` — `input_quantizer_mode` 的 `addItems` 列表
3. `ui/main_window.py` — `_on_start()` 中的 `index` 判断分支，映射到新模式字符串
4. 本文档 — 新增一条 UPD 记录
