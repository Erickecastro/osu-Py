import os

import pygame


def find_audio_file(folder_path):
    if not os.path.exists(folder_path):
        return None

    for filename in os.listdir(folder_path):
        if filename.endswith(".mp3") or filename.endswith(".ogg"):
            return os.path.join(folder_path, filename)

    return None


def start_music(music_path):
    if not music_path or pygame.mixer.music.get_busy():
        return None

    try:
        pygame.mixer.music.load(music_path)
        pygame.mixer.music.play()
        return pygame.time.get_ticks()
    except Exception as exc:
        print(exc)
        return None
