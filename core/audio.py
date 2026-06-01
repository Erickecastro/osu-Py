import os

import pygame


def find_audio_file(folder_path, preferred_filename=None):
    if not os.path.exists(folder_path):
        return None

    if preferred_filename:
        preferred_path = os.path.join(folder_path, preferred_filename)
        if os.path.exists(preferred_path):
            return preferred_path

    for filename in os.listdir(folder_path):
        lower = filename.lower()
        if lower.endswith(".mp3") or lower.endswith(".ogg") or lower.endswith(".wav"):
            return os.path.join(folder_path, filename)

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
