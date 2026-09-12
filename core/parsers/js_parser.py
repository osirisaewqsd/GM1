# core/parsers/js_parser.py
import os
import re
import json
from dataclasses import asdict
from .base_parser import BaseParser
from ..data_models import MusicInfo, PlayEvent

MUSIC_PATTERN = re.compile(r"parseGenshinImpactMusic\s*\(\s*\"([^\"]*)\"\s*,\s*\"([^\"]*)\"(?:,\s*(\d+))?\)")

class JsParser(BaseParser):
    @property
    def supported_extensions(self) -> list[str]:
        return ['.js']

    def parse(self, file_path: str) -> MusicInfo | None:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except:
            return None

        display_name = os.path.basename(file_path).replace(".js", "")
        match = MUSIC_PATTERN.search(content)
        if match:
            raw_data = match.group(2)
            speed = int(match.group(3)) if match.group(3) else None
        elif content.startswith("{"):
            raw_data = content
            speed = None
        else:
            return None

        events = self._parse_js_to_events(raw_data)
        if not events:
            return None

        serialized = json.dumps([asdict(e) for e in events])
        return MusicInfo(
            name=display_name,
            music_data=serialized,
            file_path=file_path,
            speed=speed,
            file_type='js'
        )

    @staticmethod
    def _parse_js_to_events(raw_data: str) -> list[PlayEvent]:
        events = []
        i = 0
        data = re.sub(r"\s+", "", raw_data)
        length = len(data)
        while i < length:
            if data[i].isdigit():
                start = i
                while i < length and data[i].isdigit():
                    i += 1
                events.append(PlayEvent(delay=int(data[start:i]), notes=[]))
                continue
            if data[i] == '{':
                notes = []
                while i < length and data[i] == '{':
                    start = i + 1
                    end = data.find('}', start)
                    if end == -1:
                        break
                    notes.append(data[start:end])
                    i = end + 1
                duration = 100
                if i < length and data[i] == '<':
                    start = i + 1
                    end = data.find('>', start)
                    if end != -1:
                        try:
                            duration = int(data[start:end])
                        except ValueError:
                            pass
                        i = end + 1
                if notes:
                    events.append(PlayEvent(delay=duration, notes=notes))
                continue
            i += 1
        return [ev for ev in events if ev.delay > 0 or len(ev.notes) > 0]