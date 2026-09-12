# utils/adb_touch.py
"""ADB 触摸输出模块。

注意：ADB 命令一律不允许无限期阻塞调用方。
- 需要输出的命令使用 run_adb()（带超时 + 进程树清理）；
- 点击命令使用 Popen 直接投递，不等待、不捕获输出。

原因：adb.exe 会派生一个常驻 server 进程，若 server 继承了调用方的 stdout/stderr
管道，即使 client 超时被杀，管道也永远不会有 EOF，subprocess.run 会无限期挂起，
进而卡死 GUI 线程或让后台线程越积越多。
"""

import os
import random
import socket
import subprocess

from utils.resource import get_adb_path

# Windows 下禁止创建新控制台窗口的标志
if os.name == 'nt':
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


def _popen(args, capture=False):
    """创建 ADB 子进程。capture=True 时捕获输出，否则完全丢弃输出。"""
    kwargs = {"stdin": subprocess.DEVNULL}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.Popen(args, **kwargs)


def _kill_process_tree(pid):
    """Windows 下连子进程一起杀掉，防止孤儿进程继续持有管道。"""
    if os.name != "nt" or pid is None:
        return
    try:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": 5,
            "creationflags": CREATE_NO_WINDOW,
        }
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], **kwargs)
    except Exception:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def _kill_server(adb_cmd):
    """清理 adb server（输出重定向，带超时）。"""
    try:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": 5,
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        subprocess.run([adb_cmd, "kill-server"], **kwargs)
    except Exception:
        pass


def _server_port_open():
    """探测本地 5037 端口是否有进程监听（不触发 adb 自动启动 server）。"""
    try:
        s = socket.create_connection(("127.0.0.1", 5037), timeout=0.3)
        s.close()
        return True
    except OSError:
        return False


def _server_healthy(adb_cmd):
    """adb server 是否可用：端口在听且 client 能正常通信。"""
    if not _server_port_open():
        return False
    rc, _ = run_adb(adb_cmd, ["devices"], timeout=3)
    return rc is not None


def start_adb_server(adb_cmd):
    """确保 adb server 可用，且不让它继承调用方的管道。

    关键：先单独把 server 拉起来，后续 client 命令就不会有
    “server 握着管道导致读取永久挂起”的问题。
    已有健康 server 时直接返回；server 缺失或损坏时清理并重启。
    首次启动可能较慢（杀软扫描/冷启动），超时放宽到 12 秒。
    """
    # 快路径：server 已健康，直接返回（避免每次启动都等数秒）
    if _server_healthy(adb_cmd):
        return

    # 清理可能残留的半启动/损坏 server，再启动
    _kill_server(adb_cmd)
    try:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": 12,
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        subprocess.run([adb_cmd, "start-server"], **kwargs)
    except Exception:
        pass

    # 启动后确认一次，避免半启动状态
    if not _server_healthy(adb_cmd):
        _kill_server(adb_cmd)
        try:
            kwargs["timeout"] = 12
            subprocess.run([adb_cmd, "start-server"], **kwargs)
        except Exception:
            pass


def run_adb(adb_cmd, args, timeout=3, serial=None):
    """执行需要输出的 ADB 命令，带超时和进程树清理。

    返回 (returncode, 输出文本)；超时返回 (None, "")。
    """
    proc = None
    try:
        cmd = [adb_cmd]
        if serial:
            cmd += ["-s", serial]
        cmd += list(args)
        proc = _popen(cmd, capture=True)
        out, err = proc.communicate(timeout=timeout)
        text = ""
        if out:
            text += out.decode("utf-8", errors="replace")
        if err:
            text += err.decode("utf-8", errors="replace")
        return proc.returncode, text.strip()
    except subprocess.TimeoutExpired:
        if proc is not None:
            _kill_process_tree(proc.pid)
            try:
                proc.communicate(timeout=2)
            except Exception:
                pass
        return None, ""
    except Exception:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return None, ""


def tap(adb_cmd, x, y, serial=None):
    """发一次点击：Popen 投递后立即返回，不等待、不捕获，绝不可能阻塞。"""
    try:
        cmd = [adb_cmd]
        if serial:
            cmd += ["-s", serial]
        cmd += ["shell", "input", "tap", str(int(x)), str(int(y))]
        _popen(cmd)
    except Exception:
        pass


class ADBTouch:
    # coord_map 标定所用的基准分辨率
    BASE_WIDTH = 1080
    BASE_HEIGHT = 2376

    def __init__(self, serial=None):
        self.adb_cmd = self._find_adb()
        start_adb_server(self.adb_cmd)
        self.serial = serial or self._detect_serial()
        if self.serial is None:
            raise RuntimeError("未检测到已连接的 ADB 设备")
        self._connect()
        self.width, self.height = self._get_screen_size()
        self._setup_coords()

    def _find_adb(self):
        """查找 ADB 可执行文件"""
        adb_name = "adb.exe" if os.name == "nt" else "adb"

        # 使用统一的资源路径工具
        try:
            adb_path = get_adb_path()
            if os.path.exists(adb_path):
                return adb_path
        except Exception:
            pass

        # 系统 PATH
        for path in os.environ["PATH"].split(os.pathsep):
            full = os.path.join(path, adb_name)
            if os.path.exists(full):
                return full

        # 兜底
        return "adb"

    def _detect_serial(self):
        """选择一个已经处于 device 状态的设备，优先使用无线连接。"""
        try:
            ok, out = run_adb(self.adb_cmd, ["devices"], timeout=3)
            if ok != 0:
                return None
            wireless = []
            usb = []
            for line in (out or "").splitlines():
                parts = line.split()
                if len(parts) < 2 or parts[1] != "device":
                    continue
                if ":" in parts[0]:
                    wireless.append(parts[0])
                else:
                    usb.append(parts[0])
            return wireless[0] if wireless else (usb[0] if usb else None)
        except Exception:
            return None

    def _connect(self):
        try:
            rc, out = run_adb(
                self.adb_cmd,
                ["shell", "settings", "get", "system", "user_rotation"],
                timeout=2,
                serial=self.serial,
            )
            if rc == 0 and out.strip().isdigit():
                self.rotation = int(out.strip())
            else:
                self.rotation = 1
        except Exception:
            self.rotation = 1

    def _get_screen_size(self):
        """通过 adb wm size 获取真实屏幕分辨率，失败回退基准分辨率"""
        rc, out = run_adb(
            self.adb_cmd,
            ["shell", "wm", "size"],
            timeout=2,
            serial=self.serial,
        )
        try:
            override = phys = None
            for line in (out or "").splitlines():
                if 'Override size:' in line:
                    override = line.split('Override size:')[1].strip()
                elif 'Physical size:' in line:
                    phys = line.split('Physical size:')[1].strip()
            size_str = override or phys
            if size_str and 'x' in size_str:
                w, h = size_str.split('x')
                return int(w), int(h)
        except Exception:
            pass
        return self.BASE_WIDTH, self.BASE_HEIGHT

    def _setup_coords(self):
        base_coords = {
            "C4": (550, 1750), "D4": (550, 1550), "E4": (550, 1350),
            "F4": (550, 1180), "G4": (550, 980),  "A5": (550, 800),
            "B5": (550, 600),
            "C3": (750, 1750), "D3": (750, 1550), "E3": (750, 1350),
            "F3": (750, 1180), "G3": (750, 980),  "A4": (750, 800),
            "B4": (750, 600),
            "C2": (950, 1750), "D2": (950, 1550), "E2": (950, 1350),
            "F2": (950, 1180), "G2": (950, 980),  "A3": (950, 800),
            "B3": (950, 600),
        }
        # 按真实分辨率等比缩放
        sx = self.width / self.BASE_WIDTH
        sy = self.height / self.BASE_HEIGHT
        self.coord_map = {
            k: (int(v[0] * sx), int(v[1] * sy)) for k, v in base_coords.items()
        }

    def get_coord(self, note_name):
        return self.coord_map.get(note_name)

    def press_notes(self, notes, duration_ms):
        for note in notes:
            coord = self.get_coord(note)
            if coord is None:
                continue
            x, y = coord

            if self.rotation == 1:
                x_raw = self.height - 1 - y
                y_raw = x
            elif self.rotation == 3:
                x_raw = y
                y_raw = self.width - 1 - x
            else:
                x_raw = self.height - 1 - y
                y_raw = x

            x_raw = max(0, min(self.height - 1, int(x_raw)))
            y_raw = max(0, min(self.width - 1, int(y_raw)))

            tap(self.adb_cmd, x_raw, y_raw, serial=self.serial)

    def random_like_tap(self, base_x=None, base_y=None):
        """在竖屏模式下随机点击屏幕中上部区域（用于点赞）

        参数：
            base_x: 基准X百分比位置（0-1之间）
            base_y: 基准Y百分比位置（0-1之间）

        返回：
            (y_percent, x_percent): 点击的百分比位置
        """
        # 常规点赞区域：高度40%-44%，宽度11%-28%
        if base_x is not None and base_y is not None:
            # 基于上次位置小范围偏移（±3%的屏幕尺寸）
            offset_x_percent = random.uniform(-0.03, 0.03)
            offset_y_percent = random.uniform(-0.03, 0.03)
            x_percent = base_x + offset_x_percent
            y_percent = base_y + offset_y_percent
            # 确保不超出有效范围
            x_percent = max(0.11, min(0.28, x_percent))
            y_percent = max(0.40, min(0.44, y_percent))
        else:
            # 完全随机位置
            y_percent = random.uniform(0.40, 0.44)
            x_percent = random.uniform(0.11, 0.28)

        # 计算竖屏坐标（点赞固定竖屏，不需要rotation转换）
        x_raw = max(0, min(self.width - 1, int(self.width * x_percent)))
        y_raw = max(0, min(self.height - 1, int(self.height * y_percent)))

        # 直接投递点击，不阻塞
        tap(self.adb_cmd, x_raw, y_raw, serial=self.serial)

        return y_percent, x_percent

    def close(self):
        pass

    def __del__(self):
        self.close()
