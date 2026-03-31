"""
二进制协议封装模块

协议格式（小端序）：
[帧头 2B] [类型 1B] [长度 2B] [Payload] [校验和 1B] [帧尾 1B]
 0xAA55     0x01/02  N bytes    数据      Sum&0xFF    0x0A

类型：
- 0x01: 检测数据（bbox 详细信息）
- 0x02: 控制命令（单字节指令）

Payload 结构（检测数据，类型 0x01）：
[对象数 1B] [对象1 6B] [对象2 6B] ...
每个对象：[class_id 1B][conf 1B][cx 1B][cy 1B][w 1B][h 1B]

Payload 结构（控制命令，类型 0x02）：
[命令 1B]  # 如 0xF0=open, 0x30=close

示例（检测数据）：
AA 55 01 00 0D 02 00 50 64 64 20 18 01 5A 80 78 32 1E C8 0A

示例（控制命令，open=0xF0）：
AA 55 02 00 01 F0 F0 0A
│  │  │  │  │  │  │  └─ 帧尾 (\n)
│  │  │  │  │  │  └──── 校验和 (0xF0)
│  │  │  │  │  └─────── 命令 (0xF0)
│  │  │  │  └────────── 长度 (0x0001)
│  │  │  └───────────── 类型 (0x02=命令)
│  │  └──────────────── 帧头高字节
│  └─────────────────── 帧头低字节
"""
import struct
from business.types import QuantizedData


class Protocol:
    """二进制协议处理"""

    FRAME_HEADER = 0xAA55
    FRAME_TYPE_DETECTION = 0x01  # 检测数据（详细 bbox）
    FRAME_TYPE_COMMAND = 0x02    # 控制命令（单字节）
    FRAME_TAIL = 0x0A  # '\n'

    @staticmethod
    def pack_command(data: QuantizedData) -> bytes:
        """
        将命令数据封装为二进制包（简化格式）

        Args:
            data: 量化后的命令数据（objects 中包含 'command' 字段）

        Returns:
            二进制数据包

        示例：
            open (0xF0) -> AA 55 02 00 01 F0 F0 0A
            close (0x30) -> AA 55 02 00 01 30 30 0A
        """
        # 提取命令字节
        if data.objects and 'command' in data.objects[0]:
            command = data.objects[0]['command'] & 0xFF
        else:
            command = 0x00  # 默认命令

        # Payload: 单字节命令
        payload = bytearray([command])

        # 计算长度和校验和
        length = len(payload)
        checksum = sum(payload) & 0xFF

        # 组装完整帧（帧头按字节顺序，长度使用大端序）
        packet = bytearray()
        packet.extend([0xAA, 0x55])  # 帧头（按字节顺序）
        packet.append(Protocol.FRAME_TYPE_COMMAND)  # 类型
        packet.extend(struct.pack('>H', length))  # 长度（大端序/网络字节序）
        packet += bytes(payload)
        packet += bytes([checksum, Protocol.FRAME_TAIL])

        return bytes(packet)

    @staticmethod
    def pack_detection(data: QuantizedData) -> bytes:
        """
        将量化数据封装为二进制包

        Args:
            data: 量化后的检测数据

        Returns:
            二进制数据包
        """
        # Payload: [count 1B] + [obj1 6B] + [obj2 6B] + ...
        payload = bytearray([data.count])

        for obj in data.objects:
            payload.extend([
                obj['class_id'] & 0xFF,
                obj['conf'] & 0xFF,
                obj['cx'] & 0xFF,
                obj['cy'] & 0xFF,
                obj['w'] & 0xFF,
                obj['h'] & 0xFF
            ])

        # 计算长度和校验和
        length = len(payload)
        checksum = sum(payload) & 0xFF

        # 组装完整帧（帧头按字节顺序，长度使用大端序）
        packet = bytearray()
        packet.extend([0xAA, 0x55])  # 帧头（按字节顺序）
        packet.append(Protocol.FRAME_TYPE_DETECTION)  # 类型
        packet.extend(struct.pack('>H', length))  # 长度（大端序/网络字节序）
        packet += bytes(payload)
        packet += bytes([checksum, Protocol.FRAME_TAIL])

        return bytes(packet)

    @staticmethod
    def parse_mcu_response(data: bytes) -> dict:
        """
        解析 MCU 响应数据

        Args:
            data: MCU 返回的原始字节

        Returns:
            解析结果字典

        Note:
            MVP 版本暂不实现完整解析，直接返回 hex 字符串
        """
        return {
            'raw': data.hex(),
            'length': len(data)
        }

    @staticmethod
    def validate_packet(packet: bytes) -> bool:
        """
        验证数据包的有效性

        Args:
            packet: 完整的数据包

        Returns:
            True if valid, False otherwise
        """
        if len(packet) < 7:  # 最小包长度：2+1+2+0+1+1=7
            return False

        # 检查帧头（按字节顺序检查）
        if packet[0] != 0xAA or packet[1] != 0x55:
            return False

        # 检查帧尾
        if packet[-1] != Protocol.FRAME_TAIL:
            return False

        # 验证校验和（长度使用大端序）
        length = struct.unpack('>H', packet[3:5])[0]
        payload = packet[5:5+length]
        expected_checksum = sum(payload) & 0xFF
        actual_checksum = packet[5+length]

        return expected_checksum == actual_checksum
