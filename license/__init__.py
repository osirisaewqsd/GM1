"""猫之琴授权模块：机器码绑定 + RSA 签名激活码。"""

from license.verify import (
    LicenseStatus,
    activate,
    check_license,
    get_buyer_name,
    get_license_display,
)

__all__ = [
    "LicenseStatus",
    "activate",
    "check_license",
    "get_buyer_name",
    "get_license_display",
]
