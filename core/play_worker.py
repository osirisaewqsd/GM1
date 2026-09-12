# core/play_worker.py
from PySide6.QtCore import QThread, Signal
import ctypes
from ctypes import wintypes
import time
from utils.key_mapping import get_key
from core.music_parser import PlayEvent
from utils.adb_touch import ADBTouch
from core.gmaut_bridge import GmautBridge

# 后台弹奏工具，输出adb和pc键盘模式

CHORD_DELAY_MS = 1
BATCH_MAX = 10

KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002

VK_MAP = {
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'z': 0x5A
}

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]

class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

def send_keyboard_events(key_codes, is_down, chord_delay=CHORD_DELAY_MS):
    if not key_codes:
        return
    if not is_down:
        input_arr = (INPUT * len(key_codes))()
        tick = ctypes.windll.kernel32.GetTickCount()
        for i, vk in enumerate(key_codes):
            ki = KEYBDINPUT()
            ki.wVk = vk
            ki.dwFlags = KEYEVENTF_KEYUP
            ki.time = tick
            ki.dwExtraInfo = ctypes.pointer(wintypes.ULONG(0))
            input_arr[i].type = 1
            input_arr[i].union.ki = ki
        ctypes.windll.user32.SendInput(len(key_codes), input_arr, ctypes.sizeof(INPUT))
        return
    tick = ctypes.windll.kernel32.GetTickCount()
    for vk in key_codes:
        input_arr = (INPUT * 1)()
        ki = KEYBDINPUT()
        ki.wVk = vk
        ki.dwFlags = KEYEVENTF_KEYDOWN
        ki.time = tick
        ki.dwExtraInfo = ctypes.pointer(wintypes.ULONG(0))
        input_arr[0].type = 1
        input_arr[0].union.ki = ki
        ctypes.windll.user32.SendInput(1, input_arr, ctypes.sizeof(INPUT))
        if chord_delay > 0:
            ctypes.windll.kernel32.Sleep(chord_delay)

class PlayWorker(QThread):
    sig_progress = Signal(int, str)
    sig_finish = Signal(object)
    sig_status = Signal(str)
    sig_error = Signal(str)
    sig_remote_toggle = Signal()
    sig_remote_prev = Signal()
    sig_remote_next = Signal()
    sig_remote_select = Signal(str)
    sig_remote_speed = Signal(float)

    def __init__(self, event_list: list[PlayEvent], total_ms: int):
        super().__init__()
        self.events = event_list
        self.total_ms = total_ms
        self.stop_flag = False
        self.paused = False
        self.speed = 1.0
        self.cur_index = 0
        self.played_ms = 0
        self.chord_delay = CHORD_DELAY_MS
        self.jump_requested = False
        self.mode = 0
        self.output_mode = "pc"
        self.adb_touch = None
        self.bridge = None
        self.enable_bridge = True
        self.music_name = ""
        self.music_list = []
        self._last_bridge_send = 0.0

    def set_speed(self, val: float):
        self.speed = val
        self._send_bridge_state(force=True)

    def set_music_meta(self, music_name, music_list):
        self.music_name = music_name or ""
        self.music_list = list(music_list or [])

    def set_mode(self, mode: int):
        self.mode = mode

    def set_output_mode(self, mode: str):
        self.output_mode = mode

    def jump_to_index(self, idx: int):
        self.cur_index = max(0, min(idx, len(self.events) - 1))
        self.played_ms = 0
        for i in range(self.cur_index):
            self.played_ms += self.events[i].delay
        self.jump_requested = True
        if self.paused:
            self.resume_play()

    def pause_play(self):
        self.paused = True
        self._send_bridge_state(force=True)

    def resume_play(self):
        self.paused = False
        self._send_bridge_state(force=True)

    def stop_play(self):
        self.stop_flag = True

    def format_ms(self, ms: int) -> str:
        s = ms // 1000
        m = s // 60
        sec = s % 60
        return f"{m:02d}:{sec:02d}"

    def _start_bridge(self, adb_touch):
        if self.output_mode != "adb" or adb_touch is None or not self.enable_bridge:
            return
        try:
            adb_cmd = getattr(adb_touch, "adb_cmd", "adb")
            self.bridge = GmautBridge(
                on_control=self._on_remote_control,
                adb_cmd=adb_cmd,
            )
            self.bridge.start()
            self._send_bridge_state(force=True)
        except Exception:
            self.bridge = None

    def _close_bridge(self):
        if self.bridge is not None:
            self.bridge.close()
            self.bridge = None

    def _send_bridge_state(self, force=False):
        if self.bridge is None:
            return
        now = time.monotonic()
        if not force and (now - self._last_bridge_send) < 0.1:
            return
        self._last_bridge_send = now
        progress = (self.played_ms / self.total_ms) if self.total_ms else 0.0
        songs = [
            {"id": str(index), "title": name}
            for index, name in enumerate(self.music_list)
        ]
        self.bridge.send_state(
            song=self.music_name,
            playing=not self.paused,
            progress=progress,
            position_ms=self.played_ms,
            duration_ms=self.total_ms,
            speed=self.speed,
            songs=songs,
        )

    def _on_remote_control(self, action, value):
        try:
            if action == "toggle":
                self.sig_remote_toggle.emit()
            elif action == "prev":
                self.sig_remote_prev.emit()
            elif action == "next":
                self.sig_remote_next.emit()
            elif action == "select":
                if isinstance(value, int) and 0 <= value < len(self.music_list):
                    self.sig_remote_select.emit(self.music_list[value])
                elif isinstance(value, str) and value:
                    self.sig_remote_select.emit(value)
            elif action == "speed":
                self.sig_remote_speed.emit(float(value))
        except Exception:
            pass

    def run(self):
        self.sig_status.emit("弹奏中")
        self.stop_flag = False
        self.paused = False
        time.sleep(0.2)

        adb_touch = None
        if self.output_mode == "adb":
            try:
                adb_touch = ADBTouch()
                self.adb_touch = adb_touch
                self._start_bridge(adb_touch)
            except Exception as e:
                self.sig_error.emit(f"ADB初始化失败")
                return

        real_total = sum(ev.delay for ev in self.events)
        self.total_ms = real_total
        idx = self.cur_index
        self.played_ms = sum(e.delay for e in self.events[:idx])
        self._send_bridge_state(force=True)
        skip_next = False

        while idx < len(self.events) and not self.stop_flag:
            if self.jump_requested:
                self.jump_requested = False
                idx = self.cur_index
                self.played_ms = sum(e.delay for e in self.events[:idx])
                self._send_bridge_state(force=True)
                if idx >= len(self.events):
                    break

            while self.paused and not self.stop_flag:
                ctypes.windll.kernel32.Sleep(10)
            if self.stop_flag:
                break

            if skip_next:
                ev = self.events[idx]
                self.played_ms += ev.delay
                self.played_ms = min(self.played_ms, self.total_ms)
                final_pct = int(self.played_ms * 100 / self.total_ms) if self.total_ms > 0 else 0
                final_time = f"{self.format_ms(self.played_ms)} / {self.format_ms(self.total_ms)}"
                self.sig_progress.emit(final_pct, final_time)
                self._send_bridge_state(force=True)
                idx += 1
                self.cur_index = idx
                skip_next = False
                continue

            ev = self.events[idx]
            notes_to_play = ev.notes

            if self.mode == 1 and len(notes_to_play) > 1:
                notes_to_play = [notes_to_play[-1]]
            elif self.mode == 2:
                # 模式2：只弹主旋律（八度≥3），跳过低音伴奏组
                melody_notes = [n for n in notes_to_play if n and n[-1].isdigit() and int(n[-1]) >= 3]
                if melody_notes:
                    notes_to_play = [melody_notes[-1]]
                else:
                    # 纯低音伴奏，跳过不弹
                    skip_next = True
                    continue

            # 计算实际等待时间（速度调整）
            real_delay_ms = ev.delay / self.speed

            # ---- 发送按下（ADB 直接发送长按） ----
            self._send_notes(notes_to_play, True, adb_touch, real_delay_ms)

            # 等待音符持续
            start_t = time.perf_counter()
            while True:
                if self.stop_flag or self.paused:
                    break
                elapsed = (time.perf_counter() - start_t) * 1000
                if elapsed >= real_delay_ms:
                    break
                if self.jump_requested:
                    break
                original_elapsed = elapsed * self.speed
                current_play = self.played_ms + int(original_elapsed)
                pct = int(current_play * 100 / self.total_ms) if self.total_ms > 0 else 0
                time_txt = f"{self.format_ms(current_play)} / {self.format_ms(self.total_ms)}"
                self.sig_progress.emit(pct, time_txt)
                self._send_bridge_state()
                ctypes.windll.kernel32.Sleep(1)

            # ---- PC 模式需要显式释放，ADB 模式不需要 ----
            if self.output_mode == "pc":
                self._send_notes(notes_to_play, False, adb_touch, 0)

            if self.jump_requested:
                continue

            self.played_ms += ev.delay
            self.played_ms = min(self.played_ms, self.total_ms)

            final_pct = int(self.played_ms * 100 / self.total_ms) if self.total_ms > 0 else 0
            final_time = f"{self.format_ms(self.played_ms)} / {self.format_ms(self.total_ms)}"
            self.sig_progress.emit(final_pct, final_time)
            self._send_bridge_state(force=True)

            skip_next = False

            idx += 1
            self.cur_index = idx

        if not self.stop_flag:
            self.sig_progress.emit(100, f"{self.format_ms(self.total_ms)} / {self.format_ms(self.total_ms)}")
            self._send_bridge_state(force=True)
            self.sig_finish.emit(self)
        self.sig_status.emit("已终止")

        self._close_bridge()
        if adb_touch:
            adb_touch.close()
            self.adb_touch = None

    def _send_notes(self, notes, is_down, adb_touch=None, duration_ms=0):
        if self.output_mode == "pc":
            key_codes = []
            for note in notes:
                k_char = get_key(note)
                if k_char:
                    vk = VK_MAP.get(k_char.lower())
                    if vk:
                        key_codes.append(vk)
                    else:
                        self.sig_error.emit(f"未知虚拟码: {k_char}")
                else:
                    self.sig_error.emit(f"未知音符: {note}")
            if key_codes:
                send_keyboard_events(key_codes, is_down, self.chord_delay if is_down else 0)
        else:  # ADB
            if adb_touch is None:
                return
            if is_down:
                # 发送长按，duration_ms 是音符时长（毫秒）
                adb_touch.press_notes(notes, int(duration_ms))
            # 释放由 press_notes 内部完成
