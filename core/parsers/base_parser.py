# core/parsers/base_parser.py
from abc import ABC, abstractmethod
from ..data_models import MusicInfo

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> MusicInfo | None:
        """解析文件，返回 MusicInfo，其中 music_data 为 JSON 字符串"""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """返回该解析器支持的文件扩展名列表"""
        pass