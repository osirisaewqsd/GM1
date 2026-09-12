import os
import sys
from pathlib import Path

def get_project_root() -> str:
    """
    获取项目根目录（开发环境）或 _internal 目录（打包后）
    """
    # 1. 优先使用 PyInstaller 设置的 _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS

    # 2. 如果程序是 frozen（打包状态）但 _MEIPASS 未设置，手动推断
    if getattr(sys, 'frozen', False):
        # 打包后，exe 位于 dist/猫之琴轻量版/，_internal 在 exe 同级
        exe_dir = os.path.dirname(sys.executable)
        internal = os.path.join(exe_dir, '_internal')
        if os.path.exists(internal):
            return internal
        # 如果当前文件在 _internal 目录下，直接返回其所在目录
        current_file = Path(__file__).resolve()
        if current_file.parent.name == '_internal':
            return str(current_file.parent)
        # 向上查找 _internal 目录
        parts = current_file.parts
        for i in range(len(parts)-1, -1, -1):
            if parts[i] == '_internal':
                return os.sep.join(parts[:i+1])

    # 3. 开发环境：从当前文件向上查找项目根
    current = Path(__file__).resolve()
    if current.parent.name == 'utils':
        return str(current.parent.parent)
    return str(current.parent)

def get_resource_path(relative_path: str) -> str:
    """
    获取资源文件的绝对路径，支持开发环境和打包环境
    """
    root = get_project_root()
    # 移除可能的前缀
    clean = relative_path
    if clean.startswith('resources/') or clean.startswith('resources\\'):
        clean = clean[10:]

    # 候选路径（按优先级）
    candidates = [
        os.path.join(root, 'resources', clean),   # 标准打包结构（_internal/resources/xxx）
        os.path.join(root, clean),                # 扁平结构（备用）
        os.path.join(os.getcwd(), 'resources', clean),  # 开发环境（当前目录）
        os.path.join(os.getcwd(), clean),
    ]
    # 去重并返回第一个存在的
    seen = set()
    for p in candidates:
        norm = os.path.normpath(p)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.exists(norm):
            return norm
    # 若都不存在，返回第一个
    return candidates[0]

def get_adb_path() -> str:
    adb_name = "adb.exe" if os.name == "nt" else "adb"
    return get_resource_path(os.path.join("adb", adb_name))

def get_icon_path() -> str:
    return get_resource_path("yq.ico")
