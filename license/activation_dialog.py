"""激活界面（PySide6）。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from license import activate
from license.machine_code import get_machine_code
from license.verify import LicenseStatus

_STATUS_MESSAGES = {
    LicenseStatus.NOT_ACTIVATED: "需要激活：请把下面的机器码发给卖家，获取激活码后粘贴到输入框。",
    LicenseStatus.MACHINE_MISMATCH: "当前授权与本机不匹配（软件可能被复制到了其他电脑）。请联系卖家重新激活。",
    LicenseStatus.EXPIRED: "授权已过期，请联系卖家续期。",
    LicenseStatus.INVALID: "授权文件损坏或无效，请重新激活。",
}

SELLER_QQ = "1016499728"


class ActivationDialog(QDialog):
    def __init__(self, status: str = LicenseStatus.NOT_ACTIVATED, parent=None):
        super().__init__(parent)
        self.setWindowTitle("软件激活")
        self.setMinimumWidth(480)
        self.setModal(True)

        machine_code = get_machine_code()

        tip_label = QLabel(
            _STATUS_MESSAGES.get(
                status, _STATUS_MESSAGES[LicenseStatus.NOT_ACTIVATED]
            )
        )
        tip_label.setWordWrap(True)

        seller_label = QLabel(f"如有问题请联系卖家QQ：{SELLER_QQ}")
        seller_label.setWordWrap(True)
        seller_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        machine_label = QLabel("本机机器码：")
        self.machine_edit = QLineEdit(machine_code)
        self.machine_edit.setReadOnly(True)
        copy_btn = QPushButton("复制")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(machine_code)
        )

        machine_row = QHBoxLayout()
        machine_row.addWidget(machine_label)
        machine_row.addWidget(self.machine_edit, 1)
        machine_row.addWidget(copy_btn)

        code_label = QLabel("激活码：")
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("请粘贴卖家给你的激活码")

        self.activate_btn = QPushButton("激活")
        self.activate_btn.setDefault(True)
        self.quit_btn = QPushButton("退出")
        self.quit_btn.clicked.connect(self.reject)
        self.activate_btn.clicked.connect(self._on_activate)
        self.code_edit.returnPressed.connect(self._on_activate)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.quit_btn)
        buttons.addWidget(self.activate_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.addWidget(tip_label)
        layout.addWidget(seller_label)
        layout.addSpacing(4)
        layout.addLayout(machine_row)
        layout.addWidget(code_label)
        layout.addWidget(self.code_edit)
        layout.addLayout(buttons)

    def _on_activate(self) -> None:
        ok, message = activate(self.code_edit.text())
        if ok:
            QMessageBox.information(self, "激活成功", message)
            self.accept()
        else:
            QMessageBox.warning(self, "激活失败", message)


def show_activation_dialog(
    status: str = LicenseStatus.NOT_ACTIVATED, parent=None
) -> bool:
    """弹出激活窗口，返回是否激活成功。"""
    dialog = ActivationDialog(status, parent)
    return dialog.exec() == QDialog.Accepted
