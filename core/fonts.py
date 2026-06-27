from functools import lru_cache

import pygame


ROUNDED_FONT_CANDIDATES = (
    "Nunito",
    "Quicksand",
    "VAG Rounded",
    "Arial Rounded MT Bold",
    "Segoe UI Rounded",
    "Segoe UI Semibold",
    "Segoe UI",
    "Cascadia Code",
    "Cascadia Mono",
)


@lru_cache(maxsize=96)
def rounded_font(size, bold=False, italic=False):
    size = max(1, int(size))
    for name in ROUNDED_FONT_CANDIDATES:
        path = pygame.font.match_font(name, bold=bold, italic=italic)
        if path:
            return pygame.font.Font(path, size)

    return pygame.font.SysFont("segoe ui", size, bold=bold, italic=italic)
