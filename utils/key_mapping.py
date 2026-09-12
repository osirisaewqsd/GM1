# utils/key_mapping.py
# 对应21键映射
NOTE_KEY_MAP = {
    "C2": "z",
    "D2": "x",
    "E2": "c",
    "F2": "v",
    "G2": "b",
    "A3": "n",
    "B3": "m",

    "C3": "a",
    "D3": "s",
    "E3": "d",
    "F3": "f",
    "G3": "g",
    "A4": "h",
    "B4": "j",

    "C4": "q",
    "D4": "w",
    "E4": "e",
    "F4": "r",
    "G4": "t",
    "A5": "y",
    "B5": "u"
}

def get_key(note_name: str):
    return NOTE_KEY_MAP.get(note_name, None)