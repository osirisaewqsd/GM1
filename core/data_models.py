# core/data_models.py
from dataclasses import dataclass

@dataclass
class PlayEvent:
    delay: int          # 距上一事件的等待时间（毫秒）
    notes: list[str]    # 该时刻需按下的按键名列表

@dataclass
class MusicInfo:
    name: str
    music_data: str      # 统一为 PlayEvent 列表的 JSON 序列化字符串
    file_path: str
    speed: int | None = None
    file_type: str = 'js'  # 仅作记录