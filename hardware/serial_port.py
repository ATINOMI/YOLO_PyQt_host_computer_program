"""
串口收发模块（完整的收发 + 参数配置）
"""
import queue
import time
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, pyqtSignal


class SerialPort(QThread):
    """串口收发线程"""

    sig_data_received = pyqtSignal(bytes)
    sig_port_opened = pyqtSignal(str)
    sig_port_closed = pyqtSignal()
    sig_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.ser = None
        self._running = False
        self._tx_queue = queue.Queue()
        self._rx_buffer = bytearray()

        # 配置参数
        self.port = 'COM3'
        self.baudrate = 115200
        self.bytesize = serial.EIGHTBITS
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE

    def configure(self, port: str, baudrate: int,
                  bytesize: int = 8, parity: str = 'N', stopbits: float = 1.0):
        """
        配置串口参数

        Args:
            port: 串口号（如 'COM3' 或 '/dev/ttyUSB0'）
            baudrate: 波特率
            bytesize: 数据位（5/6/7/8）
            parity: 校验位（'N'=None, 'E'=Even, 'O'=Odd）
            stopbits: 停止位（1/1.5/2）
        """
        self.port = port
        self.baudrate = baudrate

        # 映射数据位
        bytesize_map = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS
        }
        self.bytesize = bytesize_map.get(bytesize, serial.EIGHTBITS)

        # 映射校验位
        parity_map = {
            'N': serial.PARITY_NONE,
            'E': serial.PARITY_EVEN,
            'O': serial.PARITY_ODD,
            'M': serial.PARITY_MARK,
            'S': serial.PARITY_SPACE
        }
        self.parity = parity_map.get(parity.upper(), serial.PARITY_NONE)

        # 映射停止位
        stopbits_map = {
            1: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO
        }
        self.stopbits = stopbits_map.get(stopbits, serial.STOPBITS_ONE)

    def open_port(self) -> bool:
        """
        打开串口

        Returns:
            True if successful, False otherwise
        """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=0.5
            )
            self._running = True
            self.start()  # 启动接收线程
            self.sig_port_opened.emit(f"{self.port}@{self.baudrate}")
            return True
        except Exception as e:
            self.sig_error.emit(f"打开串口失败: {e}")
            return False

    def close_port(self):
        """关闭串口"""
        self._running = False
        self.wait()  # 等待线程结束
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.sig_port_closed.emit()

    def write(self, data: bytes):
        """
        异步发送数据（放入队列）

        Args:
            data: 要发送的字节数据
        """
        self._tx_queue.put(data)

    def run(self):
        """接收线程主循环"""
        while self._running:
            # 处理发送队列
            try:
                data = self._tx_queue.get_nowait()
                if self.ser and self.ser.is_open:
                    self.ser.write(data)
            except queue.Empty:
                pass
            except Exception as e:
                self.sig_error.emit(f"发送失败: {e}")

            # 处理接收（粘包处理：以 \n 分包）
            if self.ser and self.ser.is_open:
                try:
                    if self.ser.in_waiting > 0:
                        chunk = self.ser.read(self.ser.in_waiting)
                        self._rx_buffer.extend(chunk)

                        # 分包处理
                        while b'\n' in self._rx_buffer:
                            idx = self._rx_buffer.index(b'\n')
                            packet = bytes(self._rx_buffer[:idx])
                            self._rx_buffer = self._rx_buffer[idx+1:]
                            if packet:  # 忽略空包
                                self.sig_data_received.emit(packet)
                except Exception as e:
                    self.sig_error.emit(f"接收失败: {e}")

            # 防止 CPU 占用过高
            self.msleep(10)

    @staticmethod
    def list_ports():
        """
        列出可用串口

        Returns:
            串口列表 [(port_name, description), ...]
        """
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]

    def is_open(self) -> bool:
        """检查串口是否打开"""
        return self.ser is not None and self.ser.is_open
