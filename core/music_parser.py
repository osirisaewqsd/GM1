# core/music_parser.py
import os
import json
from .data_models import PlayEvent, MusicInfo
from .parser_factory import ParserFactory

__all__ = ['PlayEvent', 'MusicInfo', 'MusicLib', 'parse_event_list']

def parse_event_list(serialized_str: str) -> list[PlayEvent]:
    """反序列化 JSON 字符串为 PlayEvent 列表"""
    data = json.loads(serialized_str)
    return [PlayEvent(delay=item['delay'], notes=item['notes']) for item in data]

class MusicLib:
    def __init__(self):
        self.dir_path: str | None = None
        self.cache: dict[str, MusicInfo] = {}
        self.name_list: list[str] = []

    def set_directory(self, path: str):
        self.dir_path = path
        self.cache.clear()
        self.name_list.clear()

    def scan_all(self) -> list[str]:
        if not self.dir_path or not os.path.isdir(self.dir_path):
            return []
        self.cache.clear()
        self.name_list.clear()
        for fname in os.listdir(self.dir_path):
            full_path = os.path.join(self.dir_path, fname)
            parser = ParserFactory.get_parser(full_path)
            if parser is None:
                continue

            # 通用方式：去掉扩展名作为显示名称
            display_name = os.path.splitext(fname)[0]
            # file_type 只用于记录
            info = MusicInfo(
                name=display_name,
                music_data=full_path,  # 懒加载：存路径
                file_path=full_path,
                speed=None,
                file_type=''
            )
            self.cache[info.name] = info

        self.name_list = sorted(self.cache.keys(), key=lambda x: x.lower())
        return self.name_list

    def get_info(self, name: str) -> MusicInfo | None:
        return self.cache.get(name)

    def delete_music(self, name: str) -> bool:
        info = self.get_info(name)
        if not info or not os.path.exists(info.file_path):
            return False
        try:
            os.remove(info.file_path)
            del self.cache[name]
            self.name_list = sorted(self.cache.keys(), key=lambda x: x.lower())
            return True
        except:
            return False

    def rename_music(self, old_name: str, new_name: str) -> bool:
        info = self.get_info(old_name)
        if not info:
            return False
        dir_name = os.path.dirname(info.file_path)
        ext = os.path.splitext(info.file_path)[1]
        new_file = os.path.join(dir_name, f"{new_name}{ext}")
        if os.path.exists(new_file):
            return False
        try:
            os.rename(info.file_path, new_file)
            del self.cache[old_name]
            info.file_path = new_file
            info.name = new_name
            self.cache[new_name] = info
            self.name_list = sorted(self.cache.keys(), key=lambda x: x.lower())
            return True
        except Exception as e:
            print(f"重命名失败: {e}")
            return False