# main.py
import asyncio  # 必须放在最前面
import sys
import os
import time
import random

# 修复 PyInstaller --noconsole 导致的 stdout/stderr 为 None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')


# 抑制 FFmpeg 子进程黑窗口（必须在导入 spleeter 之前）
if sys.platform == 'win32':
    import subprocess
    _original_popen = subprocess.Popen
    def _patched_popen(*args, **kwargs):
        kwargs.setdefault('creationflags', 0)
        kwargs['creationflags'] |= subprocess.CREATE_NO_WINDOW
        return _original_popen(*args, **kwargs)
    subprocess.Popen = _patched_popen

import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox, QDialog, QDialogButtonBox,
    QInputDialog,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QStyledItemDelegate,
    QStyle,
    QListView
)
from PySide6.QtCore import (
    Qt, QTimer, Slot, QAbstractNativeEventFilter,
    QCoreApplication, QRect, QPoint,
    QAbstractListModel, QModelIndex, QSortFilterProxyModel,
    QSettings, QThread, Signal
)
from PySide6.QtGui import (
    QIcon, QGuiApplication, QShortcut, QKeySequence,
    QClipboard, QColor, QPainter, QPen, QBrush, QFont,
    QLinearGradient
)
from utils.resource import get_icon_path
from utils.toast import Toast, CustomQuestionDialog, CustomInputDialog
from utils.adb_wifi_dialog import show_adb_wifi_dialog
from core.parser_factory import ParserFactory

def get_asset_path(relative_path):
    from utils.resource import get_resource_path
    return get_resource_path(relative_path)

from utils.window_helper import get_foreground_window_title, get_all_visible_window_titles
from core.music_parser import MusicLib, parse_event_list, PlayEvent
from core.play_worker import PlayWorker
from gui.ui_mainwindow import setup_ui

# 授权开关：True = 需要激活码；False = 跳过激活检查。
ENABLE_LICENSE = False

# ---------- 自定义列表模型 ----------
class MusicListModel(QAbstractListModel):
    def __init__(self, names=None):
        super().__init__()
        self._names = names or []

    def set_names(self, names):
        self.beginResetModel()
        self._names = names[:]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._names)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._names):
            return None
        if role == Qt.DisplayRole:
            return self._names[index.row()]
        return None


# ---------- 自定义委托：为播放条目绘制独立背景，且无视选中状态 ----------
class PlayingItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.playing_name = None   # 由主窗口设置

    def paint(self, painter, option, index):
        # 获取显示文本，与 playing_name 比较
        text = index.data(Qt.DisplayRole)
        is_playing = (text == self.playing_name)
        if is_playing:
            painter.save()
            rect = option.rect
            painter.setRenderHint(QPainter.Antialiasing)
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, QColor("#2a5a7a"))
            grad.setColorAt(1, QColor("#1a3a5a"))
            painter.fillRect(rect, grad)
            if option.state & QStyle.State_Selected:
                painter.setPen(QPen(QColor("#ffdd44"), 2))
                painter.drawLine(rect.left() + 2, rect.top() + 4, rect.left() + 2, rect.bottom() - 4)
            painter.restore()

            if text:
                painter.save()
                painter.setPen(QColor("#ffffff"))
                font = painter.font()
                font.setBold(True)
                painter.setFont(font)
                text_rect = rect.adjusted(8, 0, -8, 0)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
                painter.restore()
        else:
            super().paint(painter, option, index)


# ---------- 常量 ----------
exe_root_path = os.path.dirname(os.path.abspath(sys.argv[0]))
bundle_music_folder = os.path.join(exe_root_path, "常用音谱")

DEFAULT_DIRS = []
if os.path.isdir(bundle_music_folder):
    DEFAULT_DIRS.append(bundle_music_folder)
DEFAULT_DIRS.append("E:\\常用音谱")
DEFAULT_DIRS.append("D:\\常用音谱")

FOCUS_CHECK_INTERVAL = 400
SPEED_STEP = 0.01
SPEED_MIN = 0.1
SPEED_MAX = 5.0

LOOP_NONE = 0
LOOP_SINGLE = 1
LOOP_ALL = 2

HOTKEY_SPACE = 1001
HOTKEY_ESC   = 1002
HOTKEY_LEFT  = 1003
HOTKEY_RIGHT = 1004
HOTKEY_UP    = 1005
HOTKEY_DOWN  = 1006
HOTKEY_0     = 2001
HOTKEY_1     = 2002
HOTKEY_2     = 2003
WM_HOTKEY = 0x0312


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG" or eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                self.callback(hotkey_id)
                return True, 0
        return False, 0


class LikeWorker(QThread):
    """点赞工作线程：定期随机点击屏幕"""
    sig_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.stop_flag = False
        self.adb_touch = None

    def run(self):
        try:
            from utils.adb_touch import ADBTouch
            self.adb_touch = ADBTouch()
        except Exception as e:
            self.sig_error.emit(f"ADB初始化失败")
            return

        while not self.stop_flag:
            # 完全随机节奏，模拟真人点赞：有时疯狂连点，有时停几秒看内容
            r = random.random()
            if r < 0.30:         # 30% 疯狂连点
                wait_time = random.uniform(0.08, 0.15)
            elif r < 0.75:       # 45% 快速
                wait_time = random.uniform(0.15, 0.25)
            elif r < 0.88:       # 13% 正常
                wait_time = random.uniform(0.25, 0.40)
            elif r < 0.95:       # 7% 稍慢
                wait_time = random.uniform(0.40, 0.80)
            elif r < 0.97:       # 2% 停顿看内容
                wait_time = random.uniform(0.80, 2.5)
            else:                # 3% 长时间停留
                wait_time = random.uniform(2.0, 6.0)
            
            start = time.time()
            while (time.time() - start) < wait_time and not self.stop_flag:
                time.sleep(0.005)

            if self.stop_flag:
                break

            # 执行单次点赞点击
            try:
                self.adb_touch.random_like_tap()
            except Exception as e:
                self.sig_error.emit(f"点赞失败: {str(e)}")
                break

        if self.adb_touch:
            self.adb_touch.close()
            self.adb_touch = None

    def stop_like(self):
        self.stop_flag = True


class MainWindow(QMainWindow):
    sig_gmaut_control = Signal(str, object)

    def __init__(self):
        super().__init__()
        title = "猫之琴"
        if ENABLE_LICENSE:
            from license import get_license_display
            title += get_license_display()
        self.setWindowTitle(title)
        self.setMinimumSize(320, 600)
        self.setMaximumWidth(680)
        self.setMaximumHeight(990)
        self.resize(320, 760)

        self.music_lib = MusicLib()
        # ---------- 初始化 QSettings ----------
        self.settings = QSettings("MMBLOSIRIS", "MMBLPlayer")

        self.worker: PlayWorker | None = None
        self.like_worker: LikeWorker | None = None  # 点赞工作线程
        self.loop_mode = LOOP_NONE
        self.current_music_name: str | None = None
        self.event_list: list[PlayEvent] = []
        self.total_ms = 0
        self.all_names = []
        self.auto_speed_timer = None
        self.auto_paused = False
        self.hotkey_registered = False
        self.hotkey_filter = None
        self._updating = False
        self.playing_name = None
        self.loop_play_timer = QTimer()
        self.loop_play_timer.setSingleShot(True)
        self._pending_switch_timer = QTimer(self)
        self._pending_switch_timer.setSingleShot(True)
        self._pending_switch_timer.timeout.connect(self._on_pending_switch_timeout)
        self._pending_target_name = None

        self.base_state = "就绪"
        self.game_selected = False
        self.output_mode = "pc"
        self.gmaut_bridge = None
        self.gmaut_state_timer = None
        self.sig_gmaut_control.connect(self._apply_gmaut_control, Qt.QueuedConnection)

        setup_ui(self)
        self._replace_list_widget()
        # ---------- 绑定 UI 事件 ----------
        self.bind_ui_event()

        # ---------- 焦点定时器 ----------
        self.focus_timer = QTimer()
        self.focus_timer.setInterval(FOCUS_CHECK_INTERVAL)
        self.focus_timer.timeout.connect(self.check_game_focus)
        self.focus_timer.start()

        self.load_default_dir()
        self.setFocusPolicy(Qt.StrongFocus)

        try:
            icon_full_path = get_icon_path()
            if os.path.exists(icon_full_path):
                self.setWindowIcon(QIcon(icon_full_path))
        except Exception:
            pass

        self.hotkey_filter = HotkeyFilter(self.on_hotkey)
        QCoreApplication.instance().installNativeEventFilter(self.hotkey_filter)

        # ---------- 应用程序级快捷键（仅 ADB 模式） ----------
        self.shortcuts = []

        def make_shortcut(key, callback):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(callback)
            sc.setContext(Qt.ApplicationShortcut)
            sc.setEnabled(False)
            self.shortcuts.append(sc)
            return sc

        self.shortcut_space = make_shortcut(Qt.Key_Space, self.play_or_resume)
        make_shortcut(Qt.Key_Escape, self.stop_all)
        make_shortcut(Qt.Key_Left,  lambda: self.adjust_speed(-SPEED_STEP))
        make_shortcut(Qt.Key_Right, lambda: self.adjust_speed(SPEED_STEP))
        make_shortcut(Qt.Key_Up,    self.play_prev)
        make_shortcut(Qt.Key_Down,  self.play_next)
        make_shortcut(Qt.Key_0,     lambda: self.combo_mode.setCurrentIndex(0))
        make_shortcut(Qt.Key_1,     lambda: self.combo_mode.setCurrentIndex(1))
        make_shortcut(Qt.Key_2,     lambda: self.combo_mode.setCurrentIndex(2))
        self.update_shortcuts()
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        self.btn_output_mode.clicked.connect(self.toggle_output_mode)

        # ---------- 窗口固定在桌面左侧 ----------
        screen = QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry()
        x = 40
        offset = 20
        y = (geometry.height() - self.height()) // 2 - offset
        if y < 0:
            y = 0
        self.move(x, y)

        self.update_output_mode_ui()
        self.start_gmaut_bridge()

        # ---------- 曲目名可点击复制 ----------
        self.label_current.setCursor(Qt.PointingHandCursor)
        self.label_current.installEventFilter(self)

        # ---------- 状态标签可点击 ----------
        self.label_status.setCursor(Qt.PointingHandCursor)
        self.label_status.installEventFilter(self)

        # ---------- 乐谱目录框可点击打开 ----------
        self.edit_music_dir.installEventFilter(self)

    # ------------------------------------------------------------------
    def _replace_list_widget(self):
        """将 UI 中的 QListWidget 替换为 QListView + 模型"""
        old_list = self.list_music
        # 获取旧控件的父布局
        parent_layout = old_list.parent().layout()
        if parent_layout is None:
            return

        # 创建新控件
        new_list = QListView()
        new_list.setObjectName(old_list.objectName())
        # 复制样式表
        style = old_list.styleSheet()
        style = style.replace("QListWidget", "QListView")
        new_list.setStyleSheet(style)

        # 复制其他属性
        new_list.setSelectionMode(old_list.selectionMode())
        new_list.setFont(old_list.font())
        new_list.setFocusPolicy(old_list.focusPolicy())

        # 替换布局中的控件
        index = parent_layout.indexOf(old_list)
        if index != -1:
            parent_layout.replaceWidget(old_list, new_list)
        old_list.deleteLater()

        # 保存新控件
        self.list_music = new_list

        # 创建模型和代理模型
        self.model = MusicListModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.list_music.setModel(self.proxy_model)
        self.list_music.setUniformItemSizes(True)   # 性能关键

        # 安装自定义委托
        self.delegate = PlayingItemDelegate(self.list_music)
        self.list_music.setItemDelegate(self.delegate)

        # 重新连接信号（doubleClicked）
        self.list_music.doubleClicked.connect(self.double_play)

        # 选中透明，悬停背景
        self.list_music.setStyleSheet(self.list_music.styleSheet() + """
            QListView::item:selected {
                background: transparent;
            }
            QListView::item:hover {
                background: #3a3a3a;
            }
        """)

    # ------------------------------------------------------------------
    def bind_ui_event(self):
        self.btn_select_win.clicked.connect(self.select_game_window)
        self.btn_folder.clicked.connect(self.choose_dir)
        self.btn_del.clicked.connect(self.delete_item)
        self.btn_rename.clicked.connect(self.rename_item)

        self.chk_loop_single.toggled.connect(self.on_loop_checkbox_changed)
        self.chk_loop_all.toggled.connect(self.on_loop_checkbox_changed)

        self.btn_speed_up.pressed.connect(lambda: self.start_auto_speed(SPEED_STEP))
        self.btn_speed_up.released.connect(self.stop_auto_speed)
        self.btn_speed_down.pressed.connect(lambda: self.start_auto_speed(-SPEED_STEP))
        self.btn_speed_down.released.connect(self.stop_auto_speed)

        self.btn_play.clicked.connect(self.play_or_resume)
        self.btn_pause.clicked.connect(self.pause_play)
        self.btn_stop.clicked.connect(self.stop_all)

        self.slider_progress.sliderReleased.connect(self.jump_slider)
        self.edit_search.textChanged.connect(self.filter_list)
        self.btn_search.clicked.connect(self.search_and_refresh)
        # self.list_music.doubleClicked 已在 _replace_list_widget 中连接

    def eventFilter(self, obj, event):
        if obj == self.label_current and event.type() == event.Type.MouseButtonPress:
            text = self.label_current.text()
            if text:
                clipboard = QGuiApplication.clipboard()
                clipboard.setText(text)
                Toast.show_message(f"已复制：{text}", self)
                return True
        # 点击状态标签（仅 ADB 模式有效）
        if obj == self.label_status and event.type() == event.Type.MouseButtonPress:
            if self.output_mode == "adb" or self.output_mode == "adb_like":
                show_adb_wifi_dialog(self)
            return True
        # 点击乐谱目录框，打开已选目录
        if obj == self.edit_music_dir and event.type() == event.Type.MouseButtonPress:
            path = self.edit_music_dir.text().strip()
            if path and os.path.isdir(path):
                try:
                    os.startfile(path)
                except Exception:
                    pass
            return True
        return super().eventFilter(obj, event)

    # ---------- 播放标记管理 ----------
    def apply_playing_marker(self):
        """更新委托的播放名称并刷新视图"""
        self.delegate.playing_name = self.playing_name
        self.list_music.viewport().update()

    # ------------------------------------------------------------
    def on_loop_checkbox_changed(self):
        if self._updating:
            return
        self._updating = True
        try:
            sender = self.sender()
            single = self.chk_loop_single.isChecked()
            all_ = self.chk_loop_all.isChecked()

            if sender == self.chk_loop_single:
                if single:
                    self.chk_loop_all.setChecked(False)
                    self.loop_mode = LOOP_SINGLE
                else:
                    if self.chk_loop_all.isChecked():
                        self.loop_mode = LOOP_ALL
                    else:
                        self.loop_mode = LOOP_NONE
            elif sender == self.chk_loop_all:
                if all_:
                    self.chk_loop_single.setChecked(False)
                    self.loop_mode = LOOP_ALL
                else:
                    if self.chk_loop_single.isChecked():
                        self.loop_mode = LOOP_SINGLE
                    else:
                        self.loop_mode = LOOP_NONE
            else:
                if single and all_:
                    self.chk_loop_single.setChecked(False)
                    self.loop_mode = LOOP_ALL
                elif single:
                    self.loop_mode = LOOP_SINGLE
                elif all_:
                    self.loop_mode = LOOP_ALL
                else:
                    self.loop_mode = LOOP_NONE

            self.update_status_text()
        finally:
            self._updating = False

    def on_mode_changed(self, index):
        if self.worker and self.worker.isRunning():
            self.worker.set_mode(index)

    def _stop_thread(self, thread):
        """有界等待线程退出；若线程卡死则强制终止，避免 GUI 无限期未响应。"""
        if thread is None or not thread.isRunning():
            return
        if thread.wait(3000):
            return
        thread.terminate()
        thread.wait(1000)

    def toggle_output_mode(self):
        # 切换模式前停止所有正在运行的线程
        if self.like_worker and self.like_worker.isRunning():
            self.like_worker.stop_like()
            self._stop_thread(self.like_worker)
            self.like_worker = None
        if self.worker and self.worker.isRunning():
            self.worker.stop_play()
            self._stop_thread(self.worker)
            self.worker = None

        # 重置UI状态
        self.btn_play.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.slider_progress.setEnabled(False)
        self.slider_progress.setValue(0)
        self.label_time.setText("00:00 / 00:00")
        self.playing_name = None
        self.apply_playing_marker()

        # 切换模式
        if self.output_mode == "pc":
            self.output_mode = "adb"
        elif self.output_mode == "adb":
            self.output_mode = "adb_like"
        else:
            self.output_mode = "pc"

        self.update_output_mode_ui()
        self.update_game_selection_status()
        self.update_shortcuts()
        self.update_hotkey_registration()
        self.set_base_state("就绪")

    def start_gmaut_bridge(self):
        if self.gmaut_bridge is not None:
            return
        try:
            from core.gmaut_bridge import GmautBridge
            from utils.resource import get_adb_path
            adb_path = get_adb_path()
            if not adb_path or not os.path.exists(adb_path):
                adb_path = "adb"
            self.gmaut_bridge = GmautBridge(
                on_control=self._on_gmaut_control,
                adb_cmd=adb_path,
            )
            self.gmaut_bridge.start()
        except Exception:
            self.gmaut_bridge = None
            return

        if self.gmaut_state_timer is None:
            self.gmaut_state_timer = QTimer(self)
            self.gmaut_state_timer.timeout.connect(self._send_gmaut_state)
        self.gmaut_state_timer.start(500)

    def stop_gmaut_bridge(self):
        if self.gmaut_state_timer is not None:
            self.gmaut_state_timer.stop()
        if self.gmaut_bridge is not None:
            self.gmaut_bridge.close()
            self.gmaut_bridge = None

    def _send_gmaut_state(self):
        if self.gmaut_bridge is None:
            return
        duration = int(self.total_ms or 0)
        song = self.current_music_name or self.playing_name or "未播放"
        if self.worker and self.worker.isRunning():
            playing = not getattr(self.worker, "paused", False)
            position = int(getattr(self.worker, "played_ms", 0) or 0)
            speed = float(getattr(self.worker, "speed", 1.0))
        else:
            playing = False
            pct = int(self.slider_progress.value() or 0)
            position = int(duration * pct / 100) if duration else 0
            try:
                speed = float(self.label_speed.text()[:-1])
            except Exception:
                speed = 1.0
        progress = (position / duration) if duration else 0.0
        songs = [
            {"id": str(index), "title": name}
            for index, name in enumerate(self._get_source_names_list())
        ]
        self.gmaut_bridge.send_state(
            song=song,
            playing=playing,
            progress=progress,
            position_ms=position,
            duration_ms=duration,
            speed=speed,
            songs=songs,
        )

    def _on_gmaut_control(self, action, value):
        self.sig_gmaut_control.emit(action, value)

    def _apply_gmaut_control(self, action, value):
        if action == "toggle":
            self.play_or_resume()
        elif action == "prev":
            self.play_prev()
        elif action == "next":
            self.play_next()
        elif action == "select":
            names = self._get_source_names_list()
            if isinstance(value, int) and 0 <= value < len(names):
                self.start_play(names[value])
            elif isinstance(value, str) and value:
                self.start_play(value)
        elif action == "speed":
            self.set_remote_speed(value)
        elif action == "mode":
            try:
                mode = int(value) % 3
            except Exception:
                mode = 0
            self.combo_mode.setCurrentIndex(mode)
            if self.worker:
                self.worker.set_mode(mode)

    def update_output_mode_ui(self):
        if self.output_mode == "pc":
            self.btn_output_mode.setText("PC")
            # self.btn_output_mode.setToolTip("点击切换至 安卓ADB模式")
        elif self.output_mode == "adb":
            self.btn_output_mode.setText("手机")
            # self.btn_output_mode.setToolTip("点击切换至 ADB点赞模式")
        else:  # adb_like
            self.btn_output_mode.setText("点赞")
            # self.btn_output_mode.setToolTip("点击切换至 PC键盘模式")

    def update_shortcuts(self):
        if self.output_mode == "adb":
            for sc in self.shortcuts:
                sc.setEnabled(True)
        elif self.output_mode == "adb_like":
            for sc in self.shortcuts:
                sc.setEnabled(False)
            if self.shortcut_space:
                self.shortcut_space.setEnabled(True)
        else:
            for sc in self.shortcuts:
                sc.setEnabled(False)

    def register_hotkeys(self):
        if self.hotkey_registered:
            return
        user32 = ctypes.windll.user32
        ok = True
        ok &= user32.RegisterHotKey(None, HOTKEY_SPACE, 0, 0x20)
        ok &= user32.RegisterHotKey(None, HOTKEY_ESC,   0, 0x1B)
        ok &= user32.RegisterHotKey(None, HOTKEY_LEFT,  0, 0x25)
        ok &= user32.RegisterHotKey(None, HOTKEY_RIGHT, 0, 0x27)
        ok &= user32.RegisterHotKey(None, HOTKEY_UP,    0, 0x26)
        ok &= user32.RegisterHotKey(None, HOTKEY_DOWN,  0, 0x28)
        ok &= user32.RegisterHotKey(None, HOTKEY_0,     0, 0x30)
        ok &= user32.RegisterHotKey(None, HOTKEY_1,     0, 0x31)
        ok &= user32.RegisterHotKey(None, HOTKEY_2,     0, 0x32)
        if ok:
            self.hotkey_registered = True
        else:
            self.unregister_hotkeys()
            Toast.show_message("部分热键注册失败，可能被其他程序占用", self)

    def unregister_hotkeys(self):
        if not self.hotkey_registered:
            return
        user32 = ctypes.windll.user32
        for hid in [HOTKEY_SPACE, HOTKEY_ESC, HOTKEY_LEFT, HOTKEY_RIGHT,
                    HOTKEY_UP, HOTKEY_DOWN,
                    HOTKEY_0, HOTKEY_1, HOTKEY_2]:
            user32.UnregisterHotKey(None, hid)
        self.hotkey_registered = False

    def update_hotkey_registration(self):
        if self.output_mode == "adb" or self.output_mode == "adb_like":
            self.unregister_hotkeys()
            return
        target = self.edit_target_win.text().strip()
        if not target or "请选择" in target:
            self.unregister_hotkeys()
            return
        active_win = get_foreground_window_title()
        game_focused = target in active_win
        is_running = self.worker and self.worker.isRunning()
        if is_running and game_focused:
            self.register_hotkeys()
        else:
            self.unregister_hotkeys()

    def on_hotkey(self, hotkey_id):
        if hotkey_id == HOTKEY_SPACE:
            self.play_or_resume()
        elif hotkey_id == HOTKEY_ESC:
            self.stop_all()
        elif hotkey_id == HOTKEY_LEFT:
            self.adjust_speed(-SPEED_STEP)
        elif hotkey_id == HOTKEY_RIGHT:
            self.adjust_speed(SPEED_STEP)
        elif hotkey_id == HOTKEY_UP:
            self.play_prev()
        elif hotkey_id == HOTKEY_DOWN:
            self.play_next()
        elif hotkey_id == HOTKEY_0:
            self.combo_mode.setCurrentIndex(0)
        elif hotkey_id == HOTKEY_1:
            self.combo_mode.setCurrentIndex(1)
        elif hotkey_id == HOTKEY_2:
            self.combo_mode.setCurrentIndex(2)

    def closeEvent(self, event):
        self.unregister_hotkeys()
        if self.hotkey_filter:
            QCoreApplication.instance().removeNativeEventFilter(self.hotkey_filter)
        if self._pending_switch_timer.isActive():
            self._pending_switch_timer.stop()
        # 先停止后台线程，避免 QThread 在运行中被销毁导致程序崩溃/退出卡死
        if self.like_worker:
            self.like_worker.stop_like()
            self._stop_thread(self.like_worker)
            self.like_worker = None
        if self.worker:
            self.worker.stop_play()
            self._stop_thread(self.worker)
            self.worker = None
        self.stop_gmaut_bridge()
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'adb.exe':
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except ImportError:
            try:
                import subprocess
                subprocess.run(
                    ['taskkill', '/F', '/IM', 'adb.exe'],
                    capture_output=True,
                    creationflags=0x08000000,
                    timeout=5
                )
            except Exception:
                pass
        except Exception:
            pass
        super().closeEvent(event)

    def select_game_window(self):
        titles = get_all_visible_window_titles()
        if not titles:
            Toast.show_message("未检测到游戏进程", self)
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("选择游戏进程")
        dlg.resize(310, 550)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(4, 8, 4, 12)
        lay.setSpacing(6)
        lst = QListWidget()
        lst.addItems(titles)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        font = QFont("Microsoft YaHei", 8)
        lst.setFont(font)
        lst.setStyleSheet("""
            QListWidget {
                border: none;
                background: #2b2b2b;
                outline: none;
            }
            QListWidget::item {
                padding: 2px 4px;
                border: none;
                height: 18px;
            }
            QListWidget::item:hover {
                color: #ffdd44;
                background: #3a3a3a;
            }
            QScrollBar:vertical {
                width: 6px;
                background: #3a3a3a;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #6a6a6a;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # 双击直接选择
        lst.itemDoubleClicked.connect(lambda: dlg.accept())
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_cancel = btns.button(QDialogButtonBox.Cancel)
        btn_ok = btns.button(QDialogButtonBox.Ok)
        btn_cancel.setText("取消")
        btn_ok.setText("确认")

        # 取消按钮样式（灰色）
        btn_cancel.setStyleSheet("""
            QPushButton {
                font-size: 8pt;
                padding: 6px 20px;
                min-width: 106px;
                background-color: #4a4a4a;
                color: #c0c0c0;
                border: 1px solid #5a5a5a;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)

        # 确认按钮样式（绿色）
        btn_ok.setStyleSheet("""
            QPushButton {
                font-size: 8pt;
                padding: 6px 20px;
                min-width: 106px;
                background-color: #2a7a2a;
                color: white;
                font-weight: bold;
                border: 1px solid #3a9a3a;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #3a9a3a;
            }
            QPushButton:pressed {
                background-color: #1a5a1a;
            }
        """)

        lay.addWidget(lst)
        lay.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        parent_geo = self.geometry()
        dlg.move(
            parent_geo.x() + (parent_geo.width() - 310) // 2,
            parent_geo.y() + (parent_geo.height() - 450) // 2 - 80
        )

        if dlg.exec():
            item = lst.currentItem()
            if item:
                self.edit_target_win.setText(item.text())
                self.game_selected = True
                self.update_game_selection_status()
                self.update_hotkey_registration()

    def check_game_focus(self):
        if self.output_mode == "adb" or self.output_mode == "adb_like":
            return
        if not self.worker or not self.worker.isRunning():
            return
        target = self.edit_target_win.text().strip()
        if not target or "请选择" in target:
            return
        active_win = get_foreground_window_title()
        game_focused = target in active_win
        if game_focused:
            if self.auto_paused and self.worker.paused:
                self.worker.resume_play()
                self.auto_paused = False
                self.set_base_state("弹奏中")
        else:
            if not self.worker.paused:
                self.worker.pause_play()
                self.auto_paused = True
                self.set_base_state("已暂停")
        self.update_hotkey_registration()

    def update_game_selection_status(self):
        if self.output_mode == "adb" or self.output_mode == "adb_like":
            self.game_selected = True
            self.update_status_text()
            return
        target = self.edit_target_win.text().strip()
        if not target or "请选择" in target:
            self.game_selected = False
            self.update_status_text()
        else:
            self.game_selected = True
            self.update_status_text()

    def set_base_state(self, state: str):
        self.base_state = state
        self.update_status_text()

    def update_status_text(self):
        if self.output_mode == "adb":
            self.label_status.setStyleSheet("font-size:9pt;color:#88ccff;")
            prefix = "ADB模式 - "
            loop_map = {LOOP_NONE: "", LOOP_SINGLE: "单循", LOOP_ALL: "列循"}
            loop_txt = loop_map[self.loop_mode]
            if loop_txt:
                status_text = f"{prefix}{loop_txt} - {self.base_state}"
            else:
                status_text = f"{prefix}{self.base_state}"
            self.label_status.setText(status_text)
            return
        elif self.output_mode == "adb_like":
            self.label_status.setStyleSheet("font-size:9pt;color:#88ccff;")
            prefix = "ADB点赞 - "
            loop_map = {LOOP_NONE: "", LOOP_SINGLE: "单循", LOOP_ALL: "列循"}
            loop_txt = loop_map[self.loop_mode]
            if loop_txt:
                status_text = f"{prefix}{loop_txt} - {self.base_state}"
            else:
                status_text = f"{prefix}{self.base_state}"
            self.label_status.setText(status_text)
            return

        if not self.game_selected:
            self.label_status.setStyleSheet("font-size:9pt;color:#ff4444;")
            self.label_status.setText("PC模式请选择游戏进程")
            return

        self.label_status.setStyleSheet("font-size:9pt;color:#88ccff;")
        prefix = ""
        loop_map = {LOOP_NONE: "", LOOP_SINGLE: "单循", LOOP_ALL: "列循"}
        loop_txt = loop_map[self.loop_mode]
        if loop_txt:
            status_text = f"{prefix}{loop_txt} - {self.base_state}"
        else:
            status_text = f"{prefix}{self.base_state}"
        self.label_status.setText(status_text)

    # ==============================================================
    # ---------- 修改：load_default_dir 优先读取保存的路径 ----------
    # ==============================================================
    def load_default_dir(self):
        # 1. 优先读取保存过的路径
        saved_path = self.settings.value("music_directory", "")
        if saved_path and os.path.isdir(saved_path):
            self.music_lib.set_directory(saved_path)
            self.edit_music_dir.setText(saved_path)
            self.refresh_list()
            self.update_game_selection_status()
            if self.game_selected:
                self.set_base_state("就绪")
            return

        # 2. 其次尝试硬编码的 DEFAULT_DIRS
        for p in DEFAULT_DIRS:
            if os.path.isdir(p):
                self.music_lib.set_directory(p)
                self.edit_music_dir.setText(p)
                self.refresh_list()
                self.update_game_selection_status()
                if self.game_selected:
                    self.set_base_state("就绪")
                return

        # 3. 都失败，提示用户选择
        self.set_base_state("请选择乐谱目录")
        self.update_game_selection_status()

    # ==============================================================
    # ---------- choose_dir 选择后立即保存 ----------
    # ==============================================================
    def choose_dir(self):
        cur = self.edit_music_dir.text().strip()
        start = cur if (cur and os.path.isdir(cur)) else DEFAULT_DIRS[0]
        path = QFileDialog.getExistingDirectory(self, "选择乐谱文件夹", start)
        if path:
            self.music_lib.set_directory(path)
            self.edit_music_dir.setText(path)
            self.settings.setValue("music_directory", path)   # 保存
            self.refresh_list()
            self.update_game_selection_status()
            if self.game_selected:
                self.set_base_state("就绪")

    def refresh_list(self):
        self.all_names = self.music_lib.scan_all()
        self.model.set_names(self.all_names)
        self.proxy_model.setFilterFixedString("")
        cnt = len(self.all_names)
        self.label_list_title.setText(f"🎵{cnt}首")
        self.apply_playing_marker()

    def filter_list(self):
        key = self.edit_search.text().strip()
        self.proxy_model.setFilterFixedString(key)
        cnt = self.proxy_model.rowCount()
        self.label_list_title.setText(f"🎵{cnt}首")
        self.apply_playing_marker()

    def search_and_refresh(self):
        self.refresh_list()

    def get_selected_name(self):
        idx = self.list_music.currentIndex()
        if idx.isValid():
            return self.proxy_model.data(idx, Qt.DisplayRole)
        return None

    def double_play(self):
        self.start_play()

    def pause_play(self):
        if self.worker and self.worker.isRunning() and not self.worker.paused:
            self.worker.pause_play()
            self.auto_paused = False
            self.set_base_state("已暂停")
            self.btn_play.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.update_hotkey_registration()

    def play_or_resume(self):
        # ADB点赞模式：启动/停止点赞循环
        if self.output_mode == "adb_like":
            if self.like_worker and self.like_worker.isRunning():
                # 停止点赞
                self.like_worker.stop_like()
                self._stop_thread(self.like_worker)
                self.like_worker = None
                self.set_base_state("已停止")
                self.btn_play.setEnabled(True)
                self.btn_pause.setEnabled(False)
                self.btn_stop.setEnabled(False)
            else:
                # 启动点赞
                self.like_worker = LikeWorker()
                self.like_worker.sig_error.connect(self.on_like_error)
                self.like_worker.start()
                self.set_base_state("点赞中")
                self.btn_play.setEnabled(False)
                self.btn_pause.setEnabled(False)
                self.btn_stop.setEnabled(True)
            return

        if self.output_mode == "pc":
            target = self.edit_target_win.text().strip()
            if not target or "请选择" in target:
                Toast.show_message("请先选择游戏进程", self)
                return
        if self.worker and self.worker.isRunning():
            if self.worker.paused:
                self.worker.resume_play()
                self.auto_paused = False
                self.set_base_state("弹奏中")
                self.btn_play.setEnabled(False)
                self.btn_pause.setEnabled(True)
                self.btn_stop.setEnabled(True)
                self.update_hotkey_registration()
            else:
                self.worker.pause_play()
                self.auto_paused = False
                self.set_base_state("已暂停")
                self.btn_play.setEnabled(True)
                self.btn_pause.setEnabled(False)
                self.btn_stop.setEnabled(True)
                self.update_hotkey_registration()
        else:
            self.start_play()

    def start_play(self, target_name=None):
        if self._pending_switch_timer.isActive():
            self._pending_switch_timer.stop()
        self._pending_target_name = None
        self.loop_play_timer.stop()
        try:
            self.loop_play_timer.timeout.disconnect()
        except (TypeError, RuntimeError):
            pass
        if self.output_mode == "adb_like":
            Toast.show_message("点赞模式请点 ▶ 或按空格启动点赞", self)
            return
        name = target_name or self.get_selected_name()
        if not name:
            Toast.show_message("请选择要播放的曲目", self)
            return
        if self.output_mode == "pc":
            target = self.edit_target_win.text().strip()
            if not target or "请选择" in target:
                Toast.show_message("请先选择游戏进程", self)
                return
        info = self.music_lib.get_info(name)
        if not info:
            Toast.show_message("乐谱解析失败", self)
            return
        ev_list = None
        # 检查 music_data 是否已经是 JSON 字符串（以 '[' 开头）
        if info.music_data.startswith('['):
            ev_list = parse_event_list(info.music_data)
        else:
            # 未解析，现场解析
            parser = ParserFactory.get_parser(info.file_path)
            if parser:
                parsed_info = parser.parse(info.file_path)
                if parsed_info:
                    ev_list = parse_event_list(parsed_info.music_data)
                    # 缓存解析结果，下次直接使用
                    info.music_data = parsed_info.music_data
                    self.music_lib.cache[info.name] = info  # 更新缓存
        if not ev_list:
            Toast.show_message("无有效音符", self)
            return
        self.current_music_name = name
        self.label_current.setText(name)
        self.playing_name = name
        self.apply_playing_marker()

        self.stop_all(keep_loop_mode=True)
        self.event_list = ev_list
        self.total_ms = sum(e.delay for e in ev_list)

        self.worker = PlayWorker(self.event_list, self.total_ms)
        if self.gmaut_bridge is not None:
            self.worker.enable_bridge = False
        self.worker.speed = float(self.label_speed.text()[:-1])
        self.worker.set_mode(self.combo_mode.currentIndex())
        self.worker.set_output_mode(self.output_mode)
        self.worker.sig_progress.connect(self.on_progress)
        self.worker.sig_finish.connect(self.on_play_end)
        self.worker.sig_status.connect(self.on_status_changed)
        self.worker.sig_error.connect(self.on_error)
        self.worker.set_music_meta(name, self._get_source_names_list())
        self.worker.sig_remote_toggle.connect(self.play_or_resume, Qt.QueuedConnection)
        self.worker.sig_remote_prev.connect(self.play_prev, Qt.QueuedConnection)
        self.worker.sig_remote_next.connect(self.play_next, Qt.QueuedConnection)
        self.worker.sig_remote_select.connect(self.start_play, Qt.QueuedConnection)
        self.worker.sig_remote_speed.connect(self.set_remote_speed, Qt.QueuedConnection)

        self.slider_progress.setEnabled(True)
        self.btn_play.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.chk_loop_single.setEnabled(True)
        self.chk_loop_all.setEnabled(True)

        self.chk_loop_single.blockSignals(True)
        self.chk_loop_all.blockSignals(True)
        if self.loop_mode == LOOP_SINGLE:
            self.chk_loop_single.setChecked(True)
            self.chk_loop_all.setChecked(False)
        elif self.loop_mode == LOOP_ALL:
            self.chk_loop_single.setChecked(False)
            self.chk_loop_all.setChecked(True)
        else:
            self.chk_loop_single.setChecked(False)
            self.chk_loop_all.setChecked(False)
        self.chk_loop_single.blockSignals(False)
        self.chk_loop_all.blockSignals(False)

        self.worker.start()
        self.set_base_state("弹奏中")
        self.auto_paused = False
        self.update_hotkey_registration()

    def on_status_changed(self, s):
        if s == "弹奏中":
            self.set_base_state("弹奏中")
        elif s == "已终止":
            self.set_base_state("已终止")
        else:
            self.set_base_state(s)

    @Slot(str)
    def on_like_error(self, msg):
        self.label_status.setText(f"错误：{msg}")
        if self.like_worker:
            self.like_worker.stop_like()
            self._stop_thread(self.like_worker)
            self.like_worker = None
        self.btn_play.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.set_base_state("点赞失败")

    def set_loop_mode(self, mode):
        self.loop_mode = mode
        self.chk_loop_single.blockSignals(True)
        self.chk_loop_all.blockSignals(True)
        if mode == LOOP_SINGLE:
            self.chk_loop_single.setChecked(True)
            self.chk_loop_all.setChecked(False)
        elif mode == LOOP_ALL:
            self.chk_loop_single.setChecked(False)
            self.chk_loop_all.setChecked(True)
        else:
            self.chk_loop_single.setChecked(False)
            self.chk_loop_all.setChecked(False)
        self.chk_loop_single.blockSignals(False)
        self.chk_loop_all.blockSignals(False)
        self.update_status_text()

    @Slot(int, str)
    def on_progress(self, pct, timetxt):
        if not self.slider_progress.isSliderDown():
            if abs(self.slider_progress.value() - pct) >= 1:
                self.slider_progress.setValue(pct)
        self.label_time.setText(timetxt)

    @Slot(object)
    def on_play_end(self, worker):
        if worker is not self.worker:
            return
        self.btn_play.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.slider_progress.setValue(100)
        self.update_hotkey_registration()
        try:
            self.loop_play_timer.timeout.disconnect()
        except (TypeError, RuntimeError):
            pass
        if self.loop_mode == LOOP_SINGLE:
            self._pending_target_name = self.playing_name
            self._pending_switch_timer.start(100)
        elif self.loop_mode == LOOP_ALL:
            source_names = self._get_source_names_list()
            target_name = None
            if source_names and self.playing_name:
                try:
                    idx_in_source = source_names.index(self.playing_name)
                except ValueError:
                    idx_in_source = -1
                if idx_in_source >= 0:
                    if idx_in_source >= len(source_names) - 1:
                        target_name = source_names[0]
                    else:
                        target_name = source_names[idx_in_source + 1]
                    proxy_row = self._find_proxy_row_by_name(target_name)
                    if proxy_row >= 0:
                        self.list_music.setCurrentIndex(self.proxy_model.index(proxy_row, 0))
            self._pending_target_name = target_name
            self._pending_switch_timer.start(100)
        else:
            self.playing_name = None
            self.apply_playing_marker()
            self.set_base_state("播放完毕")

    @Slot(str)
    def on_error(self, msg):
        self.label_status.setText(f"错误：{msg}")
        self.stop_all()

    def stop_all(self, keep_loop_mode=False):
        # 停止点赞循环
        if self.like_worker:
            self.like_worker.stop_like()
            self._stop_thread(self.like_worker)
            self.like_worker = None
            self.btn_play.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            if not keep_loop_mode:
                self.set_base_state("已停止")
            return

        if self._pending_switch_timer.isActive():
            self._pending_switch_timer.stop()
        self._pending_target_name = None
        self.loop_play_timer.stop()
        try:
            self.loop_play_timer.timeout.disconnect()
        except (TypeError, RuntimeError):
            pass
        if self.worker:
            try:
                self.worker.sig_finish.disconnect(self.on_play_end)
            except TypeError:
                pass
            for signal, slot in (
                (self.worker.sig_remote_toggle, self.play_or_resume),
                (self.worker.sig_remote_prev, self.play_prev),
                (self.worker.sig_remote_next, self.play_next),
                (self.worker.sig_remote_select, self.start_play),
                (self.worker.sig_remote_speed, self.set_remote_speed),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            self.worker.stop_play()
            self._stop_thread(self.worker)
            self.worker = None
        self.btn_play.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.slider_progress.setEnabled(False)
        self.slider_progress.setValue(0)
        self.label_time.setText("00:00 / 00:00")
        self.event_list.clear()
        self.total_ms = 0
        if not keep_loop_mode:
            self.current_music_name = None
            self.loop_mode = LOOP_NONE
            self.chk_loop_single.blockSignals(True)
            self.chk_loop_all.blockSignals(True)
            self.chk_loop_single.setChecked(False)
            self.chk_loop_all.setChecked(False)
            self.chk_loop_single.blockSignals(False)
            self.chk_loop_all.blockSignals(False)
            self.set_base_state("已终止")
            self.label_current.setText("")
            self.playing_name = None
            self.apply_playing_marker()
        self.auto_paused = False
        self.update_hotkey_registration()

    def jump_slider(self):
        if not self.worker or not self.event_list:
            return
        val = self.slider_progress.value()
        target_ms = int(self.total_ms * val / 100)
        acc = 0
        idx = 0
        for i, ev in enumerate(self.event_list):
            acc += ev.delay
            if acc >= target_ms:
                idx = i
                break
        self.worker.jump_to_index(idx)
        if self.worker.paused:
            self.worker.resume_play()
        pct = int(target_ms * 100 / self.total_ms) if self.total_ms else 0
        t = f"{self.worker.format_ms(target_ms)} / {self.worker.format_ms(self.total_ms)}"
        self.on_progress(pct, t)
        self.update_hotkey_registration()

    def adjust_speed(self, delta):
        try:
            old = float(self.label_speed.text()[:-1])
            new = round(old + delta, 2)
            new = max(SPEED_MIN, min(SPEED_MAX, new))
            self.label_speed.setText(f"{new:.2f}x")
            if self.worker:
                self.worker.set_speed(new)
        except:
            self.label_speed.setText("1.00x")

    def set_remote_speed(self, speed):
        try:
            new = max(SPEED_MIN, min(SPEED_MAX, float(speed)))
            self.label_speed.setText(f"{new:.2f}x")
            if self.worker:
                self.worker.set_speed(new)
        except Exception:
            pass

    def start_auto_speed(self, delta):
        self.auto_speed_timer = QTimer()
        self.auto_speed_timer.setInterval(50)
        self.auto_speed_timer.timeout.connect(lambda: self.adjust_speed(delta))
        self.auto_speed_timer.start()

    def stop_auto_speed(self):
        if self.auto_speed_timer:
            self.auto_speed_timer.stop()
            self.auto_speed_timer = None

    def _find_proxy_row_by_name(self, name):
        for row in range(self.proxy_model.rowCount()):
            idx = self.proxy_model.index(row, 0)
            if self.proxy_model.data(idx, Qt.DisplayRole) == name:
                return row
        return -1

    def _get_source_names_list(self):
        return list(self.model._names)

    def _on_pending_switch_timeout(self):
        target = self._pending_target_name
        self._pending_target_name = None
        self.start_play(target)

    def play_prev(self):
        source_names = self._get_source_names_list()
        if not source_names:
            return
        current_name = self.playing_name
        if not current_name:
            current_name = self.get_selected_name()
        if not current_name:
            return
        try:
            idx_in_source = source_names.index(current_name)
        except ValueError:
            idx_in_source = self.list_music.currentIndex().row()
        if idx_in_source <= 0:
            target_name = source_names[-1]
        else:
            target_name = source_names[idx_in_source - 1]
        proxy_row = self._find_proxy_row_by_name(target_name)
        if proxy_row >= 0:
            self.list_music.setCurrentIndex(self.proxy_model.index(proxy_row, 0))
        self.start_play(target_name)

    def play_next(self):
        source_names = self._get_source_names_list()
        if not source_names:
            return
        current_name = self.playing_name
        if not current_name:
            current_name = self.get_selected_name()
        if not current_name:
            return
        try:
            idx_in_source = source_names.index(current_name)
        except ValueError:
            idx_in_source = self.list_music.currentIndex().row()
        if idx_in_source >= len(source_names) - 1:
            target_name = source_names[0]
        else:
            target_name = source_names[idx_in_source + 1]
        proxy_row = self._find_proxy_row_by_name(target_name)
        if proxy_row >= 0:
            self.list_music.setCurrentIndex(self.proxy_model.index(proxy_row, 0))
        self.start_play(target_name)

    def show_question(self, title, text):
        dlg = CustomQuestionDialog(title, text, self)
        return dlg.exec() == QDialog.Accepted

    def delete_item(self):
        name = self.get_selected_name()
        if not name:
            Toast.show_message("请选择要删除的曲目", self)
            return
        if self.show_question("确认删除", f"确定删除乐谱？无法恢复哦\n\n【{name}】\n"):
            if name == self.playing_name:
                self.stop_all()
            if self.music_lib.delete_music(name):
                self.refresh_list()
                Toast.show_message("删除完成", self)
            else:
                Toast.show_message("文件删除失败", self)

    def rename_item(self):
        name = self.get_selected_name()
        if not name:
            Toast.show_message("请选择要重命名的曲目", self)
            return
        dlg = CustomInputDialog("重命名", "重命名，不含后缀", name, self)
        if dlg.exec() == QDialog.Accepted:
            new = dlg.get_text().strip()
            if not new:
                Toast.show_message("名称不能为空", self)
                return
            if new == name:
                Toast.show_message("名称未修改", self)
                return
            if self.music_lib.rename_music(name, new):
                if name == self.playing_name:
                    self.playing_name = new
                self.refresh_list()
                # 重新选中新名称
                for i in range(self.proxy_model.rowCount()):
                    idx = self.proxy_model.index(i, 0)
                    if idx.data(Qt.DisplayRole) == new:
                        self.list_music.setCurrentIndex(idx)
                        break
                Toast.show_message("重命名完成", self)
            else:
                Toast.show_message("重命名失败，被占用或无权限", self)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)

    # 全局样式
    input_dialog_style = """
    QInputDialog {
        background: #2b2b2b;
        border: 2px solid #6a6a6a;
        border-radius: 12px;
    }
    QInputDialog QLabel {
        color: #d0d0d0;
        font-size: 10pt;
        padding: 4px 8px;
    }
    QInputDialog QLineEdit {
        background: #3b3b3b;
        color: #d0d0d0;
        border: 1px solid #5a5a5a;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 10pt;
    }
    QInputDialog QLineEdit:focus {
        border-color: #4b6eb9;
    }
    QInputDialog QPushButton {
        background: #4a4a4a;
        border: 1px solid #5a5a5a;
        border-radius: 6px;
        padding: 6px 20px;
        color: #d0d0d0;
        font-size: 9pt;
        min-width: 80px;
        min-height: 28px;
    }
    QInputDialog QPushButton:hover {
        background: #5a5a5a;
        border-color: #7a7a7a;
    }
    QInputDialog QPushButton:default {
        background: #2a7a2a;
        color: white;
        border-color: #3a9a3a;
    }
    QInputDialog QPushButton:default:hover {
        background: #3a9a3a;
    }
    """

    dark_style = """
    QWidget {
        background: #2b2b2b;
        color: #a9b7c6;
        font-size: 10pt;
        font-family: "Microsoft YaHei","Segoe UI",sans-serif;
    }
    QPushButton {
        background: #3b3b3b;
        border: 0px solid #4a4a4a;
        border-radius: 4px;
        padding: 2px 6px;
        color: #a9b7c6;
    }
    QPushButton:hover {
        background: #4b4b4b;
        border-color: #5a5a5a;
    }
    QPushButton:pressed {
        background: #2b2b2b;
    }
    QPushButton:disabled {
        background: #2b2b2b;
        color: #555555;
        border-color: #3a3a3a;
    }
    QLineEdit {
        background: #3b3b3b;
        border: 1px solid #4a4a4a;
        border-radius: 4px;
        padding: 2px 6px;
        color: #a9b7c6;
        font-size: 9pt;
    }
    QLineEdit:focus {
        border-color: #4b6eb9;
        outline: none;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #3b3b3b;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        width: 12px;
        height: 12px;
        margin: -4px 0;
        background: #4b6eb9;
        border-radius: 6px;
    }
    QSlider::handle:horizontal:hover {
        background: #5a8ab5;
    }
    QSlider::sub-page:horizontal {
        background: #4b6eb9;
        border-radius: 2px;
    }
    QDialog {
        background: #2b2b2b;
        color: #a9b7c6;
    }
    QInputDialog QLineEdit {
        background: #3b3b3b;
        color: #a9b7c6;
    }
    QCheckBox {
        color: #a9b7c6;
        spacing: 4px;
    }
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        background: #3b3b3b;
        border: 1px solid #4a4a4a;
        border-radius: 2px;
    }
    QToolTip {
        color: #a9b7c6;
        background: #2b2b2b;
        border: 1px solid #4a4a4a;
    }
    QMessageBox {
        background: #2b2b2b;
        border: 1px solid #4a4a4a;
        border-radius: 8px;
    }
    QMessageBox QLabel {
        color: #a9b7c6;
        font-size: 10pt;
        padding: 6px;
    }
    QMessageBox QPushButton {
        background: #3b3b3b;
        border: 1px solid #4a4a4a;
        border-radius: 4px;
        padding: 5px 16px;
        color: #a9b7c6;
        font-size: 9pt;
        min-width: 70px;
    }
    QMessageBox QPushButton:hover {
        background: #4b4b4b;
        border-color: #5a5a5a;
    }
    QMessageBox QPushButton:default {
        background: #4b6eb9;
        color: white;
        border-color: #4b6eb9;
    }
    QInputDialog {
        background: #2b2b2b;
        border: 1px solid #4a4a4a;
        border-radius: 8px;
    }
    QInputDialog QLabel {
        color: #a9b7c6;
        font-size: 10pt;
    }
    QInputDialog QLineEdit {
        background: #3b3b3b;
        color: #a9b7c6;
        border: 1px solid #4a4a4a;
        border-radius: 4px;
        padding: 4px;
    }
    QInputDialog QPushButton {
        background: #3b3b3b;
        border: 1px solid #4a4a4a;
        border-radius: 4px;
        padding: 5px 16px;
        color: #a9b7c6;
        font-size: 9pt;
        min-width: 70px;
    }
    QInputDialog QPushButton:hover {
        background: #4b4b4b;
    }
    QInputDialog QPushButton:default {
        background: #4b6eb9;
        color: white;
        border-color: #4b6eb9;
    }
    QDialogButtonBox QPushButton[role="AcceptRole"] {
        background: #2a7a2a;
        color: white;
        border: 1px solid #3a9a3a;
        border-radius: 4px;
        padding: 5px 16px;
        font-size: 9pt;
        min-width: 70px;
    }
    QDialogButtonBox QPushButton[role="AcceptRole"]:hover {
        background: #3a9a3a;
    }
    QDialogButtonBox QPushButton[role="AcceptRole"]:pressed {
        background: #1a5a1a;
    }
    QDialogButtonBox QPushButton[role="RejectRole"] {
        background: #4a4a4a;
        color: #c0c0c0;
        border: 1px solid #5a5a5a;
        border-radius: 4px;
        padding: 5px 16px;
        font-size: 9pt;
        min-width: 70px;
    }
    QDialogButtonBox QPushButton[role="RejectRole"]:hover {
        background: #5a5a5a;
    }
    QDialogButtonBox QPushButton[role="RejectRole"]:pressed {
        background: #3a3a3a;
    }
    """

    app.setStyleSheet(dark_style + input_dialog_style)

    # 授权检查：未激活 / 机器码不匹配 / 过期 / 无效时弹出激活窗口
    if ENABLE_LICENSE:
        from license import LicenseStatus, check_license
        from license.activation_dialog import show_activation_dialog

        license_status, _ = check_license()
        if license_status != LicenseStatus.OK:
            if not show_activation_dialog(license_status):
                sys.exit(0)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
