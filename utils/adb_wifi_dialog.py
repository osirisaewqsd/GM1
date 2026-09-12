# utils/adb_wifi_dialog.py
"""
ADB 无线调试连接助手

提供两种连接方式：
1. 扫码连接（Android 11+，默认）：电脑生成二维码，手机扫码后自动配对并连接；
2. USB 无线连接：保留原有方式，先通过 USB 执行 adb tcpip，再走 Wi-Fi 连接。

所有 ADB 命令都在后台 QThread 中执行，避免阻塞 GUI 线程。
"""

import re
import time
import secrets
from threading import Event

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QTabWidget, QWidget
)
from PySide6.QtGui import QGuiApplication, QImage, QPixmap, QColor

from utils.resource import get_adb_path
from utils.adb_touch import run_adb, start_adb_server
from utils.qrcodegen import QrCode


class _AdbTask(QThread):
    """在后台线程中执行一段 ADB 流程，结果通过信号回主线程。"""

    sig_log = Signal(str)
    sig_state = Signal(str)
    sig_busy = Signal(bool)

    def __init__(self, parent, fn):
        super().__init__(parent)
        self._fn = fn
        self._stop_event = Event()

    def log(self, text):
        self.sig_log.emit(text)

    def request_stop(self):
        self._stop_event.set()

    def is_stop_requested(self):
        return self._stop_event.is_set()

    def run(self):
        try:
            self._fn(self)
        except Exception as e:
            self.sig_log.emit(f"❌ 异常: {e}")
        finally:
            self.sig_busy.emit(False)


class AdbWifiDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ADB 无线调试")
        self.setFixedSize(560, 700)
        self.setModal(True)

        self._task = None
        self._active_mode = None

        # USB 无线连接状态
        self._connected = False
        self._wifi_ip = None
        self._is_running = False

        # 扫码连接状态
        self._qr_connected = False
        self._qr_endpoint = None
        self._qr_service = None
        self._qr_password = None
        self._qr_payload = None

        self._setup_ui()
        self._connect_signals()

        self.tabs.setCurrentIndex(0)
        self._generate_qr()
        self._set_qr_checking_state()
        self._log_qr("正在检测 ADB 连接...")

        QTimer.singleShot(0, self._start_qr_init)

        self._position_next_to_parent()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._auto_refresh_status)
        self._status_timer.start(3000)

    def _auto_refresh_status(self):
        if not self.isVisible() or self._is_running:
            return
        if self.tabs.currentIndex() == 0:
            self._start_task(self._qr_refresh_status_flow, "qr")
        else:
            self._start_task(self._usb_refresh_status_flow, "usb")

    def _position_next_to_parent(self):
        if not self.parent():
            return
        parent_geo = self.parent().geometry()
        x = parent_geo.x() + parent_geo.width() + 10
        y = parent_geo.y()
        screen_geo = QGuiApplication.primaryScreen().availableGeometry()
        if x + self.width() > screen_geo.width():
            x = parent_geo.x() - self.width() - 10
        if x < 0:
            x = 10
        if y + self.height() > screen_geo.height():
            y = screen_geo.height() - self.height()
        if y < 0:
            y = 10
        self.move(x, y)

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #2b2b2b;
                border-radius: 6px;
            }
            QLabel {
                color: #a9b7c6;
                font-size: 10pt;
            }
            QPushButton {
                background: #3b3b3b;
                border: 1px solid #4a4a4a;
                border-radius: 3px;
                padding: 6px 16px;
                color: #a9b7c6;
                font-size: 10pt;
                min-height: 32px;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #4b4b4b;
            }
            QPushButton:pressed {
                background: #2b2b2b;
            }
            QPushButton:disabled {
                background: #2b2b2b;
                color: #555;
                border-color: #3a3a3a;
            }
            QPushButton#btn_start {
                background: #1a6a3a;
                color: #66dd88;
                border: none;
                font-weight: bold;
            }
            QPushButton#btn_start:hover {
                background: #2a7a4a;
            }
            QPushButton#btn_start:disabled {
                background: #3b3b3b;
                color: #666;
                border: 1px solid #4a4a4a;
                font-weight: normal;
            }
            QPushButton#btn_disconnect, QPushButton#btn_disconnect_qr {
                background: #6a1a1a;
                color: #ff6666;
                border-color: #8a2a2a;
                font-weight: bold;
            }
            QPushButton#btn_disconnect:hover, QPushButton#btn_disconnect_qr:hover {
                background: #8a2a2a;
            }
            QPushButton#btn_close {
                background: transparent;
                border: 1px solid #4a4a4a;
                color: #aaa;
                font-size: 10pt;
                min-width: 80px;
                min-height: 32px;
            }
            QPushButton#btn_close:hover {
                background: #3b3b3b;
                color: #fff;
            }
            QTextEdit {
                background: #1a1a1a;
                color: #88ccff;
                border: 1px solid #3a3a3a;
                border-radius: 3px;
                font-family: Consolas, monospace;
                font-size: 10pt;
                padding: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background: #2b2b2b;
                border-radius: 3px;
            }
            QTabBar::tab {
                background: #333;
                color: #a9b7c6;
                padding: 7px 18px;
                border: 1px solid #4a4a4a;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #1a6a3a;
                color: #d8ffe4;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("安卓 ADB 无线调试")
        title.setStyleSheet("color: #88ccff; font-size: 12pt; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # ---------------- 扫码连接页 ----------------
        qr_page = QWidget()
        qr_layout = QVBoxLayout(qr_page)
        qr_layout.setContentsMargins(10, 10, 10, 10)
        qr_layout.setSpacing(8)

        self.info_label_qr = QLabel()
        self.info_label_qr.setWordWrap(True)
        self.info_label_qr.setMinimumHeight(72)
        self.info_label_qr.setStyleSheet(
            "color: #a9b7c6; font-size: 10pt; padding: 6px; background: #222; border-radius: 3px;"
        )
        qr_status_row = QHBoxLayout()
        qr_status_row.setSpacing(10)
        self.btn_disconnect_qr = QPushButton("断开")
        self.btn_disconnect_qr.setObjectName("btn_disconnect_qr")
        self.btn_disconnect_qr.setVisible(False)
        qr_status_row.addWidget(self.info_label_qr, 1)
        qr_status_row.addWidget(self.btn_disconnect_qr, 0, Qt.AlignVCenter)
        qr_layout.addLayout(qr_status_row)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setFixedSize(282, 282)
        self.qr_label.setStyleSheet("background: white; border: 1px solid #444;")
        self.qr_label.setCursor(Qt.PointingHandCursor)
        self.qr_label.installEventFilter(self)
        qr_layout.addWidget(self.qr_label, 0, Qt.AlignHCenter)

        self.qr_log = QTextEdit()
        self.qr_log.setReadOnly(True)
        self.qr_log.setFixedHeight(110)
        self.qr_log.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.qr_log.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        qr_layout.addWidget(self.qr_log)
        qr_layout.addStretch(1)

        self.tabs.addTab(qr_page, "扫码连接")

        # ---------------- USB 无线连接页 ----------------
        usb_page = QWidget()
        usb_layout = QVBoxLayout(usb_page)
        usb_layout.setContentsMargins(10, 10, 10, 10)
        usb_layout.setSpacing(8)

        self.info_label = QLabel("就绪")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet(
            "color: #a9b7c6; font-size: 10pt; padding: 4px; background: #222; border-radius: 3px;"
        )

        self.btn_start = QPushButton("一键连接")
        self.btn_start.setObjectName("btn_start")
        self.btn_disconnect = QPushButton("断开")
        self.btn_disconnect.setObjectName("btn_disconnect")
        self.btn_disconnect.setVisible(False)
        usb_status_row = QHBoxLayout()
        usb_status_row.setSpacing(12)
        usb_status_row.addWidget(self.btn_start, 0)
        usb_status_row.addWidget(self.info_label, 1)
        usb_status_row.addWidget(self.btn_disconnect, 0)
        usb_layout.addLayout(usb_status_row)

        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFixedHeight(150)
        self.status_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.status_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        usb_layout.addWidget(self.status_text)
        usb_layout.addStretch(1)

        self.tabs.addTab(usb_page, "USB连接无线调试")

        # ---------------- 底部关闭按钮 ----------------
        close_row = QHBoxLayout()
        self.btn_close = QPushButton("关闭")
        self.btn_close.setObjectName("btn_close")
        close_row.addStretch()
        close_row.addWidget(self.btn_close)
        close_row.addStretch()
        layout.addLayout(close_row)

    def _connect_signals(self):
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.btn_disconnect_qr.clicked.connect(self.on_disconnect_qr)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_disconnect.clicked.connect(self.on_disconnect)
        self.btn_close.clicked.connect(self.reject)

    def _on_tab_changed(self, index):
        if index == 0:
            self._start_task(self._qr_init_flow, "qr")
        elif index == 1:
            self._start_task(self._usb_refresh_status_flow, "usb")

    def eventFilter(self, obj, event):
        if obj == self.qr_label and event.type() == event.Type.MouseButtonPress:
            self.on_refresh_qr()
            return True
        return super().eventFilter(obj, event)

    # ----------------------------------------------------------------
    # 通用 UI / 日志
    # ----------------------------------------------------------------
    def _log(self, text):
        self.status_text.append(text)
        self.status_text.verticalScrollBar().setValue(
            self.status_text.verticalScrollBar().maximum()
        )

    def _log_qr(self, text):
        self.qr_log.append(text)
        self.qr_log.verticalScrollBar().setValue(
            self.qr_log.verticalScrollBar().maximum()
        )

    def _set_connected_state(self):
        self.info_label.setWordWrap(False)
        self.info_label.setMinimumHeight(0)
        self.btn_start.setText("已连接")
        self.btn_start.setEnabled(False)
        self.btn_start.setStyleSheet(
            "background: #3b3b3b; color: #666; border: 1px solid #4a4a4a; font-weight: normal;"
        )
        self.btn_disconnect.setVisible(True)
        self.btn_disconnect.setEnabled(True)
        self.info_label.setText(f"无线调试已连接: {self._usb_endpoint()}")
        self.info_label.setStyleSheet(
            "color: #66dd88; font-size: 10pt; padding: 4px; background: #1a3a2a; border-radius: 3px;"
        )
        self._connected = True

    def _set_disconnected_state(self):
        self.info_label.setWordWrap(False)
        self.info_label.setMinimumHeight(0)
        self.btn_start.setText("一键连接")
        self.btn_start.setEnabled(True)
        self.btn_start.setStyleSheet(
            "background: #1a6a3a; color: #66dd88; border: none; font-weight: bold;"
        )
        self.btn_disconnect.setVisible(False)
        self.info_label.setText("就绪")
        self.info_label.setStyleSheet(
            "color: #a9b7c6; font-size: 10pt; padding: 4px; background: #222; border-radius: 3px;"
        )
        self._connected = False
        self._wifi_ip = None

    def _usb_endpoint(self):
        if not self._wifi_ip:
            return ""
        if ":" in self._wifi_ip:
            return self._wifi_ip
        return f"{self._wifi_ip}:5555"

    def _set_qr_waiting_state(self):
        self.info_label_qr.setWordWrap(True)
        self.info_label_qr.setMinimumHeight(72)
        self.info_label_qr.setText(
            "请按以下步骤操作：\n"
            "1. 安卓手机打开：设置 → 开发者选项 → 无线调试\n"
            "2. 点击“使用二维码配对设备”\n"
            "3. 用手机扫描下方二维码，点击二维码可重新生成"
        )
        self.info_label_qr.setStyleSheet(
            "color: #a9b7c6; font-size: 10pt; padding: 6px; background: #222; border-radius: 3px;"
        )
        self.qr_label.setCursor(Qt.PointingHandCursor)
        self.btn_disconnect_qr.setVisible(False)
        self._qr_connected = False
        self._qr_endpoint = None

    def _set_qr_checking_state(self):
        self.info_label_qr.setWordWrap(False)
        self.info_label_qr.setMinimumHeight(0)
        self.info_label_qr.setText("正在检测 ADB 连接...")
        self.info_label_qr.setStyleSheet(
            "color: #a9b7c6; font-size: 10pt; padding: 6px; background: #222; border-radius: 3px;"
        )
        self.qr_label.setCursor(Qt.PointingHandCursor)
        self.btn_disconnect_qr.setVisible(False)
        self._qr_connected = False
        self._qr_endpoint = None

    def _set_qr_connected_state(self):
        self.info_label_qr.setWordWrap(False)
        self.info_label_qr.setMinimumHeight(0)
        self.info_label_qr.setText(f"无线调试已连接: {self._qr_endpoint}")
        self.info_label_qr.setStyleSheet(
            "color: #66dd88; font-size: 10pt; padding: 6px; background: #1a3a2a; border-radius: 3px;"
        )
        self.btn_disconnect_qr.setVisible(True)
        self.btn_disconnect_qr.setEnabled(True)
        self._qr_connected = True

    # ----------------------------------------------------------------
    # 后台任务调度
    # ----------------------------------------------------------------
    def _start_task(self, fn, mode):
        self._stop_current_task()
        self._active_mode = mode
        self._is_running = True
        self._task = _AdbTask(self, fn)
        self._task.sig_log.connect(self._on_task_log)
        self._task.sig_state.connect(self._on_task_state)
        self._task.sig_busy.connect(self._on_task_busy)
        self._task.start()

        if mode == "qr":
            self.btn_disconnect_qr.setEnabled(False)
        else:
            self.btn_start.setEnabled(False)
            self.btn_disconnect.setEnabled(False)

    def _stop_current_task(self):
        """停止并解绑当前后台任务，避免旧的二维码等待任务卡住 USB 流程。"""
        task = self._task
        if task is None:
            return

        try:
            task.sig_log.disconnect(self._on_task_log)
            task.sig_state.disconnect(self._on_task_state)
            task.sig_busy.disconnect(self._on_task_busy)
        except Exception:
            pass

        if task.isRunning():
            task.request_stop()
            if not task.wait(1500):
                task.terminate()
                task.wait(500)

        self._task = None
        self._is_running = False

    def _on_task_log(self, text):
        if self._active_mode == "qr":
            self._log_qr(text)
        else:
            self._log(text)

    def _on_task_state(self, state):
        if state.startswith("qr_connected:"):
            self._qr_endpoint = state.split(":", 1)[1]
            self._set_qr_connected_state()
        elif state == "qr_disconnected":
            self._set_qr_waiting_state()
        elif state.startswith("connected:"):
            self._connected = True
            self._wifi_ip = state.split(":", 1)[1]
            self._set_connected_state()
        else:
            self._set_disconnected_state()

    def _on_task_busy(self, busy):
        self._is_running = busy
        if busy:
            return
        if self._active_mode == "qr":
            self.btn_disconnect_qr.setVisible(self._qr_connected)
            self.btn_disconnect_qr.setEnabled(self._qr_connected)
        elif self._connected:
            self._set_connected_state()
        else:
            self._set_buttons_enabled(True, False)

    # ----------------------------------------------------------------
    # ADB 基础工具
    # ----------------------------------------------------------------
    def _adb_path(self):
        return get_adb_path()

    def _check_status(self):
        """USB 无线调试页使用：返回 (connected, ip)，只识别 5555 端口。"""
        ok, out = run_adb(self._adb_path(), ["devices"], timeout=5)
        if ok == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].endswith(":5555") and parts[1].startswith("device"):
                    return True, parts[0].replace(":5555", "")
        return False, None

    def _get_connected_wireless_endpoint(self):
        """返回第一个已连接无线设备的 serial:port，例如 192.168.1.3:41234。"""
        ok, out = run_adb(self._adb_path(), ["devices"], timeout=5)
        if ok == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and ":" in parts[0] and parts[1].startswith("device"):
                    return parts[0]
        return None

    def _is_endpoint_connected(self, endpoint):
        ok, out = run_adb(self._adb_path(), ["devices"], timeout=5)
        if ok == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == endpoint and parts[1].startswith("device"):
                    return True
        return False

    def _check_usb(self):
        ok, out = run_adb(self._adb_path(), ["devices"], timeout=5)
        if ok == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and ":" not in parts[0] and parts[1].startswith("device"):
                    return True
        return False

    def _get_wifi_ip(self):
        commands = [
            ["shell", "ip", "addr", "show", "wlan0"],
            ["shell", "ip", "addr", "show"],
            ["shell", "ifconfig"],
        ]
        for cmd in commands:
            ok, out = run_adb(self._adb_path(), cmd, timeout=5)
            if ok == 0 and out:
                patterns = [
                    r'inet\s+(\d+\.\d+\.\d+\.\d+)/\d+',
                    r'inet addr:(\d+\.\d+\.\d+\.\d+)',
                    r'(\d+\.\d+\.\d+\.\d+)\s+\d+\s+\d+\s+\w+',
                ]
                for pattern in patterns:
                    for ip in re.findall(pattern, out):
                        if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                            return ip
        return None

    def _mdns_services(self, adb):
        ok, out = run_adb(adb, ["mdns", "services"], timeout=6)
        if ok != 0:
            return []
        result = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of discovered"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                instance = parts[0].rstrip(".")
                service = parts[1].rstrip(".")
                endpoint = parts[2] if len(parts) >= 3 else ""
                result.append((instance, service, endpoint))
        return result

    def _split_host_port(self, endpoint):
        if ":" in endpoint:
            host, port = endpoint.rsplit(":", 1)
            return host, port
        return endpoint, ""

    def _find_mdns_pairing_endpoint(self, adb, service):
        for instance, service_type, endpoint in self._mdns_services(adb):
            if "_adb-tls-pairing._tcp" in service_type and instance == service and endpoint:
                return endpoint
        return None

    def _find_mdns_connect_endpoint(self, adb, preferred_guid=None):
        candidates = []
        for instance, service_type, endpoint in self._mdns_services(adb):
            if "_adb-tls-connect._tcp" not in service_type or not endpoint:
                continue
            if preferred_guid and preferred_guid in instance:
                return endpoint
            candidates.append(endpoint)
        return candidates[0] if candidates else None

    # ----------------------------------------------------------------
    # 切换标签时的状态刷新（只查询，不发起连接）
    # ----------------------------------------------------------------
    def _qr_refresh_status_flow(self, task):
        start_adb_server(self._adb_path())
        endpoint = self._get_connected_wireless_endpoint()
        if endpoint:
            task.sig_state.emit(f"qr_connected:{endpoint}")
        else:
            task.sig_state.emit("qr_disconnected")

    def _usb_refresh_status_flow(self, task):
        start_adb_server(self._adb_path())
        connected, ip = self._check_status()
        if connected:
            task.sig_state.emit(f"connected:{ip}:5555")
            return
        endpoint = self._get_connected_wireless_endpoint()
        if endpoint:
            task.sig_state.emit(f"connected:{endpoint}")
        else:
            task.sig_state.emit("disconnected")

    # ----------------------------------------------------------------
    # 扫码连接流程
    # ----------------------------------------------------------------
    def _generate_qr(self):
        self._qr_service = "mmbl-" + secrets.token_hex(4)
        self._qr_password = f"{secrets.randbelow(1000000):06d}"
        self._qr_payload = f"WIFI:T:ADB;S:{self._qr_service};P:{self._qr_password};;"

        qr = QrCode.encode_text(self._qr_payload, QrCode.Ecc.MEDIUM)
        scale = 8
        border = 2
        size = qr.get_size()
        dim = (size + border * 2) * scale
        image = QImage(dim, dim, QImage.Format_RGB32)
        image.fill(QColor("white").rgb())
        black = QColor("black").rgb()
        for y in range(size):
            for x in range(size):
                if qr.get_module(x, y):
                    px = (x + border) * scale
                    py = (y + border) * scale
                    for dy in range(scale):
                        for dx in range(scale):
                            image.setPixel(px + dx, py + dy, black)
        pixmap = QPixmap.fromImage(image).scaled(
            280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.qr_label.setPixmap(pixmap)

    def _start_qr_init(self):
        self._start_task(self._qr_init_flow, "qr")

    def _qr_init_flow(self, task):
        adb = self._adb_path()
        start_adb_server(adb)
        ok, _ = run_adb(adb, ["version"], timeout=5)
        task.log("✅ ADB 可用" if ok == 0 else "❌ ADB 不可用")

        endpoint = self._get_connected_wireless_endpoint()
        if endpoint:
            task.log(f"✅ 已连接: {endpoint}")
            task.sig_state.emit(f"qr_connected:{endpoint}")
            return

        task.sig_state.emit("qr_disconnected")
        task.log("✅ 二维码已就绪，等待扫码...")
        self._qr_pair_and_connect(task)

    def _qr_pair_and_connect(self, task):
        adb = self._adb_path()
        start_adb_server(adb)
        service = self._qr_service
        password = self._qr_password

        task.log("请打开无线调试 → 扫码配对")
        task.log("等待扫码...")

        pairing_endpoint = None
        while not task.is_stop_requested():
            pairing_endpoint = self._find_mdns_pairing_endpoint(adb, service)
            if pairing_endpoint:
                break
            time.sleep(1)

        if task.is_stop_requested():
            task.sig_state.emit("qr_disconnected")
            return

        host, port = self._split_host_port(pairing_endpoint)
        task.log(f"🔗 发现配对服务: {host}:{port}")
        ok, out = run_adb(adb, ["pair", f"{host}:{port}", password], timeout=12)
        if task.is_stop_requested():
            task.sig_state.emit("qr_disconnected")
            return
        if not (ok == 0 and ("successfully" in out.lower() or "paired" in out.lower())):
            detail = (out or "").strip().replace("\n", " ")
            task.log(f"❌ 配对失败: {detail}")
            task.sig_state.emit("qr_disconnected")
            return
        task.log("✅ 配对成功")

        guid = None
        match = re.search(r"guid=([^\]]+)", out)
        if match:
            guid = match.group(1)

        task.log("🔍 查找连接端口...")
        connect_endpoint = None
        while not task.is_stop_requested():
            connect_endpoint = self._find_mdns_connect_endpoint(adb, guid)
            if connect_endpoint:
                break
            time.sleep(1)

        if task.is_stop_requested():
            task.sig_state.emit("qr_disconnected")
            return

        host, port = self._split_host_port(connect_endpoint)
        task.log(f"🔗 连接设备: {host}:{port}")
        ok, out = run_adb(adb, ["connect", f"{host}:{port}"], timeout=12)
        if ok == 0 and ("connected" in out.lower() or "already" in out.lower()):
            endpoint = f"{host}:{port}"
            if self._is_endpoint_connected(endpoint):
                task.log("✅ 连接成功！")
                task.sig_state.emit(f"qr_connected:{endpoint}")
            else:
                task.log("❌ 设备未就绪")
                task.sig_state.emit("qr_disconnected")
        else:
            detail = (out or "").strip().replace("\n", " ")
            task.log(f"❌ 连接失败: {detail}")
            task.sig_state.emit("qr_disconnected")

    def _qr_disconnect_flow(self, task):
        adb = self._adb_path()
        start_adb_server(adb)
        endpoint = self._qr_endpoint or ""
        if endpoint:
            ok, _ = run_adb(adb, ["disconnect", endpoint], timeout=10)
        else:
            ok, _ = run_adb(adb, ["disconnect"], timeout=10)
        task.log("✅ 已断开" if ok == 0 else "❌ 断开失败")
        if endpoint and self._is_endpoint_connected(endpoint):
            task.sig_state.emit(f"qr_connected:{endpoint}")
        else:
            task.sig_state.emit("qr_disconnected")

    # ----------------------------------------------------------------
    # USB 无线连接流程（保留原有逻辑）
    # ----------------------------------------------------------------
    def _init_flow(self, task):
        start_adb_server(self._adb_path())
        ok, _ = run_adb(self._adb_path(), ["version"], timeout=5)
        task.log("✅ ADB 可用" if ok == 0 else "❌ ADB 不可用")

        connected, ip = self._check_status()
        if connected:
            task.log(f"✅ 已连接: {ip}:5555")
        task.sig_state.emit(f"connected:{ip}" if connected else "disconnected")

    def _start_flow(self, task):
        adb = self._adb_path()
        start_adb_server(adb)
        run_adb(adb, ["disconnect"], timeout=5)

        connected, ip = self._check_status()
        if connected:
            task.log(f"✅ 已连接: {ip}:5555")
            task.sig_state.emit(f"connected:{ip}")
            return

        if not self._check_usb():
            task.log("❌ 未检测到 USB 设备")
            task.sig_state.emit("disconnected")
            return

        ip = self._get_wifi_ip()
        if ip:
            task.log(f"IP: {ip}")
        else:
            task.log("⚠️ 未获取到 IP")

        ok, _ = run_adb(adb, ["tcpip", "5555"], timeout=10)
        if ok != 0:
            task.log("❌ 开启无线调试失败")
            task.sig_state.emit("disconnected")
            return

        if not ip:
            ip = self._get_wifi_ip()
            if ip:
                task.log(f"IP: {ip}")

        time.sleep(1.5)

        if not ip:
            task.log("❌ 无 IP")
            task.sig_state.emit("disconnected")
            return

        ok, out = run_adb(adb, ["connect", f"{ip}:5555"], timeout=10)
        if ok == 0 and ("connected" in out.lower() or "already" in out.lower()):
            connected, ip = self._check_status()
            if connected:
                task.log("✅ 连接成功！")
                task.sig_state.emit(f"connected:{ip}")
            else:
                task.log("❌ 设备未就绪")
                task.sig_state.emit("disconnected")
        else:
            task.log("❌ 连接失败")
            task.sig_state.emit("disconnected")

    def _disconnect_flow(self, task):
        start_adb_server(self._adb_path())
        endpoint = self._usb_endpoint()
        ok, _ = run_adb(self._adb_path(), ["disconnect", endpoint], timeout=10)
        if ok == 0:
            task.log("✅ 已断开")
            task.sig_state.emit("disconnected")
        else:
            task.log("❌ 断开失败")
            if endpoint:
                task.sig_state.emit(f"connected:{endpoint}")

    # ----------------------------------------------------------------
    # 界面操作
    # ----------------------------------------------------------------
    def on_refresh_qr(self):
        if self._qr_connected:
            return
        self._stop_current_task()
        self._generate_qr()
        self._set_qr_waiting_state()
        self._log_qr("二维码已刷新，等待手机扫描...")
        self._start_task(self._qr_pair_and_connect, "qr")

    def on_disconnect_qr(self):
        if self._is_running or not self._qr_connected:
            return
        self._log_qr("🔌 断开中...")
        self._start_task(self._qr_disconnect_flow, "qr")

    def on_start(self):
        if self._connected:
            return
        self._log("连接中...")
        self._start_task(self._start_flow, "usb")

    def on_disconnect(self):
        if self._is_running or not self._connected:
            return
        self._log("🔌 断开中...")
        self._start_task(self._disconnect_flow, "usb")

    def _set_buttons_enabled(self, start, disconnect):
        self.btn_start.setEnabled(start)
        self.btn_disconnect.setEnabled(disconnect)

    def closeEvent(self, event):
        # 只停止正在等待/检测的后台任务，不主动断开 ADB 连接
        if self._task and self._task.isRunning():
            self._task.request_stop()
            self._task.wait(3000)
            if self._task.isRunning():
                self._task.terminate()
                self._task.wait(1000)
        event.accept()


def show_adb_wifi_dialog(parent=None):
    return AdbWifiDialog(parent).exec()