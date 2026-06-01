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
        progress_time = self.scene._clamp01((current - start) / duration)
        fade_in = self.scene._clamp01((current - start) / 240.0)
        fade_out = self.scene._clamp01((note.get("end_time", end) - current) / 260.0)
        alpha = int(255 * min(fade_in, fade_out))
        if alpha <= 0:
            return

        radius = int(min(self.scene.game.WIDTH, self.scene.game.HEIGHT) * 0.3705)
        pulse = 1.0 + 0.035 * math.sin(current * 0.018)
        visual_angle = math.degrees(note.get("spinner_visual_angle", 0.0))
        rpm = note.get("spinner_rpm", 0.0)
        speed_scale = min(1.18, 1.0 + rpm / 1800.0)

        self._draw_glow(target, center, int(radius * 1.08), alpha)
        self._draw_image_centered(
            target,
            self.images["approach"],
            center,
            int(radius * 2.25 * pulse),
            alpha=int(alpha * 0.85)
        )
        if not self._draw_rotated_centered(
            target,
            self.images["circle"],
            center,
            int(radius * 1.35 * speed_scale),
            -visual_angle,
            alpha=alpha
        ):
            pygame.draw.circle(
                target,
                (235, 235, 245, int(alpha * 0.60)),
                center,
                int(radius * 0.68),
                max(6, radius // 28)
            )

        self._draw_progress(target, center, radius, note, alpha)
        self._draw_particles(target, center, radius, note, alpha)
        self._draw_text(target, center, radius, note, alpha)

    def _draw_glow(self, target, center, radius, alpha):
        glow = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        local = (glow.get_width() // 2, glow.get_height() // 2)
        for index in range(5):
            r = int(radius * (1.0 - index * 0.10))
            a = int(alpha * (0.055 + index * 0.022))
            pygame.draw.circle(glow, (170, 210, 255, a), local, r)
        target.blit(glow, glow.get_rect(center=center))

    def _draw_progress(self, target, center, radius, note, alpha):
        width = int(radius * 1.55)
        height = max(12, int(radius * 0.065))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (center[0], center[1] + int(radius * 0.86))
        pygame.draw.rect(target, (12, 14, 24, int(alpha * 0.66)), rect, border_radius=height // 2)
        pygame.draw.rect(target, (255, 255, 255, int(alpha * 0.42)), rect, 2, border_radius=height // 2)

        fill = rect.copy()
        fill.width = int(rect.width * min(1.0, note.get("spinner_progress", 0.0)))
        fill_color = (115, 210, 255, int(alpha * 0.92))
        if note.get("spinner_goal_reached"):
            fill_color = (255, 225, 120, int(alpha * 0.95))
        pygame.draw.rect(target, fill_color, fill, border_radius=height // 2)

    def _draw_particles(self, target, center, radius, note, alpha):
        rpm = note.get("spinner_rpm", 0.0)
        if rpm < 85:
            return
        count = int(min(20, 4 + rpm / 32))
        base_angle = note.get("spinner_visual_angle", 0.0)
        for index in range(count):
            phase = base_angle + index * (math.tau / count)
            wobble = math.sin(self.scene.current_time * 0.01 + index) * 0.10
            distance = radius * (0.70 + 0.18 * ((index % 3) / 2))
            pos = (
                center[0] + math.cos(phase + wobble) * distance,
                center[1] + math.sin(phase + wobble) * distance
            )
            particle_alpha = int(alpha * min(0.72, rpm / 420.0))
            pygame.draw.circle(
                target,
                (255, 255, 255, particle_alpha),
                (int(pos[0]), int(pos[1])),
                max(2, radius // 70)
            )

    def _draw_text(self, target, center, radius, note, alpha):
        rpm_text = self.scene.medium_overlay_font.render(
            f"{int(note.get('spinner_rpm', 0))} RPM",
            True,
            (255, 255, 255)
        )
        avg_text = self.scene.small_overlay_font.render(
            f"avg {int(note.get('spinner_average_rpm', 0))}  bonus x{note.get('spinner_bonus_count', 0)}",
            True,
            (220, 235, 255)
        )
        status = "SPIN!"
        if note.get("spinner_goal_reached"):
            status = "CLEAR!"
        status_text = self.scene.title_overlay_font.render(
            status,
            True,
            (255, 255, 255)
        )
        for surf, y in (
            (status_text, center[1] - int(radius * 0.20)),
            (rpm_text, center[1] + int(radius * 0.10)),
            (avg_text, center[1] + int(radius * 0.28))
        ):
            surf.set_alpha(alpha)
            target.blit(surf, surf.get_rect(center=(center[0], y)))

    def _draw_image_centered(self, target, image, center, diameter, alpha=255):
        if image is None:
            return False
        scaled = self._scaled(image, diameter)
        scaled.set_alpha(alpha)
        target.blit(scaled, scaled.get_rect(center=center))
        return True

    def _draw_rotated_centered(self, target, image, center, diameter, angle, alpha=255):
        if image is None:
            return False
        scaled = self._scaled(image, diameter)
        rotated = pygame.transform.rotozoom(scaled, angle, 1.0)
        rotated.set_alpha(alpha)
        target.blit(rotated, rotated.get_rect(center=center))
        return True

    def _scaled(self, image, diameter):
        diameter = max(1, int(diameter))
        key = (id(image), diameter)
        cached = self.cache.get(key)
        if cached is None:
            cached = pygame.transform.smoothscale(image, (diameter, diameter)).convert_alpha()
            self.cache[key] = cached
        return cached.copy()
