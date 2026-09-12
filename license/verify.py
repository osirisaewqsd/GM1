"""授权状态检查与激活逻辑。"""

from datetime import datetime

from license.crypto import parse_activation_code
from license.machine_code import get_machine_code
from license.store import load_license, save_license


class LicenseStatus:
    OK = "ok"
    NOT_ACTIVATED = "not_activated"
    MACHINE_MISMATCH = "machine_mismatch"
    EXPIRED = "expired"
    INVALID = "invalid"


def _parse_expiry(info: dict) -> str | None:
    expiry = info.get("e") or ""
    if not expiry:
        return None
    try:
        if datetime.fromisoformat(expiry) < datetime.now().astimezone():
            return LicenseStatus.EXPIRED
    except ValueError:
        return LicenseStatus.INVALID
    return None


def check_license(license_path: str | None = None) -> tuple[str, dict | None]:
    """返回 (状态, 授权信息)。每次启动都重新校验签名，不信任本地文件。"""
    saved = load_license(license_path)
    if not saved or not saved.get("activation_code"):
        return LicenseStatus.NOT_ACTIVATED, None

    try:
        info = parse_activation_code(saved["activation_code"])
    except ValueError:
        return LicenseStatus.INVALID, None

    if info.get("m") != get_machine_code():
        return LicenseStatus.MACHINE_MISMATCH, None

    expired = _parse_expiry(info)
    if expired:
        return expired, None
    return LicenseStatus.OK, info


def activate(
    activation_code: str, license_path: str | None = None
) -> tuple[bool, str]:
    """校验激活码并绑定本机。返回 (是否成功, 提示消息)。"""
    code = activation_code.strip()
    try:
        info = parse_activation_code(code)
    except ValueError as exc:
        return False, str(exc)

    machine_code = get_machine_code()
    if info.get("m") != machine_code:
        return False, f"激活码与本机不匹配（本机机器码：{machine_code}）"

    expired = _parse_expiry(info)
    if expired == LicenseStatus.EXPIRED:
        return False, "激活码已过期"
    if expired == LicenseStatus.INVALID:
        return False, "激活码内容损坏"

    expiry = info.get("e") or ""
    if not expiry:
        success_msg = "激活成功，已永久激活"
    else:
        try:
            exp_text = datetime.fromisoformat(expiry).strftime("%Y-%m-%d")
        except ValueError:
            exp_text = str(expiry)
        success_msg = f"激活成功，有效期至 {exp_text}"

    save_license(
        {
            "machine_code": machine_code,
            "activation_code": code,
            "activated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "buyer": info.get("b", ""),
        },
        license_path,
    )
    return True, success_msg


def get_buyer_name(license_path: str | None = None) -> str:
    saved = load_license(license_path)
    if saved:
        return str(saved.get("buyer", ""))
    return ""


def get_license_display(license_path: str | None = None) -> str:
    """返回窗口标题用的授权后缀，如 【张三】永久激活。"""
    saved = load_license(license_path)
    if not saved or not saved.get("activation_code"):
        return ""
    try:
        info = parse_activation_code(saved["activation_code"])
    except ValueError:
        return ""

    buyer = str(info.get("b", "")).strip()
    expiry = info.get("e") or ""
    if not expiry:
        suffix = "永久激活"
    else:
        try:
            suffix = f"有效期至{datetime.fromisoformat(expiry).strftime('%Y-%m-%d')}"
        except ValueError:
            suffix = "已激活"
    return f"【{buyer}】{suffix}" if buyer else f"【{suffix}】"
