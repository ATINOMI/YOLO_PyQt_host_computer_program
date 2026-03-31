"""
UI 样式定义（QSS）
"""

DARK_THEME_QSS = """
QMainWindow { background-color: #1e1e1e; }
QLabel { color: #e0e0e0; font-family: "Microsoft YaHei"; font-size: 13px; }
QLabel#TitleLabel { font-size: 20px; font-weight: bold; color: #00aaff; padding: 5px; }
QFrame#VideoFrame { background-color: #2d2d2d; border: 1px solid #3e3e3e; border-radius: 10px; }
QLabel#VideoLabel { background-color: #000; border: 1px solid #444; border-radius: 5px; color: #666; }
QFrame#ControlPanel { background-color: #252526; border-left: 1px solid #3e3e3e; min-width: 340px; }
QGroupBox { color: #00aaff; font-weight: bold; border: 1px solid #3e3e3e; border-radius: 6px; margin-top: 8px; padding-top: 12px; font-size: 12px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 3px; }
QPushButton { background-color: #3e3e42; color: white; border: none; border-radius: 4px; padding: 6px; font-weight: bold; font-size: 12px; }
QPushButton:hover { background-color: #505055; }
QPushButton#BtnStart { background-color: #0e639c; }
QPushButton#BtnStop { background-color: #c53030; }
QTextEdit { background-color: #151515; border: 1px solid #3e3e3e; border-radius: 4px; color: #00ff00; font-family: "Consolas"; font-size: 11px; padding: 4px; }
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
    background-color: #333; color: #eee; border: 1px solid #555; border-radius: 3px; padding: 2px;
}
"""
