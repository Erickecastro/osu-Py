import os

import pygame


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

    for extensions in ((".mp3", ".ogg"), (".wav",)):
        for filename in files:
            lower = filename.lower()
            path = os.path.join(folder_path, filename)
            if lower.endswith(extensions) and not is_sound_effect_file(path):
                return path

    return None


def start_music(music_path, start_ms=0):
    if not music_path:
        return None

    try:
        start_seconds = max(0.0, float(start_ms or 0) / 1000.0)
        actual_start_ms = int(start_ms or 0)
        pygame.mixer.music.stop()
        pygame.mixer.music.load(music_path)
        try:
            pygame.mixer.music.play(start=start_seconds)
        except TypeError:
            actual_start_ms = 0
            pygame.mixer.music.play()
        except pygame.error:
            actual_start_ms = 0
            pygame.mixer.music.play()
        return pygame.time.get_ticks() - actual_start_ms
    except Exception as exc:
        print(exc)
        return None
