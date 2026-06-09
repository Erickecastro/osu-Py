import os

import pygame

from core.assets import load_image


class CursorRenderer:
    def __init__(
        self,
        asset_dir=os.path.join("assets", "cursor"),
        cursor_scale=0.92,
        trail_scale=1.16
    ):
        self.asset_dir = asset_dir
        self.pos = pygame.mouse.get_pos()
        self.last_emit_pos = self.pos
        self.emit_timer = 0.0
        self.trail = []
        self.scaled_image_cache = {}

        self.trail_duration = 0.285
        self.trail_emit_interval = 0.012
        self.trail_min_distance = 2.0
        self.trail_max_points = 8

        self.cursor_image = self._load_asset(
            "cursor.png",
            cursor_scale
        )
        if self.cursor_image is not None:
            self.cursor_image.set_alpha(250)
        self.trail_image = self._load_asset(
            "cursortrail.png",
            trail_scale
        )

    def update(self, dt, pos):
        self.pos = pos
        self.emit_timer += dt

        live_trail = []
        for entry in self.trail:
            entry["age"] += dt
            if entry["age"] <= self.trail_duration:
                live_trail.append(entry)

        dx = self.pos[0] - self.last_emit_pos[0]
        dy = self.pos[1] - self.last_emit_pos[1]
        moved_distance = (dx * dx + dy * dy) ** 0.5

        if (
            self.emit_timer >= self.trail_emit_interval
            and moved_distance >= self.trail_min_distance
        ):
            live_trail.append({
                "pos": self.pos,
                "age": 0.0
            })
            self.emit_timer = 0.0
            self.last_emit_pos = self.pos

        self.trail = live_trail[-self.trail_max_points:]

    def draw(self, screen, pos=None):
        if pos is not None:
            self.pos = pos

        for entry in self.trail:
            progress = self._clamp01(
                entry["age"] / self.trail_duration
            )
            fade_in = self._clamp01(entry["age"] / 0.018)
            fade_out = 1.0 - progress
            alpha = int(
                220
                * self._ease_out_cubic(fade_in)
                * (fade_out ** 1.8)
            )
            scale = 0.86 + (0.14 * self._ease_out_cubic(fade_in))
            self._blit_centered(
                screen,
                self.trail_image,
                entry["pos"],
                alpha=alpha,
                scale=scale
            )

        self._blit_centered(
            screen,
            self.cursor_image,
            self.pos,
            alpha=None
        )

    def _load_asset(self, filename, scale=1.0):
        image = load_image(filename, "cursor")
        if image is None:
            return None

        if scale != 1.0:
            size = (
                max(1, int(image.get_width() * scale)),
                max(1, int(image.get_height() * scale))
            )
            image = pygame.transform.smoothscale(
                image,
                size
            )

        return image

    def _blit_centered(
        self,
        target,
        image,
        center,
        alpha=255,
        scale=1.0
    ):
        if image is None:
            return

        if alpha is not None:
            alpha = max(0, min(255, int(alpha)))
            if alpha <= 0:
                return

        if scale != 1.0:
            size = (
                max(1, int(image.get_width() * scale)),
                max(1, int(image.get_height() * scale))
            )
            cache_key = (id(image), size)
            render_image = self.scaled_image_cache.get(cache_key)
            if render_image is None:
                render_image = pygame.transform.smoothscale(
                    image,
                    size
                )
                self.scaled_image_cache[cache_key] = render_image
        else:
            render_image = image

        if alpha is not None and render_image.get_alpha() != alpha:
            render_image.set_alpha(alpha)
        rect = render_image.get_rect(
            center=(
                int(round(center[0])),
                int(round(center[1]))
            )
        )
        target.blit(render_image, rect)

    def _clamp01(self, value):
        if value <= 0:
            return 0.0
        if value >= 1:
            return 1.0
        return value

    def _ease_out_cubic(self, value):
        value = self._clamp01(value)
        return 1.0 - ((1.0 - value) ** 3)
