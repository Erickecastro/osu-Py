import math
from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class AtlasSpriteRef:
    page_index: int
    rect: pygame.Rect
    key: object
    size: tuple[int, int]


class _AtlasPage:
    def __init__(self, size):
        self.size = int(size)
        self.surface = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        self.cursor_x = 0
        self.cursor_y = 0
        self.row_height = 0
        self.used_area = 0
        self.version = 0

    def try_add(self, source, padding):
        width, height = source.get_size()
        padded_width = width + (padding * 2)
        padded_height = height + (padding * 2)
        if padded_width > self.size or padded_height > self.size:
            return None

        if self.cursor_x + padded_width > self.size:
            self.cursor_x = 0
            self.cursor_y += self.row_height
            self.row_height = 0

        if self.cursor_y + padded_height > self.size:
            return None

        rect = pygame.Rect(
            self.cursor_x + padding,
            self.cursor_y + padding,
            width,
            height,
        )
        self.surface.blit(source, rect)
        self.cursor_x += padded_width
        self.row_height = max(self.row_height, padded_height)
        self.used_area += width * height
        self.version += 1
        return rect


class SpriteAtlasRegistry:
    """CPU-side atlas registry used to stage future GPU sprite batching.

    Pygame remains the authoritative renderer for now. The atlas only records
    stable/cached sprites that opt in through the backend so we can measure and
    later promote those commands to a GPU path without changing gameplay logic.
    """

    def __init__(self, page_size=1024, padding=1, max_pages=32):
        self.page_size = int(page_size)
        self.padding = int(padding)
        self.max_pages = int(max_pages)
        self.pages = []
        self.entries = {}
        self.eviction_count = 0

    @property
    def page_count(self):
        return len(self.pages)

    @property
    def sprite_count(self):
        return len(self.entries)

    @property
    def used_area(self):
        return sum(page.used_area for page in self.pages)

    @property
    def total_area(self):
        return sum(page.size * page.size for page in self.pages)

    def clear(self):
        self.pages.clear()
        self.entries.clear()
        self.eviction_count += 1

    def add(self, surface, key=None, padding=None):
        if surface is None:
            return None

        size = surface.get_size()
        if size[0] <= 0 or size[1] <= 0:
            return None

        atlas_key = key if key is not None else (id(surface), size)
        cached = self.entries.get(atlas_key)
        if cached is not None and cached.size == size:
            return cached

        if cached is not None:
            self.entries.pop(atlas_key, None)

        if self.max_pages > 0 and len(self.pages) >= self.max_pages:
            self.clear()

        pad = self.padding if padding is None else int(padding)
        rect = None
        page_index = -1
        for index, page in enumerate(self.pages):
            rect = page.try_add(surface, pad)
            if rect is not None:
                page_index = index
                break

        if rect is None:
            page_size = self._page_size_for(size, pad)
            page = _AtlasPage(page_size)
            self.pages.append(page)
            page_index = len(self.pages) - 1
            rect = page.try_add(surface, pad)

        if rect is None:
            return None

        ref = AtlasSpriteRef(
            page_index=page_index,
            rect=rect,
            key=atlas_key,
            size=size,
        )
        self.entries[atlas_key] = ref
        return ref

    def _page_size_for(self, size, padding):
        required = max(size[0], size[1]) + (padding * 2)
        page_size = max(self.page_size, self._next_power_of_two(required))
        return page_size

    def _next_power_of_two(self, value):
        value = max(1, int(value))
        return 1 << int(math.ceil(math.log2(value)))

    def stats(self):
        return {
            "pages": self.page_count,
            "sprites": self.sprite_count,
            "used_area": self.used_area,
            "total_area": self.total_area,
            "evictions": self.eviction_count,
        }
