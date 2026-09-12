"""授权文件的读写（保存在 %APPDATA%\\猫之琴\\license.json）。"""

import json
import os
from pathlib import Path

APP_NAME = "猫之琴GM1"


def default_license_path() -> str:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return os.path.join(base, APP_NAME, "license.json")


def load_license(path: str | None = None) -> dict | None:
    path = path or default_license_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_license(data: dict, path: str | None = None) -> None:
    path = path or default_license_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
