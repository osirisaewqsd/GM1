# utils/toast.py
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QLabel, QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit
)
from PySide6.QtGui import QTextCursor

class Toast(QLabel):
    def __init__(self, text, parent=None, duration=1500):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("""
            QLabel {
                background: rgba(160, 70, 50, 255);
                color: #ffffff;
                border: 1px solid rgba(210, 180, 140, 0.6);
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 10pt;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                box-shadow: 0px 4px 20px rgba(0, 0, 0, 0.5);
            }
        """)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.raise_()

        # 宽度控制
        if parent:
            # 最小宽度：父窗口宽度的 80%，但至少 270px
            min_width = max(270, int(parent.width() * 0.8))
            max_width = int(parent.width() * 1.2)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            min_width = max(270, int(screen.width() * 0.8))
            max_width = int(screen.width() * 1.2)

        self.setMinimumWidth(min_width)
        self.setMaximumWidth(max_width)

        self.adjustSize()
        offset = 90

        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2 - offset
            if y < 0:
                y = 0
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            center = screen.center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2 - offset)

        self.show()
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(300)
        self.opacity_anim.setStartValue(1.0)
        self.opacity_anim.setEndValue(0.0)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start_fade_out)
        self.timer.start(duration)

    def start_fade_out(self):
        self.opacity_anim.finished.connect(self.close)
        self.opacity_anim.start()

    @staticmethod
    def show_message(text, parent=None, duration=1500):
        Toast(text, parent, duration)


class CustomQuestionDialog(QDialog):
    """自定义删除对话框（取消在左，确认在右）"""
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)
        if parent:
            parent_width = parent.width()
            self.setMaximumWidth(int(parent_width * 0.85))
        else:
            self.setMaximumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background: #2b2b2b;
                border: none;
                border-radius: 12px;
            }
            QLabel {
                color: #d0d0d0;
                font-size: 10pt;
                padding: 8px 2px;
            }
            QPushButton {
                background: #4a4a4a;
                border: 1px solid #5a5a5a;
                border-radius: 6px;
                padding: 6px 20px;
                color: #d0d0d0;
                font-size: 9pt;
                min-width: 80px;
                min-height: 26px;
            }
            QPushButton:hover {
                background: #5a5a5a;
                border-color: #7a7a7a;
            }
            QPushButton#confirmButton {
                background: #c0392b;
                color: white;
                border-color: #e74c3c;
            }
            QPushButton#confirmButton:hover {
                background: #e74c3c;
                border-color: #ff6b5a;
            }
            QPushButton#confirmButton:pressed {
                background: #962d22;
                border-color: #c0392b;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(5, 16, 5, 16)
        label = QLabel(text)
        label.setFixedHeight(100)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        self.confirm_btn = QPushButton("确认删除")
        self.confirm_btn.setObjectName("confirmButton")
        self.confirm_btn.setDefault(True)
        self.confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.confirm_btn)
        layout.addLayout(btn_layout)
        self.adjustSize()
        offset = 50
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2 - offset
            if y < 0:
                y = 0
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            center = screen.center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2 - offset)

    def exec(self):
        return super().exec()


class CustomInputDialog(QDialog):
    """自定义重命名对话框（取消在左，确认在右），支持多行输入"""
    def __init__(self, title, label_text, default_text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)
        if parent:
            parent_width = parent.width()
            self.setMaximumWidth(int(parent_width * 0.85))
        else:
            self.setMaximumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background: #2b2b2b;
                border: none;
                border-radius: 12px;
            }
            QLabel {
                color: #d0d0d0;
                font-size: 10pt;
                padding: 6px 2px;
            }
            QTextEdit {
                background: #3b3b3b;
                color: #d0d0d0;
                border: 1px solid #5a5a5a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 10pt;
                min-height: 30px;
                max-height: 100px;
            }
            QTextEdit:focus {
                border-color: #4b6eb9;
            }
            QPushButton {
                background: #4a4a4a;
                border: 1px solid #5a5a5a;
                border-radius: 6px;
                padding: 6px 20px;
                color: #d0d0d0;
                font-size: 9pt;
                min-width: 80px;
                min-height: 26px;
            }
            QPushButton:hover {
                background: #5a5a5a;
                border-color: #7a7a7a;
            }
            QPushButton#confirmButton {
                background: #2a7a2a;
                color: white;
                border-color: #3a9a3a;
            }
            QPushButton#confirmButton:hover {
                background: #3a9a3a;
            }
            QPushButton#confirmButton:pressed {
                background: #1a5a1a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(5, 12, 5, 12)
        label = QLabel(label_text)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(default_text)
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.text_edit)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setObjectName("confirmButton")
        self.confirm_btn.setDefault(True)
        self.confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.confirm_btn)
        layout.addLayout(btn_layout)
        self.adjustSize()
        offset = 50
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2 - offset
            if y < 0:
                y = 0
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            center = screen.center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2 - offset)

    def get_text(self):
        return self.text_edit.toPlainText()

    def exec(self):
        return super().exec()