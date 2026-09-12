"""激活码的 RSA 签名 / 校验。

激活码格式：MAO1.<base64(payload)>.<base64(signature)>
payload 为 JSON：{"v": 1, "m": 机器码, "b": 购买者, "i": 签发时间, "e": 过期时间或空}
"""

import base64
import json
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from license.public_key import PUBLIC_KEY_PEM

CODE_PREFIX = "MAO1"
_RSA_PADDING = padding.PKCS1v15()
_RSA_HASH = hashes.SHA256()


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    text = text.strip()
    text += "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text)


def build_activation_code(
    private_key_pem: bytes,
    machine_code: str,
    buyer: str = "",
    days: int | None = None,
) -> str:
    """卖家端：用私钥为指定机器码签发激活码。"""
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "m": machine_code.strip().upper(),
        "b": (buyer or "").strip(),
        "i": now.isoformat(timespec="seconds"),
        "e": (now + timedelta(days=days)).isoformat(timespec="seconds")
        if days
        else "",
    }
    payload_bytes = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(payload_bytes, _RSA_PADDING, _RSA_HASH)
    return f"{CODE_PREFIX}.{_b64e(payload_bytes)}.{_b64e(signature)}"


def parse_activation_code(code: str) -> dict:
    """程序端：解析并验证激活码签名，返回 payload 字典；任何错误抛 ValueError。"""
    parts = code.strip().split(".")
    if len(parts) != 3 or parts[0] != CODE_PREFIX:
        raise ValueError("激活码格式不正确")
    try:
        payload_bytes = _b64d(parts[1])
        signature = _b64d(parts[2])
    except Exception as exc:
        raise ValueError("激活码内容无法解析") from exc

    public_key = serialization.load_pem_public_key(
        PUBLIC_KEY_PEM.encode("utf-8")
    )
    try:
        public_key.verify(signature, payload_bytes, _RSA_PADDING, _RSA_HASH)
    except InvalidSignature as exc:
        raise ValueError("激活码无效（签名校验失败）") from exc

    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("激活码内容损坏") from exc
    if data.get("v") != 1:
        raise ValueError("激活码版本不受支持")
    return data
