# utils/window_helper.py

import win32gui

def get_foreground_window_title() -> str:
    """获取当前前台激活窗口标题"""
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    return title.strip()

def get_all_visible_window_titles() -> list[str]:
    """枚举所有可见、非空窗口标题"""
    titles = []
    def enum_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd).strip()
            if t:
                titles.append(t)
        return True
    win32gui.EnumWindows(enum_callback, None)
    # 去重排序
    return sorted(list(set(titles)))
