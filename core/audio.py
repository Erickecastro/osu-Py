import os

import pygame


_LOADED_MUSIC_PATH = None
_LAST_START_OFFSET_MS = 0

SOUND_EFFECT_NAME_PARTS = (
    "hitnormal",
    "hitclap",
    "hitfinish",
    "hitwhistle",
    "normal-hit",
    "soft-hit",
    "drum-hit",
    "slider",
    "spinner",
    "combobreak",
    "failsound",
    "sectionfail",
    "sectionpass",
    "applause",
    "pause",
    "menuhit",
    "menuback",
    "menuclick"
)


def is_sound_effect_file(path):
    name = os.path.basename(str(path)).lower()
    return any(part in name for part in SOUND_EFFECT_NAME_PARTS)


def find_audio_file(folder_path, preferred_filename=None):
    if not os.path.exists(folder_path):
        return None

    if preferred_filename:
        preferred_path = os.path.join(folder_path, preferred_filename)
        if os.path.exists(preferred_path) and not is_sound_effect_file(preferred_path):
            return preferred_path

    files = [
        filename
        for filename in os.listdir(folder_path)
        if filename.lower().endswith((".mp3", ".ogg", ".wav"))
    ]
    files.sort()

    for extensions in ((".mp3", ".ogg"), (".wav",
    )):
        for filename in files:
            lower = filename.lower()
            path = os.path.join(folder_path, filename)
            if lower.endswith(extensions) and not is_sound_effect_file(path):
                return path

    return None


def _normalise_music_path(music_path):
    if not music_path:
        return None
    return os.path.abspath(str(music_path))


def mark_music_loaded(music_path):
    global _LOADED_MUSIC_PATH, _LAST_START_OFFSET_MS
    _LOADED_MUSIC_PATH = _normalise_music_path(music_path)
    _LAST_START_OFFSET_MS = 0


def clear_loaded_music():
    global _LOADED_MUSIC_PATH, _LAST_START_OFFSET_MS
    _LOADED_MUSIC_PATH = None
    _LAST_START_OFFSET_MS = 0


def get_last_start_offset_ms():
    return _LAST_START_OFFSET_MS


def preload_music(music_path):
    global _LOADED_MUSIC_PATH, _LAST_START_OFFSET_MS
    normalized = _normalise_music_path(music_path)
    if not normalized:
        return False

    if _LOADED_MUSIC_PATH == normalized:
        return True

    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.load(normalized)
        _LOADED_MUSIC_PATH = normalized
        _LAST_START_OFFSET_MS = 0
        return True
    except pygame.error:
        _LOADED_MUSIC_PATH = None
        _LAST_START_OFFSET_MS = 0
        return False


def start_music(music_path, start_ms=0):
    global _LOADED_MUSIC_PATH, _LAST_START_OFFSET_MS
    if not music_path:
        _LAST_START_OFFSET_MS = 0
        return None

    try:
        normalized = _normalise_music_path(music_path)
        start_seconds = max(0.0, float(start_ms or 0) / 1000.0)
        actual_start_ms = int(start_ms or 0)
        pygame.mixer.music.stop()
        if _LOADED_MUSIC_PATH != normalized:
            pygame.mixer.music.load(normalized)
            _LOADED_MUSIC_PATH = normalized
        try:
            pygame.mixer.music.play(start=start_seconds)
        except TypeError:
            actual_start_ms = 0
            pygame.mixer.music.play()
        except pygame.error:
            actual_start_ms = 0
            pygame.mixer.music.play()
        _LAST_START_OFFSET_MS = actual_start_ms
        return pygame.time.get_ticks() - actual_start_ms
    except Exception as exc:
        _LOADED_MUSIC_PATH = None
        _LAST_START_OFFSET_MS = 0
        print(exc)
        return None
