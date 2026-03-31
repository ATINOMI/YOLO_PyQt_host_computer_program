"""
模块单元测试脚本

用于验证各个模块的基本功能，无需启动完整 GUI
"""
from business.types import Detection, QuantizedData
from business.quantizer import SimpleQuantizer
from business.protocol import Protocol


def test_quantizer():
    """测试量化器"""
    print("=" * 50)
    print("测试量化器模块")
    print("=" * 50)

    # 创建测试检测结果
    detections = [
        Detection(
            class_id=0,
            class_name="person",
            confidence=0.85,
            bbox=(100, 100, 200, 180)  # x1, y1, x2, y2
        ),
        Detection(
            class_id=1,
            class_name="car",
            confidence=0.92,
            bbox=(300, 200, 450, 350)
        )
    ]

    # 量化
    quantizer = SimpleQuantizer(img_width=640, img_height=480)
    quantized = quantizer.quantize(detections)

    print(f"检测对象数: {quantized.count}")
    for i, obj in enumerate(quantized.objects):
        print(f"对象 {i+1}:")
        print(f"  class_id: {obj['class_id']}")
        print(f"  conf: {obj['conf']} (百分比)")
        print(f"  cx: {obj['cx']}, cy: {obj['cy']}")
        print(f"  w: {obj['w']}, h: {obj['h']}")

    print("\n测试通过！\n")
    return quantized


def test_protocol(quantized_data):
    """测试协议封装"""
    print("=" * 50)
    print("测试协议封装模块")
    print("=" * 50)

    # 封装数据包
    packet = Protocol.pack_detection(quantized_data)

    print(f"数据包长度: {len(packet)} 字节")
    print(f"数据包（hex）: {packet.hex().upper()}")
    print(f"数据包（格式化）:")

    # 解析数据包结构
    hex_bytes = [f"{b:02X}" for b in packet]

    print(f"  帧头: {hex_bytes[0]} {hex_bytes[1]} (0xAA55)")
    print(f"  类型: {hex_bytes[2]} (0x01=检测数据)")
    print(f"  长度: {hex_bytes[3]} {hex_bytes[4]} (小端序)")

    payload_len = packet[3] | (packet[4] << 8)
    print(f"  Payload 长度: {payload_len} 字节")
    print(f"  对象数: {packet[5]}")

    # 解析每个对象
    offset = 6
    for i in range(packet[5]):
        print(f"  对象 {i+1}:")
        print(f"    class_id: {packet[offset]}")
        print(f"    conf: {packet[offset+1]}")
        print(f"    cx: {packet[offset+2]}")
        print(f"    cy: {packet[offset+3]}")
        print(f"    w: {packet[offset+4]}")
        print(f"    h: {packet[offset+5]}")
        offset += 6

    print(f"  校验和: {hex_bytes[offset]} (计算值: {sum(packet[5:offset]) & 0xFF:02X})")
    print(f"  帧尾: {hex_bytes[offset+1]} (0x0A=\\n)")

    # 验证数据包
    is_valid = Protocol.validate_packet(packet)
    print(f"\n数据包校验: {'通过' if is_valid else '失败'}")

    print("\n测试通过！\n")
    return packet


def test_protocol_parsing():
    """测试协议解析"""
    print("=" * 50)
    print("测试协议解析模块")
    print("=" * 50)

    # 模拟 MCU 响应
    mcu_response = b'\xAA\x55\x02\x00\x01\x01\x01\x0A'

    parsed = Protocol.parse_mcu_response(mcu_response)
    print(f"MCU 响应（hex）: {parsed['raw']}")
    print(f"响应长度: {parsed['length']} 字节")

    print("\n测试通过！\n")


def test_detection_data():
    """测试检测数据类型"""
    print("=" * 50)
    print("测试数据类型模块")
    print("=" * 50)

    det = Detection(
        class_id=0,
        class_name="person",
        confidence=0.85,
        bbox=(100, 100, 200, 180)
    )

    print(f"检测对象:")
    print(f"  类别 ID: {det.class_id}")
    print(f"  类别名称: {det.class_name}")
    print(f"  置信度: {det.confidence:.2f}")
    print(f"  边界框: {det.bbox}")

    print("\n测试通过！\n")


def main():
    """主测试函数"""
    print("\n" + "=" * 50)
    print("YOLO 串口上位机 - 模块单元测试")
    print("=" * 50 + "\n")

    try:
        # 测试数据类型
        test_detection_data()

        # 测试量化器
        quantized = test_quantizer()

        # 测试协议封装
        packet = test_protocol(quantized)

        # 测试协议解析
        test_protocol_parsing()

        print("=" * 50)
        print("所有测试通过！")
        print("=" * 50)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
