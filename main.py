"""
YOLO 串口上位机 MVP 重构版本

入口程序
"""
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.styles import DARK_THEME_QSS


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME_QSS)

    window = MainWindow()
    window.setWindowTitle("YOLO 串口上位机 MVP")
    window.resize(1400, 800)
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
