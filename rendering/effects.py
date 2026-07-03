import pygame


class GameplayEffectsRenderer:
    def __init__(self, scene):
        self.scene = scene
        self.combo_number_surface_cache = {}

    def combo_number_surfaces(self, text):
        cached = self.combo_number_surface_cache.get(text)
        if cached is not None:
            return cached

        surfaces = (
            self.scene.circle_number_font.render(
                text,
                True,
                (0, 0, 0)
            ),
            self.scene.circle_number_font.render(
                text,
                True,
                (255, 255, 255)
            )
        )
        self.combo_number_surface_cache[text] = surfaces
        return surfaces

    def combo_number_image(self, text):
        digits = self.scene.skin_images.get("combo_digits", {})
        parts = [
            self.scene._cropped_alpha_image(digits.get(ch))
            for ch in text
        ]
        if not parts or any(part is None for part in parts):
            return None

        key = ("image", text, "digit-spacing-v2")
        cached = self.combo_number_surface_cache.get(key)
        if cached is not None:
            return cached

        height = max(part.get_height() for part in parts)
        spacing = max(2, int(height * 0.045)) if len(parts) > 1 else 0
        width = (
            sum(part.get_width() for part in parts)
            + spacing * max(0, len(parts) - 1)
        )
        surface = pygame.Surface(
            (max(1, width), height),
            pygame.SRCALPHA
        )
        x = 0
        for part in parts:
            y = (height - part.get_height()) // 2
            surface.blit(part, (x, y))
            x += part.get_width() + spacing

        self.combo_number_surface_cache[key] = surface
        return surface

    def draw_combo_number(
        self,
        target,
        text,
        center,
        alpha=255
    ):
        image = self.combo_number_image(text)
        if image is not None:
            visual_radius = getattr(
                self.scene,
                "note_visual_radius",
                self.scene.scaled_radius
            )
            height = max(1, int(visual_radius * 0.565))
            width = max(
                1,
                int(image.get_width() * (height / image.get_height()))
            )
            scaled = self.scene._scaled_image(
                image,
                (width, height)
            )
            self.scene._draw_centered_text(
                target,
                scaled,
                center,
                alpha=alpha
            )
            return

        outline, main_text = self.combo_number_surfaces(text)
        outline.set_alpha(alpha)

        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rect = outline.get_rect(
                center=(
                    int(round(center[0] + dx)),
                    int(round(center[1] + dy))
                )
            )
            target.blit(outline, rect)

        self.scene._draw_centered_text(
            target,
            main_text,
            center,
            alpha=alpha
        )

    def draw_miss_pop(
        self,
        target,
        center,
        radius,
        color,
        alpha=255
    ):
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        radius = max(1, int(radius))
        progress = self.scene._clamp01(1.0 - (alpha / 255.0))
        base_radius = max(
            1,
            float(getattr(self.scene, "note_visual_radius", radius))
        )
        scale = (radius / base_radius) * (1.0 - progress * 0.42)
        skin_alpha = int(alpha * (1.0 - progress * 0.10))
        if self.scene._draw_hitcircle_skin(
            target,
            center,
            color,
            alpha=skin_alpha,
            diameter_scale=max(0.12, scale)
        ):
            return

        eased = progress * progress * progress * (
            progress * (progress * 6.0 - 15.0) + 10.0
        )
        collapse = 1.0 - ((1.0 - eased) ** 1.75)
        remaining = 1.0 - collapse

        fill_radius = int(radius * max(0.04, remaining ** 1.05))
        shell_radius = int(radius * max(0.07, remaining ** 0.94))
        ring_width = max(1, int(radius * (0.055 * remaining + 0.018)))
        visible_alpha = int(255 * (remaining ** 1.18))

        if fill_radius > 1:
            self.scene._draw_aa_circle(
                target,
                center,
                fill_radius,
                fill_color=color,
                alpha=int(visible_alpha * 0.82)
            )

        self.scene._draw_aa_circle(
            target,
            center,
            shell_radius,
            outline_color=(255, 255, 255),
            outline_width=ring_width,
            alpha=visible_alpha
        )

        if progress < 0.64:
            inner_alpha = int(visible_alpha * (1.0 - progress / 0.64) * 0.30)
            inner_radius = int(radius * max(0.03, remaining ** 1.42))
            self.scene._draw_aa_circle(
                target,
                center,
                inner_radius,
                outline_color=(255, 255, 255),
                outline_width=max(1, int(ring_width * 0.55)),
                alpha=inner_alpha
            )

    def draw_hit_explosion(
        self,
        target,
        center,
        radius,
        color,
        hit_time,
        alpha=255
    ):
        explosion_elapsed = self.scene.current_time - hit_time
        explosion_progress = min(
            1.0,
            explosion_elapsed / self.scene.hit_explosion_duration
        )
        base_radius = max(
            1,
            float(getattr(self.scene, "note_visual_radius", radius))
        )
        eased = 1.0 - ((1.0 - explosion_progress) ** 3)
        expansion_factor = (radius / base_radius) * (1.0 + eased * 0.34)
        explosion_alpha = int(alpha * ((1.0 - explosion_progress) ** 0.78))
        if self.scene._draw_hitcircle_skin(
            target,
            center,
            color,
            alpha=explosion_alpha,
            diameter_scale=expansion_factor
        ):
            return

        explosion_radius = int(radius * expansion_factor)

        self.scene._draw_aa_circle(
            target,
            center,
            explosion_radius,
            fill_color=color,
            outline_color=(255, 255, 255),
            outline_width=max(1, int(3 * (1.0 - explosion_progress))),
            alpha=explosion_alpha
        )
