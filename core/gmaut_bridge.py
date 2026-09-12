"""GMAUT Android 悬浮遥控与猫之琴之间的 ADB/TCP 桥接。"""

import json
import os
import socket
import threading
import time

from utils.adb_touch import run_adb

HOST = "127.0.0.1"
PORT = 22555


class GmautBridge:
    def __init__(self, on_control=None, adb_cmd="adb"):
        self.on_control = on_control
        self.adb_cmd = adb_cmd
        self.running = False
        self.sock = None
        self.lock = threading.Lock()
        self.connect_thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.connect_thread = threading.Thread(
            target=self._connect_loop, name="GMAUTBridge", daemon=True
        )
        self.connect_thread.start()

    def _connect_loop(self):
        while self.running:
            last_forward_attempt = 0.0
            connected = False
            while self.running and not connected:
                now = time.monotonic()
                if now - last_forward_attempt >= 2.0:
                    last_forward_attempt = now
                    self._run_adb_forward()
                try:
                    sock = socket.create_connection((HOST, PORT), timeout=2)
                    with self.lock:
                        self.sock = sock
                    connected = True
                except OSError:
                    time.sleep(0.5)

            if not self.running:
                break

            self._read_loop()
            self._clear_socket()
            time.sleep(0.5)

    def _run_adb_forward(self):
        try:
            run_adb(
                self.adb_cmd,
                ["forward", f"tcp:{PORT}", f"tcp:{PORT}"],
                timeout=4,
            )
        except Exception:
            pass

    def _read_loop(self):
        buf = b""
        while self.running:
            with self.lock:
                sock = self.sock
            if sock is None:
                break
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line.decode("utf-8", errors="replace"))
        self._clear_socket()

    def _handle_line(self, line):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(obj, dict):
            return
        if obj.get("type") != "control":
            return
        action = obj.get("action")
        value = obj.get("value")
        if self.on_control:
            self.on_control(action, value)

    def send_state(
        self,
        song="",
        playing=False,
        progress=0.0,
        position_ms=0,
        duration_ms=0,
        speed=1.0,
        songs=None,
    ):
        if not self.running:
            return
        if songs is None:
            songs = []
        payload = {
            "type": "state",
            "song": song,
            "playing": bool(playing),
            "progress": max(0.0, min(1.0, float(progress))),
            "positionMs": int(position_ms),
            "durationMs": int(duration_ms),
            "speed": float(speed),
            "songs": songs,
        }
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            with self.lock:
                if self.sock is None:
                    return
                self.sock.sendall(line.encode("utf-8"))
        except OSError:
            self._clear_socket()

    def _clear_socket(self):
        with self.lock:
            if self.sock is not None:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None

    def close(self):
        self.running = False
        self._clear_socket()


if __name__ == "__main__":
    def on_control(action, value):
        print(action, value)

    bridge = GmautBridge(on_control=on_control)
    bridge.start()
    try:
        bridge.send_state(song="测试", duration_ms=120000)
        time.sleep(5)
    finally:
        bridge.close()
