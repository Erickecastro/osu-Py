import math
from pathlib import Path

import pygame


class SpinnerRenderer:
    def __init__(self, scene):
        self.scene = scene
        self.images = {
            "approach": self._load_image("spinner-approachcircle.png"),
            "circle": self._load_image("spinner-circle.png")
        }
        self.cache = {}

    def _load_image(self, filename):
        path = Path("assets") / "spinner" / filename
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None

    def draw(self, target, note):
        start = note["spinner_start_time"]
        end = note["spinner_end_time"]
        current = self.scene.current_time
        if current < start or current > note.get("end_time", end):
            return

        center = (
            self.scene.game.WIDTH // 2,
            self.scene.game.HEIGHT // 2
        )
        duration = max(1, end - start)
        radius = int(min(self.scene.game.WIDTH, self.scene.game.HEIGHT) * 0.3705)
        progress = self.scene._clamp01((current - start) / duration)
        visual_angle = -math.degrees(note.get("spinner_visual_angle", 0.0))

        self._draw_image_centered(
            target,
            self.images["approach"],
            center,
            int(radius * (3.25 - 1.62 * progress)),
            alpha=235
        )
        if not self._draw_rotated_centered(
            target,
            self.images["circle"],
            center,
            int(radius * 1.35),
            visual_angle,
            alpha=255
        ):
            pygame.draw.circle(
                target,
                (235, 235, 245, 175),
                center,
                int(radius * 0.68),
                max(6, radius // 28)
            )

    def _draw_image_centered(self, target, image, center, diameter, alpha=255):
        if image is None:
            return False
        scaled = self._scaled(image, diameter)
        previous_alpha = scaled.get_alpha()
        if alpha != 255:
            scaled.set_alpha(alpha)
        target.blit(scaled, scaled.get_rect(center=center))
        if alpha != 255:
            scaled.set_alpha(previous_alpha)
        return True

    def _draw_rotated_centered(self, target, image, center, diameter, angle, alpha=255):
        if image is None:
            return False
        angle_key = int(round(angle / 2.0) * 2) % 360
        key = ("rotated", id(image), max(1, int(diameter)), angle_key)
        rotated = self.cache.get(key)
        if rotated is None:
            scaled = self._scaled(image, diameter)
            rotated = pygame.transform.rotozoom(scaled, angle_key, 1.0)
            self.cache[key] = rotated

        previous_alpha = rotated.get_alpha()
        if alpha != 255:
            rotated.set_alpha(alpha)
        target.blit(rotated, rotated.get_rect(center=center))
        if alpha != 255:
            rotated.set_alpha(previous_alpha)
        return True

    def _scaled(self, image, diameter):
        diameter = max(1, int(diameter))
        key = (id(image), diameter)
        cached = self.cache.get(key)
        if cached is None:
            cached = pygame.transform.smoothscale(image, (diameter, diameter)).convert_alpha()
            self.cache[key] = cached
        return cached
