# core/parsers/midi_parser.py
import os
import json
from dataclasses import asdict
import mido
from .base_parser import BaseParser
from ..data_models import PlayEvent, MusicInfo

class MidiParser(BaseParser):
    @property
    def supported_extensions(self) -> list[str]:
        return ['.mid', '.midi']

    def parse(self, file_path: str) -> MusicInfo | None:
        events = self._parse_midi_to_events(file_path)
        if not events:
            return None
        display_name = os.path.splitext(os.path.basename(file_path))[0]
        serialized = json.dumps([asdict(e) for e in events])
        return MusicInfo(
            name=display_name,
            music_data=serialized,
            file_path=file_path,
            speed=None,
            file_type='midi'
        )

    @staticmethod
    def _parse_midi_to_events(midi_path: str) -> list[PlayEvent]:
        try:
            mid = mido.MidiFile(midi_path)
        except Exception as e:
            print(f"读取 MIDI 失败: {e}")
            return []

        ticks_per_beat = mid.ticks_per_beat
        tempo = 500000

        notes = []
        for track in mid.tracks:
            cur_time = 0.0
            active = {}
            for msg in track:
                cur_time += mido.tick2second(msg.time, ticks_per_beat, tempo)
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                elif msg.type == 'note_on' and msg.velocity > 0:
                    active[msg.note] = cur_time
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in active:
                        start = active.pop(msg.note)
                        end = cur_time
                        if end <= start:
                            end = start + 0.1
                        notes.append((start, end, msg.note))

        if not notes:
            return []

        notes.sort(key=lambda x: x[0])

        groups = []
        i = 0
        while i < len(notes):
            start_time = notes[i][0]
            group_pitches = []
            end_time = 0.0
            while i < len(notes) and abs(notes[i][0] - start_time) < 0.01:
                s, e, pitch = notes[i]
                group_pitches.append(pitch)
                if e > end_time:
                    end_time = e
                i += 1
            group_pitches = list(set(group_pitches))
            group_pitches.sort()
            groups.append((start_time, end_time, group_pitches))

        if not groups:
            return []

        from ..note_events_to_txt import apply_of_lyre_processing, midi_to_note_name
        processed_groups = apply_of_lyre_processing(groups)

        if not processed_groups:
            return []

        result = []
        for idx, (start, end, pitches) in enumerate(processed_groups):
            note_names = [midi_to_note_name(p) for p in pitches]
            note_names = [n for n in note_names if n]
            if not note_names:
                continue
            if idx == 0:
                delay = 0
            else:
                prev_start = processed_groups[idx - 1][0]
                delay = int((start - prev_start) * 1000)
                if delay < 0:
                    delay = 0
            result.append(PlayEvent(delay=delay, notes=note_names))

        print(f"生成 {len(result)} 个事件")
        return result
