import math

import pygame

from core.assets import load_image

 
class SpinnerRenderer:
    def __init__(self, scene):
        self.scene = scene
        self.images = {
            "approach": self._load_image("spinner-approachcircle.png"),
            "circle": self._load_image("spinner-circle.png")
        }
        self.cache = {}

    def _load_image(self, filename):
        img = load_image(filename, "spinner")
        return img.convert_alpha() if img else None

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
        approach_progress = self.scene._smoothstep(progress)
        fade_in = self.scene._ease_out_cubic((current - start) / 150.0)
        fade_out = 1.0
        fade_out_start = note.get("fade_out_start")
        if fade_out_start is not None:
            fade_out_duration = max(1.0, float(note.get("fade_out_duration", 260)))
            fade_out_progress = self.scene._clamp01(
                (current - fade_out_start) / fade_out_duration
            )
            fade_out = (1.0 - fade_out_progress) ** 1.35
        object_alpha_scale = getattr(self.scene, "object_alpha_scale", 1.0)
        alpha = int(255 * fade_in * fade_out * object_alpha_scale)
        visual_angle = -math.degrees(note.get("spinner_visual_angle", 0.0))
        approach_close_fade = 1.0 - self.scene._smoothstep(
            self.scene._clamp01((progress - 0.94) / 0.06)
        )
        approach_alpha = int(
            235
            * fade_in
            * fade_out
            * object_alpha_scale
            * approach_close_fade
        )

        if approach_alpha > 0:
            self._draw_image_centered(
                target,
                self.images["approach"],
                center,
                int(radius * (3.35 - 3.17 * approach_progress)),
                alpha=approach_alpha,
                quantize_step=4
            )
        if not self._draw_rotated_centered(
            target,
            self.images["circle"],
            center,
            int(radius * 1.35),
            visual_angle,
            alpha=alpha
        ):
            pygame.draw.circle(
                target,
                (235, 235, 245, int(175 * fade_in * fade_out * object_alpha_scale)),
                center,
                int(radius * 0.68),
                max(6, radius // 28)
            )

        if note.get("spinner_goal_reached"):
            text = getattr(self.scene, "spinner_pass_text_surface", None)
            if text is None:
                text = self.scene.medium_overlay_font.render(
                    "PASS",
                    True,
                    (255, 245, 150)
                )
                self.scene.spinner_pass_text_surface = text
            pass_time = note.get("spinner_pass_time", current)
            pop = self.scene._clamp01((current - pass_time) / 180.0)
            settle = self.scene._clamp01((current - pass_time) / 520.0)
            text_alpha = int(210 * fade_in * fade_out * (1.0 - settle * 0.28))
            previous_alpha = text.get_alpha()
            text.set_alpha(max(0, min(255, text_alpha)))
            text_rect = text.get_rect(
                center=(
                    center[0],
                    center[1] + int(radius * (0.42 - 0.035 * self.scene._ease_out_cubic(pop)))
                )
            )
            target.blit(text, text_rect)
            text.set_alpha(previous_alpha)

    def _draw_image_centered(
        self,
        target,
        image,
        center,
        diameter,
        alpha=255,
        quantize_step=None
    ):
        if image is None:
            return False
        scaled = self._scaled(image, diameter, quantize_step=quantize_step)
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
        angle_key = int(round(angle / 4.0) * 4) % 360
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

    def _scaled(self, image, diameter, quantize_step=None):
        diameter = max(1, int(diameter))
        if quantize_step is not None:
            step = max(1, int(quantize_step))
            diameter = max(1, int(round(diameter / step)) * step)
        elif diameter >= 128:
            diameter = max(1, int(round(diameter / 8.0)) * 8)
        elif diameter >= 48:
            diameter = max(1, int(round(diameter / 4.0)) * 4)
        key = (id(image), diameter)
        cached = self.cache.get(key)
        if cached is None:
            cached = pygame.transform.smoothscale(image, (diameter, diameter)).convert_alpha()
            self.cache[key] = cached
        return cached
