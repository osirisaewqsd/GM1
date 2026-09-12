# core/parser_factory.py
from .parsers.base_parser import BaseParser
from .parsers.js_parser import JsParser
from .parsers.midi_parser import MidiParser
from .parsers.txt_parser import TxtParser

class ParserFactory:
    _parsers: list[BaseParser] = []

    @classmethod
    def register_parser(cls, parser: BaseParser):
        cls._parsers.append(parser)

    @classmethod
    def get_parser(cls, file_path: str) -> BaseParser | None:
        for parser in cls._parsers:
            for ext in parser.supported_extensions:
                if file_path.lower().endswith(ext):
                    return parser
        return None

# 注册所有解析器
ParserFactory.register_parser(JsParser())
ParserFactory.register_parser(MidiParser())
ParserFactory.register_parser(TxtParser())
