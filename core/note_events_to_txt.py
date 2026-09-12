from typing import List, Tuple, Any

_WHITE_OFFSETS = {0, 2, 4, 5, 7, 9, 11}

_MIN_PITCH = 36
_MAX_PITCH = 71

_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _is_white_key(midi_num: int) -> bool:
    return (midi_num % 12) in _WHITE_OFFSETS


def _midi_to_note_name(midi_num: int) -> str:
    note_idx = midi_num % 12
    note = _NOTE_NAMES[note_idx]
    if note in ('A', 'B'):
        octave = midi_num // 12
    else:
        octave = midi_num // 12 - 1
    return f"{note}{octave}"


def _is_in_range(midi_num: int) -> bool:
    return _MIN_PITCH <= midi_num <= _MAX_PITCH


def _find_best_transpose(pitches: List[int], min_shift: int = -24, max_shift: int = 24) -> int:
    best_count = -1
    best_shift = 0
    for shift in range(min_shift, max_shift + 1):
        count = 0
        for p in pitches:
            shifted = p + shift
            if _MIN_PITCH <= shifted <= _MAX_PITCH and _is_white_key(shifted):
                count += 1
        key = (count, -abs(shift), 1 if shift > 0 else (0 if shift == 0 else -1))
        best_key = (best_count, -abs(best_shift), 1 if best_shift > 0 else (0 if best_shift == 0 else -1))
        if key > best_key:
            best_count = count
            best_shift = shift
    return best_shift


def _compress_silences(
    groups: List[Tuple[float, float, List[int]]],
    max_silence_sec: float = 2.5
) -> List[Tuple[float, float, List[int]]]:
    """长静音压缩到 max_silence。"""
    if len(groups) <= 1:
        return groups

    result = []
    total_offset = 0.0
    for i, (start, end, notes) in enumerate(groups):
        if i > 0:
            prev_orig_end = groups[i - 1][1]
            silence = start - prev_orig_end
            if silence > max_silence_sec:
                total_offset += (silence - max_silence_sec)

        result.append((start - total_offset, end - total_offset, notes))

    return result


def _build_txt_string(groups: List[Tuple[float, float, List[int]]]) -> str:
    if not groups:
        return ""

    txt_parts = []
    num_groups = len(groups)
    for idx, (start, end, notes) in enumerate(groups):
        note_strs = []
        for pitch in notes:
            if _is_white_key(pitch) and _is_in_range(pitch):
                note_name = _midi_to_note_name(pitch)
                note_strs.append(f"{{{note_name}}}")
        if not note_strs:
            continue

        note_block = ''.join(note_strs)
        if idx < num_groups - 1:
            next_start = groups[idx + 1][0]
            wait_ms = int((next_start - start) * 1000)
        else:
            wait_ms = int((end - start) * 1000)

        if wait_ms <= 0:
            wait_ms = 1
        txt_parts.append(f"{note_block}<{wait_ms}>")

    return ''.join(txt_parts)


def apply_of_lyre_processing(
    groups: List[Tuple[float, float, List[int]]]
) -> List[Tuple[float, float, List[int]]]:
    """MIDI/TXT 精简处理链：移调、折叠、去黑键/超范围、压缩静音。"""
    if not groups:
        return []

    all_pitches = [pitch for _, _, notes in groups for pitch in notes]
    if not all_pitches:
        return []

    best_shift = _find_best_transpose(all_pitches)

    shifted_groups = []
    for start, end, notes in groups:
        shifted_notes = []
        for pitch in notes:
            new_pitch = pitch + best_shift
            while new_pitch < _MIN_PITCH:
                new_pitch += 12
            while new_pitch > _MAX_PITCH:
                new_pitch -= 12
            if _is_white_key(new_pitch) and _is_in_range(new_pitch):
                shifted_notes.append(new_pitch)
        if shifted_notes:
            shifted_notes.sort()
            shifted_groups.append((start, end, shifted_notes))

    if not shifted_groups:
        return []

    return _compress_silences(shifted_groups, max_silence_sec=2.5)


def midi_to_note_name(midi_num: int) -> str:
    return _midi_to_note_name(midi_num)


def note_events_to_txt(
    events: List[Tuple[float, float, float, float, Any]],
    bpm: float = 120
) -> str:
    filtered = []
    for start, end, pitch, vel, bends in events:
        dur = end - start
        if dur < 0.05 or vel < 0.1:
            continue
        pitch = int(round(pitch))
        while pitch < _MIN_PITCH:
            pitch += 12
        while pitch > _MAX_PITCH:
            pitch -= 12
        if _MIN_PITCH <= pitch <= _MAX_PITCH:
            filtered.append((start, end, pitch, vel))

    if not filtered:
        return ""

    filtered.sort(key=lambda x: x[0])
    groups = []
    i = 0
    while i < len(filtered):
        start_time = filtered[i][0]
        group_notes = []
        end_time = 0.0
        while i < len(filtered) and abs(filtered[i][0] - start_time) < 0.03:
            _, end, pitch, _ = filtered[i]
            group_notes.append(pitch)
            if end > end_time:
                end_time = end
            i += 1
        group_notes = list(set(group_notes))
        group_notes.sort()
        groups.append((start_time, end_time, group_notes))

    if not groups:
        return ""

    groups = apply_of_lyre_processing(groups)
    return _build_txt_string(groups)
