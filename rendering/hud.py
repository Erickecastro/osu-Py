import pygame

from core.assets import load_image
from rendering.render_backend import RenderCommandBatch


class GameplayHUDRenderer:
    def __init__(self, font):
        self.font = font
        self.text_cache = {}
        self.text_cache_limit = 384
        self.dynamic_text_cache = {}
        self.health_bar_cache = {}
        self.health_bar_image = self._load_health_bar_image()
        self.health_bar_scaled_cache = {}
        self.hit_error_bar_cache = {}
        self.hit_error_marker_cache = {}
        self.fade_surface = None
        self.fade_surface_size = None
        self._hud_surface_cache = {}
        self.display_score = 0.0
        self.score_anim_start_value = 0.0+
        self.score_anim_target = 0
        self.score_anim_start_time = 0.0
        self.score_anim_duration = 160.0
        self.combo_anim_value = None
        self.combo_anim_start_time = 0.0
        self.combo_pop_duration = 140.0
        self.combo_scaled_cache = {}
        self.combo_scaled_cache_limit = 96

    def _load_health_bar_image(self):
        return load_image("scorebar-colour.png", "HP")

    def text_surface(self, text, color=(255, 255, 255)):
        key = (text, tuple(color))
        cached = self.text_cache.get(key)
        if cached is not None:
            return cached

        if len(self.text_cache) > self.text_cache_limit:
            self.text_cache.clear()

        surface = self.font.render(
            text,
            True,
            color
        )
        if surface is not None:
            surface = surface.convert_alpha()
        self.text_cache[key] = surface
        return surface

    def dynamic_text_surface(self, slot, text, color=(255, 255, 255)):
        key = (text, tuple(color))
        cached_key, cached_surface = self.dynamic_text_cache.get(
            slot,
            (None, None)
        )
        if cached_key == key and cached_surface is not None:
            return cached_surface

        surface = self.font.render(text, True, color)
        if surface is not None:
            surface = surface.convert_alpha()
        self.dynamic_text_cache[slot] = (key, surface)
        return surface

    def _clamp01(self, value):
        return max(0.0, min(1.0, float(value)))

    def _ease_out_quart(self, value):
        value = self._clamp01(value)
        return 1.0 - ((1.0 - value) ** 4)

    def _animated_score(self, score, current_time):
        score = int(score)
        now = float(current_time)
        try:
            self.display_score = float(self.display_score)
        except (TypeError, ValueError):
            self.display_score = float(score)
        if score != self.score_anim_target:
            self.score_anim_start_value = float(self.display_score)
            self.score_anim_target = score
            self.score_anim_start_time = now

        progress = self._ease_out_quart(
            (now - self.score_anim_start_time)
            / max(1.0, self.score_anim_duration)
        )
        self.display_score = (
            self.score_anim_start_value
            + ((self.score_anim_target - self.score_anim_start_value) * progress)
        )
        if progress >= 1.0:
            self.display_score = float(self.score_anim_target)

        return int(round(self.display_score))

    def _combo_scale(self, combo, current_time):
        combo = int(combo)
        now = float(current_time)
        if self.combo_anim_value is None:
            self.combo_anim_value = combo
            self.combo_anim_start_time = now
            return 1.0

        if combo != self.combo_anim_value:
            if combo > self.combo_anim_value:
                self.combo_anim_start_time = now
            self.combo_anim_value = combo

        progress = self._clamp01(
            (now - self.combo_anim_start_time)
            / max(1.0, self.combo_pop_duration)
        )
        if combo <= 0 or progress >= 1.0:
            return 1.0

        return 1.0 + (0.18 * (1.0 - self._ease_out_quart(progress)))

    def draw(
        self,
        screen,
        beatmap,
        current_time,
        score,
        accuracy,
        combo,
        health=1.0,
        hit_error_markers=None,
        hit_window_300=50,
        hit_window_100=100,
        hit_window_50=150,
        alpha=255,
        batch=None,
    ):
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        if alpha < 255:
            size = screen.get_size()
            if self.fade_surface is None or self.fade_surface_size != size:
                self.fade_surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
                self.fade_surface_size = size
            hud_surface = self.fade_surface
            hud_surface.fill((0, 0, 0, 0))
            self._draw_hud_content(
                hud_surface,
                beatmap,
                current_time,
                score,
                accuracy,
                combo,
                health,
                hit_error_markers,
                hit_window_300,
                hit_window_100,
                hit_window_50,
                batch=None,
            )
            hud_surface.set_alpha(alpha)
            screen.blit(hud_surface, (0, 0))
            return

        self._draw_hud_content(
            screen,
            beatmap,
            current_time,
            score,
            accuracy,
            combo,
            health,
            hit_error_markers,
            hit_window_300,
            hit_window_100,
            hit_window_50,
            batch=batch,
        )

    def _draw_hud_content(
        self,
        screen,
        beatmap,
        current_time,
        score,
        accuracy,
        combo,
        health=1.0,
        hit_error_markers=None,
        hit_window_300=50,
        hit_window_100=100,
        hit_window_50=150,
        batch=None,
    ):
        display_score = self._animated_score(score, current_time)
        combo_scale = self._combo_scale(combo, current_time)

        score_text = self.dynamic_text_surface(
            "score",
            f"{display_score:08d}",
            (255, 255, 255)
        )
        accuracy_text = self.dynamic_text_surface(
            "accuracy",
            f"{accuracy:05.2f}%",
            (255, 255, 255)
        )
        combo_text = self.dynamic_text_surface(
            "combo",
            f"{combo}x",
            (255, 255, 255)
        )
        combo_draw_surface = combo_text
        if combo_scale > 1.001:
            scaled_size = (
                max(1, int(round(combo_text.get_width() * combo_scale))),
                max(1, int(round(combo_text.get_height() * combo_scale)))
            )
            combo_draw_surface = self._scaled_combo_surface(
                combo_text,
                scaled_size
            )

        score_pos = (
            screen.get_width() - score_text.get_width() - 20,
            20
        )
        accuracy_pos = (
            screen.get_width() - accuracy_text.get_width() - 20,
            60
        )
        combo_pos = (
            20,
            screen.get_height() - combo_draw_surface.get_height() - 20
        )

        if batch is not None:
            batch.add_surface(
                score_text,
                score_pos,
                atlas_key=("hud", "score", display_score)
            )
            batch.add_surface(
                accuracy_text,
                accuracy_pos,
                atlas_key=("hud", "accuracy", f"{accuracy:05.2f}")
            )
            batch.add_surface(
                combo_draw_surface,
                combo_pos,
                atlas_key=(
                    "hud",
                    "combo",
                    int(combo),
                    combo_draw_surface.get_width(),
                    combo_draw_surface.get_height()
                )
            )
        else:
            screen.blit(score_text, score_pos)
            screen.blit(accuracy_text, accuracy_pos)
            screen.blit(combo_draw_surface, combo_pos)

        self.draw_health_bar(screen, health, batch=batch)
        self.draw_hit_error_bar(
            screen,
            current_time,
            hit_error_markers or (),
            hit_window_300,
            hit_window_100,
            hit_window_50,
            batch=batch,
        )

    def draw_health_bar(self, screen, health, batch=None):
        health = max(0.0, min(1.0, float(health)))
        width = min(760, max(360, int(screen.get_width() * 0.56)))
        source_ratio = (
            self.health_bar_image.get_height()
            / max(1, self.health_bar_image.get_width())
            if self.health_bar_image is not None
            else 0.028
        )
        height = max(12, int(width * source_ratio))
        x = max(14, int(screen.get_width() * 0.018))
        y = max(12, int(screen.get_height() * 0.024))
        fill_width = int(width * health)

        if self.health_bar_image is not None:
            scaled_key = (width, height)
            scaled = self.health_bar_scaled_cache.get(scaled_key)
            if scaled is None:
                if len(self.health_bar_scaled_cache) > 8:
                    self.health_bar_scaled_cache.clear()
                scaled = pygame.transform.smoothscale(
                    self.health_bar_image,
                    (width, height)
                )
                self.health_bar_scaled_cache[scaled_key] = scaled
            if fill_width > 0:
                if batch is not None:
                    batch.add_surface(
                        scaled,
                        (x, y),
                        area=pygame.Rect(0, 0, fill_width, height),
                        atlas_key=("hud", "health", width, height)
                    )
                else:
                    screen.blit(
                        scaled,
                        (x, y),
                        pygame.Rect(0, 0, fill_width, height)
                    )
            return

        cache_key = (width, height, fill_width, self.health_bar_image is not None)
        cached = self.health_bar_cache.get(cache_key)
        if cached is not None:
            if batch is not None:
                batch.add_surface(
                    cached,
                    (x, y),
                    atlas_key=("hud", "fallback_health", cache_key)
                )
            else:
                screen.blit(cached, (x, y))
            return

        if len(self.health_bar_cache) > 128:
            self.health_bar_cache.clear()

        surface = pygame.Surface(
            (width, height),
            pygame.SRCALPHA
        )

        if fill_width > 0:
            pygame.draw.rect(
                surface,
                (248, 248, 248),
                (0, 0, fill_width, height),
                border_radius=max(2, height // 2)
            )
        self.health_bar_cache[cache_key] = surface
        if batch is not None:
            batch.add_surface(
                surface,
                (x, y),
                atlas_key=("hud", "fallback_health", cache_key)
            )
        else:
            screen.blit(surface, (x, y))

    def draw_hit_error_bar(
        self,
        screen,
        current_time,
        markers,
        hit_window_300,
        hit_window_100,
        hit_window_50,
        batch=None,
    ):
        width = min(225, max(160, int(screen.get_width() * 0.157)))
        height = 28
        x = (screen.get_width() - width) // 2
        y = screen.get_height() - 48
        center_x = width // 2
        bar_y = height // 2
        half_width = width * 0.47
        max_window = max(1.0, float(hit_window_50))

        base = self._hit_error_base_surface(
            width,
            height,
            hit_window_300,
            hit_window_100,
            hit_window_50
        )
        if batch is not None:
            batch.add_surface(
                base,
                (x, y),
                atlas_key=(
                    "hud",
                    "hit_error_base",
                    width,
                    height,
                    int(hit_window_300),
                    int(hit_window_100),
                    int(hit_window_50)
                )
            )
        else:
            screen.blit(base, (x, y))

        for marker in markers:
            age = current_time - marker["time"]
            if age < 0 or age > marker.get("duration", 3000):
                continue

            lifetime = marker.get("duration", 3000)
            remaining = max(0.0, 1.0 - (age / max(1.0, lifetime)))
            alpha = int(235 * (remaining ** 0.55))
            delta = max(-max_window, min(max_window, float(marker["delta"])))
            marker_x = int(center_x + (delta / max_window) * half_width)
            color = self._hit_error_color(marker.get("result", 300))
            marker_surface = self._hit_error_marker_surface(
                color,
                alpha,
                height
            )
            if batch is not None:
                batch.add_surface(
                    marker_surface,
                    (x + marker_x - 3, y),
                    atlas_key=(
                        "hud",
                        "hit_error_marker",
                        color,
                        alpha,
                        height
                    )
                )
            else:
                screen.blit(marker_surface, (x + marker_x - 3, y))

    def _scaled_combo_surface(self, combo_text, scaled_size):
        cache_key = (id(combo_text), scaled_size)
        cached = self.combo_scaled_cache.get(cache_key)
        if cached is not None:
            return cached

        if len(self.combo_scaled_cache) > self.combo_scaled_cache_limit:
            self.combo_scaled_cache.clear()

        scaled = pygame.transform.smoothscale(
            combo_text,
            scaled_size
        ).convert_alpha()
        self.combo_scaled_cache[cache_key] = scaled
        return scaled

    def _hit_error_base_surface(
        self,
        width,
        height,
        hit_window_300,
        hit_window_100,
        hit_window_50
    ):
        cache_key = (
            width,
            height,
            int(hit_window_300),
            int(hit_window_100),
            int(hit_window_50)
        )
        cached = self.hit_error_bar_cache.get(cache_key)
        if cached is not None:
            return cached

        if len(self.hit_error_bar_cache) > 24:
            self.hit_error_bar_cache.clear()

        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        center_x = width // 2
        bar_y = height // 2
        half_width = width * 0.47
        max_window = max(1.0, float(hit_window_50))

        def x_for(delta):
            return int(center_x + (delta / max_window) * half_width)

        bar_rect = pygame.Rect(
            x_for(-hit_window_50),
            bar_y - 3,
            x_for(hit_window_50) - x_for(-hit_window_50),
            6
        )
        mask = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(
            mask,
            (255, 255, 255, 255),
            bar_rect,
            border_radius=3
        )

        gradient = pygame.Surface((width, height), pygame.SRCALPHA)
        for px in range(bar_rect.left, bar_rect.right + 1):
            delta = abs((px - center_x) / half_width) * max_window
            if delta <= hit_window_300:
                color = (86, 210, 255)
            elif delta <= hit_window_100:
                t = (delta - hit_window_300) / max(1.0, hit_window_100 - hit_window_300)
                color = self._mix_color((86, 210, 255), (140, 226, 72), t)
            else:
                t = (delta - hit_window_100) / max(1.0, hit_window_50 - hit_window_100)
                color = self._mix_color((140, 226, 72), (245, 190, 64), t)

            edge = min(px - bar_rect.left, bar_rect.right - px)
            alpha = int(190 * min(1.0, max(0.0, edge / 8.0)))
            pygame.draw.line(
                gradient,
                (*color, alpha),
                (px, bar_rect.top),
                (px, bar_rect.bottom)
            )

        gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(gradient, (0, 0))

        pygame.draw.circle(
            surface,
            (230, 248, 255, 235),
            (center_x, bar_y),
            5
        )
        pygame.draw.circle(
            surface,
            (72, 195, 255, 230),
            (center_x, bar_y),
            2
        )

        self.hit_error_bar_cache[cache_key] = surface
        return surface

    def _mix_color(self, a, b, t):
        t = max(0.0, min(1.0, float(t)))
        smooth = t * t * (3.0 - (2.0 * t))
        return (
            int(a[0] + (b[0] - a[0]) * smooth),
            int(a[1] + (b[1] - a[1]) * smooth),
            int(a[2] + (b[2] - a[2]) * smooth)
        )

    def _hit_error_color(self, result):
        if result == 300:
            return (86, 210, 255)
        if result == 100:
            return (140, 226, 72)
        return (245, 190, 64)

    def _hit_error_marker_surface(self, color, alpha, height):
        alpha = max(0, min(255, int(round(alpha / 8) * 8)))
        cache_key = (tuple(color), alpha, int(height))
        cached = self.hit_error_marker_cache.get(cache_key)
        if cached is not None:
            return cached

        if len(self.hit_error_marker_cache) > 96:
            self.hit_error_marker_cache.clear()

        marker_surface = pygame.Surface((7, height), pygame.SRCALPHA)
        pygame.draw.line(
            marker_surface,
            (*color, alpha),
            (3, 3),
            (3, height - 4),
            2
        )
        pygame.draw.line(
            marker_surface,
            (255, 255, 255, int(alpha * 0.55)),
            (4, 5),
            (4, height - 6),
            1
        )
        self.hit_error_marker_cache[cache_key] = marker_surface
        return marker_surface
