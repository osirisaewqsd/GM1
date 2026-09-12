"""生成本机机器码（绑定 Windows 安装标识 + 硬件特征，无需管理员权限）。"""

import hashlib
import os
import uuid


def _get_machine_guid() -> str:
    """Windows 安装标识，重装系统会变化，正常使用环境非常稳定。"""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except Exception:
        return ""


def _get_volume_serial() -> str:
    """系统盘卷序列号，重装/格式化系统盘会变化。"""
    try:
        import ctypes

        system_drive = os.environ.get("SystemDrive", "C:") + "\\"
        serial = ctypes.c_ulong(0)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetVolumeInformationW(
            system_drive,
            None,
            0,
            ctypes.byref(serial),
            None,
            None,
            None,
            0,
        )
        return format(serial.value & 0xFFFFFFFF, "08X")
    except Exception:
        return ""


def _get_mac_hex() -> str:
    """主网卡 MAC 地址，更换网卡/主板可能变化。"""
    try:
        return format(uuid.getnode() & 0xFFFFFFFFFFFF, "012X")
    except Exception:
        return ""


def get_machine_code() -> str:
    """组合多个系统/硬件特征后取 SHA-256 摘要，格式化为 5 组 4 位大写十六进制。"""
    parts = [_get_machine_guid(), _get_mac_hex(), _get_volume_serial()]
    raw = "|".join(part for part in parts if part)
    if not raw:
        raw = uuid.uuid4().hex  # 极端环境下兜底，仍能保证每台机器码唯一
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    code = digest[:20]
    return "-".join(code[i : i + 4] for i in range(0, 20, 4))
