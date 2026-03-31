# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a YOLO-based vision detection upper computer application that performs real-time object detection from camera feed, quantizes results, and transmits them to an MCU via serial port using a custom binary protocol. Built with PyQt5, OpenCV, and Ultralytics YOLO.

## Essential Commands

### Setup and Running
```bash
# Install dependencies
pip install PyQt5 opencv-python ultralytics pyserial numpy

# Run the application
python main.py

# Run unit tests
python test_modules.py
```

### Testing Phases
The project uses a 4-phase testing approach (see TESTING.md):
1. Camera → UI (no inference)
2. Camera → YOLO → UI (inference without serial)
3. Full pipeline with serial loopback
4. Real MCU integration

## Architecture

### Layer Structure
The codebase follows a strict 4-layer architecture with clear separation of concerns:

```
hardware/       # Hardware abstraction (camera, serial port)
  ├── camera.py           # Camera capture (QThread)
  └── serial_port.py      # Serial I/O with packet framing

business/       # Core business logic (no hardware/UI dependencies)
  ├── types.py            # Data classes (Detection, QuantizedData, Packet)
  ├── yolo_engine.py      # YOLO inference with FPS control
  ├── quantizer.py        # Bbox normalization to 0-255
  └── protocol.py         # Binary protocol packing/parsing

controller/     # Data flow orchestration
  └── pipeline.py         # Connects all modules, manages data flow

ui/             # User interface
  ├── main_window.py      # Main GUI window
  └── styles.py           # QSS dark theme
```

### Critical Data Flow
```
Camera (30 fps) → Pipeline._on_frame() → YOLOEngine.should_infer() check
                                      ↓ (if detect_fps interval met)
                                      YOLOEngine.infer()
                                      ↓
                                      Quantizer.quantize()
                                      ↓
                                      Protocol.pack_detection()
                                      ↓
                                      SerialPort.write()
```

### Key Design Principles

1. **FPS Decoupling**: Camera FPS (e.g., 30) is separate from detection FPS (e.g., 10). YOLOEngine.should_infer() controls inference frequency.

2. **Thread Safety**: Camera and SerialPort run as QThreads. All cross-thread communication uses PyQt signals (never shared state).

3. **Layer Boundaries**:
   - Hardware layer: No business logic, only device I/O
   - Business layer: Pure functions, no hardware/UI dependencies
   - Controller: Orchestrates only, doesn't duplicate business logic
   - UI: Display and input only, delegates to controller

4. **Binary Protocol** (little-endian):
   ```
   [Header 0xAA55][Type 0x01][Length 2B][Payload][Checksum][Footer 0x0A]
   Payload: [Count 1B][Obj1 6B][Obj2 6B]...
   Object: [class_id][conf][cx][cy][w][h] (all 1 byte, normalized to 0-255)
   ```

## Important Implementation Details

### When Modifying Detection Logic
- Check `YOLOEngine.should_infer()` before inference to respect `detect_fps` setting
- Update quantizer image size when frame dimensions change: `quantizer.update_image_size()`
- Detection FPS is measured in `Pipeline._on_frame()`, not in YOLOEngine

### When Modifying Serial Communication
- All packets must end with `\n` (0x0A) for proper framing
- SerialPort uses a queue for async writes (`self.write_queue`)
- Received data is split on `\n` to handle packet boundaries
- Use little-endian byte order (`struct.pack('<HBH', ...)`) for MCU compatibility

### When Adding New Features
- Respect layer boundaries: hardware modules should not import from business layer
- Use signals for async communication, never direct method calls across threads
- Add new data types to `business/types.py` as dataclasses
- Configuration is passed via dict to `DataPipeline.__init__(config)`

### Protocol Debugging
Enable hex display in UI to verify packet format:
- Header should be `AA 55`
- Length is little-endian (e.g., `07 00` = 7 bytes)
- Checksum is `sum(payload_bytes) & 0xFF`
- Footer is always `0A`

## Known Limitations (MVP)
- `Protocol.parse_mcu_response()` currently only returns hex string, not full parsing
- Configuration is not persisted between sessions
- Single camera only (index hardcoded in config)
- No file logging for detections or serial data
- Error messages only shown in MCU echo area

## Default Configuration
- Serial: COM3, 115200 baud, 8N1
- Detection FPS: 10
- Model: yolo11n.pt
- Confidence threshold: 0.25

## Additional Context
- Original 670-line monolithic file was `hello_qt.py`
- Current modular structure enables easier testing and maintenance
- See ARCHITECTURE.md for detailed module responsibilities
- See TESTING.md for step-by-step validation procedures
