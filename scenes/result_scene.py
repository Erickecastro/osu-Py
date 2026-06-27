from pathlib import Path
import math

import pygame

from core.assets import load_image
from core.beatmap_info import LocalScoreManager
from core.fonts import rounded_font
from scenes.base_scene import BaseScene


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _ease_out_cubic(value):
    value = _clamp(value, 0.0, 1.0)
    return 1.0 - ((1.0 - value) ** 3)


class ResultScene(BaseScene):
    uses_ui = False
    draws_own_cursor = False

    BUTTON_COLORS = {
        "retry": (222, 112, 34),
        "quit": (218, 58, 66)
    }

    def __init__(self, game, beatmap, result, save_record=True):
        super().__init__(game)
        self.beatmap = beatmap
        self.result = dict(result)
        self.save_record = bool(save_record)
        self.created_at = pygame.time.get_ticks()
        self.score_manager = LocalScoreManager()
        self.saved_record = (
            self.score_manager.add_record(
                beatmap.get("osu_file", ""),
                self.result
            )
            if save_record
            else self.result
        )
        self.buttons = {}
        self.button_hover = {}
        self.rank_images = {
            "SS": load_image("ranking-X.png"),
            "S": load_image("ranking-S.png"),
            "A": load_image("ranking-A.png"),
            "B": load_image("ranking-B.png"),
            "C": load_image("ranking-C.png"),
            "D": load_image("ranking-D.png")
        }
        self.panel_image = load_image("results-menu.png")
        self.button_image = load_image("button.png")
        self.title_font = rounded_font(25, bold=True)
        self.score_font = rounded_font(38, bold=True)
        self.large_font = rounded_font(34, bold=True)
        self.medium_font = rounded_font(23, bold=True)
        self.small_font = rounded_font(19, bold=True)
        self.tiny_font = rounded_font(14, bold=False)
        self.text_cache = {}
        self.rank_image_cache = {}
        self.button_cache = {}
        self.shade_surface = None
        self.shade_size = None
        self.background_surface = None
        self.background_size = None
        self.background_source = None
        self.panel_surface_cache = {}
        self._load_background()
        self._layout()

    def _layout(self):
        w, h = self.game.WIDTH, self.game.HEIGHT
        if self.panel_image is not None:
            iw, ih = self.panel_image.get_size()
            scale = min(w * 0.78 / iw, h * 0.64 / ih, 1.25)
            panel_w = int(iw * scale)
            panel_h = int(ih * scale)
        else:
            panel_w = int(_clamp(w * 0.64, 680, 920))
            panel_h = int(_clamp(h * 0.60, 420, 560))
        self.panel = pygame.Rect(0, 0, panel_w, panel_h)
        self.panel.center = (w // 2, h // 2)

        button_h = int(_clamp(panel_h * 0.105, 42, 56))
        if self.button_image is not None:
            aspect = self.button_image.get_width() / max(1, self.button_image.get_height())
            button_w = int(round(button_h * aspect))
        else:
            button_w = int(panel_w * 0.24)
        gap = int(panel_w * 0.045)
        y = self.panel.y + int(panel_h * 0.83)
        total_w = button_w * 2 + gap
        x = self.panel.x + int(panel_w * 0.89) - total_w
        self.buttons = {
            "retry": pygame.Rect(x, y, button_w, button_h),
            "quit": pygame.Rect(x + button_w + gap, y, button_w, button_h)
        }
        self.panel_surface_cache.clear()

    def on_resize(self):
        self._layout()
        self.background_surface = None
        self.background_size = None

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self._retry()
                return
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_BACKSPACE):
                self._quit()
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            for action, rect in self.buttons.items():
                if rect.inflate(28, 18).collidepoint(pos):
                    if action == "retry":
                        self._retry()
                    else:
                        self._quit()
                    return

    def update(self, dt):
        mouse_pos = self.game.mouse_pos
        for action, rect in self.buttons.items():
            target = 1.0 if rect.collidepoint(mouse_pos) else 0.0
            current = self.button_hover.get(action, 0.0)
            self.button_hover[action] = current + (target - current) * (
                1.0 - pow(0.0002, min(dt, 0.05))
            )

    def render(self, screen):
        self._draw_background(screen)
        progress = _ease_out_cubic(
            (pygame.time.get_ticks() - self.created_at) / 420.0
        )
        size = screen.get_size()
        if self.shade_surface is None or self.shade_size != size:
            self.shade_surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
            self.shade_size = size
        self.shade_surface.fill((12, 12, 18, int(178 * progress)))
        screen.blit(self.shade_surface, (0, 0))

        panel = self.panel.copy()
        panel.y += int((1.0 - progress) * 22)
        self._draw_panel(screen, panel)
        self._draw_result_contents(screen, panel)
        self._draw_button(screen, "retry", "Retry")
        self._draw_button(screen, "quit", "Quit")

    def _draw_background(self, screen):
        source = self._background_path()
        size = screen.get_size()
        if source is None:
            screen.fill((7, 7, 12))
            return

        if (
            self.background_surface is None
            or self.background_size != size
            or self.background_source != source
        ):
            try:
                image = pygame.image.load(str(source)).convert()
            except pygame.error:
                self.background_surface = None
                self.background_size = None
                screen.fill((7, 7, 12))
                return
            iw, ih = image.get_size()
            scale = max(size[0] / iw, size[1] / ih)
            scaled = pygame.transform.smoothscale(
                image,
                (int(iw * scale), int(ih * scale))
            ).convert()
            self.background_surface = scaled
            self.background_size = size
            self.background_source = source

        rect = self.background_surface.get_rect(center=(size[0] // 2, size[1] // 2))
        screen.blit(self.background_surface, rect)

    def _draw_panel(self, screen, panel):
        if self.panel_image is not None:
            cached = self.panel_surface_cache.get(panel.size)
            if cached is None:
                cached = pygame.transform.smoothscale(
                    self.panel_image,
                    panel.size
                ).convert_alpha()
                self.panel_surface_cache[panel.size] = cached
            screen.blit(cached, panel)
            return

        fallback = pygame.Surface(panel.size, pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(fallback, (15, 15, 29, 236), fallback.get_rect(), border_radius=18)
        pygame.draw.rect(fallback, (255, 215, 86, 230), fallback.get_rect(), 2, border_radius=18)
        screen.blit(fallback, panel)

    def _draw_result_contents(self, screen, panel):
        title = self._song_title()
        self._blit_text(screen, self.title_font, title, (246, 246, 255), (
            panel.x + int(panel.width * 0.035),
            panel.y + int(panel.height * 0.065)
        ))
        subtitle = "Results saved locally" if self.save_record else "Local score details"
        self._blit_text(screen, self.tiny_font, subtitle, (193, 202, 224), (
            panel.x + int(panel.width * 0.037),
            panel.y + int(panel.height * 0.14)
        ))

        score = int(self.result.get("score", 0))
        accuracy = float(self.result.get("accuracy", 0.0))
        combo = int(self.result.get("combo", 0))
        count_300 = int(self.result.get("hit_300", 0))
        count_100 = int(self.result.get("hit_100", 0))
        count_50 = int(self.result.get("hit_50", 0))
        misses = int(self.result.get("misses", 0))

        left_x = panel.x + int(panel.width * 0.088)
        value_x = panel.x + int(panel.width * 0.218)
        score_center = (
            panel.x + int(panel.width * 0.154),
            panel.y + int(panel.height * 0.247)
        )
        self._blit_text(
            screen,
            self.score_font,
            f"{score:08d}",
            (255, 255, 255),
            score_center,
            center=True
        )

        row_centers = (
            panel.y + int(panel.height * 0.354),
            panel.y + int(panel.height * 0.428),
            panel.y + int(panel.height * 0.502),
            panel.y + int(panel.height * 0.578)
        )
        rows = (
            ("300", count_300, (130, 220, 255)),
            ("100", count_100, (120, 255, 145)),
            ("50", count_50, (255, 214, 90)),
            ("Miss", misses, (255, 104, 124))
        )
        for (label, value, color), row_y in zip(rows, row_centers):
            self._blit_text(
                screen,
                self.small_font,
                label,
                color,
                (left_x, row_y),
                center=True
            )
            self._blit_text(screen, self.small_font, str(value), (245, 245, 255), (value_x, row_y), center=True)

        self._blit_text(
            screen,
            self.medium_font,
            f"{accuracy:05.2f}%",
            (145, 224, 255),
            (
                panel.x + int(panel.width * 0.226),
                panel.y + int(panel.height * 0.666)
            ),
            center=True
        )
        self._blit_text(
            screen,
            self.small_font,
            f"{combo}x",
            (235, 235, 245),
            (
                panel.x + int(panel.width * 0.226),
                panel.y + int(panel.height * 0.750)
            ),
            center=True
        )

        rank = self.result.get("rank", "D")
        rank_img = self.rank_images.get(rank)
        rank_box = int(panel.height * 0.75)
        rank_center = (
            panel.x + int(panel.width * 0.69),
            panel.y + int(panel.height * 0.44)
        )
        self._draw_rank_glow(screen, rank_center, rank_box)
        if rank_img is not None:
            iw, ih = rank_img.get_size()
            scale = rank_box / max(1, max(iw, ih))
            rank_size = (
                max(1, int(round(iw * scale))),
                max(1, int(round(ih * scale)))
            )
            rank_rect = pygame.Rect(0, 0, *rank_size)
            rank_rect.center = rank_center
            cache_key = (rank, rank_size)
            scaled = self.rank_image_cache.get(cache_key)
            if scaled is None:
                scaled = pygame.transform.smoothscale(
                    rank_img,
                    rank_size
                ).convert_alpha()
                self.rank_image_cache[cache_key] = scaled
            screen.blit(scaled, rank_rect)
        else:
            self._blit_text(screen, self.large_font, rank, (255, 235, 100), rank_center, center=True)

    def _draw_rank_glow(self, screen, center, size):
        elapsed = (pygame.time.get_ticks() - self.created_at) * 0.001
        radius = int(size * 0.87)
        layer_size = radius * 2 + 28
        layer = pygame.Surface((layer_size, layer_size), pygame.SRCALPHA)
        local = (layer_size // 2, layer_size // 2)
        for ring, alpha in ((0.28, 32), (0.44, 24), (0.62, 16)):
            pygame.draw.circle(
                layer,
                (115, 215, 255, alpha),
                local,
                int(radius * ring),
                max(1, int(size * 0.012))
            )
        for i in range(18):
            angle = elapsed * 0.58 + (i / 18.0) * math.tau
            pulse = 0.76 + 0.24 * math.sin(elapsed * 1.0 + i * 1.7)
            inner = radius * (0.12 + (i % 2) * 0.04)
            outer = radius * (0.52 + (i % 3) * 0.08) * pulse
            start = (
                local[0] + int(math.cos(angle) * inner),
                local[1] + int(math.sin(angle) * inner)
            )
            end = (
                local[0] + int(math.cos(angle) * outer),
                local[1] + int(math.sin(angle) * outer)
            )
            pygame.draw.line(
                layer,
                (130, 225, 255, 32 + (i % 3) * 13),
                start,
                end,
                max(1, int(size * 0.014))
            )
        for i in range(7):
            angle = -elapsed * 0.78 + (i / 7.0) * math.tau
            point = (
                local[0] + int(math.cos(angle) * radius * 0.48),
                local[1] + int(math.sin(angle) * radius * 0.48)
            )
            pygame.draw.circle(
                layer,
                (205, 246, 255, 54),
                point,
                max(2, int(size * 0.030))
            )
        screen.blit(layer, layer.get_rect(center=center))

    def _draw_button(self, screen, action, label):
        rect = self.buttons[action]
        hover = self.button_hover.get(action, 0.0)
        if self.button_image is not None:
            hover_h = rect.height + int(2 * hover)
            aspect = self.button_image.get_width() / max(1, self.button_image.get_height())
            draw_rect = pygame.Rect(0, 0, int(round(hover_h * aspect)), hover_h)
            draw_rect.center = rect.center
        else:
            grow = int(10 * hover)
            draw_rect = rect.inflate(grow * 2, int(5 * hover))
        button_surface = self._button_surface(action, draw_rect.size, hover)
        if button_surface is not None:
            screen.blit(button_surface, draw_rect)
        else:
            pygame.draw.rect(screen, self.BUTTON_COLORS.get(action, (240, 120, 80)), draw_rect, border_radius=draw_rect.height // 2)
        self._blit_text(screen, self.medium_font, label, (255, 255, 255), draw_rect.center, center=True)

    def _button_surface(self, action, size, hover):
        if self.button_image is None:
            return None
        size = (max(1, int(size[0])), max(1, int(size[1])))
        hover_bucket = int(round(_clamp(hover, 0.0, 1.0) * 8))
        key = (action, size, hover_bucket)
        cached = self.button_cache.get(key)
        if cached is not None:
            return cached
        source = pygame.transform.smoothscale(self.button_image, size).convert_alpha()
        surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
        hover_amount = hover_bucket / 8.0
        base = self.BUTTON_COLORS.get(action, (240, 120, 80))
        color = tuple(
            int(channel + (255 - channel) * 0.13 * hover_amount)
            for channel in base
        )
        for y in range(size[1]):
            for x in range(size[0]):
                alpha = source.get_at((x, y)).a
                if alpha:
                    surface.set_at((x, y), (*color, alpha))
        self.button_cache[key] = surface
        return surface

    def _background_path(self):
        explicit = self.beatmap.get("background_path")
        if explicit:
            path = Path(explicit)
            return path if path.exists() else None
        background = self.beatmap.get("background")
        folder = self.beatmap.get("path")
        if background and folder:
            path = Path(folder) / background
            return path if path.exists() else None
        return None

    def _load_background(self):
        self.background_source = self._background_path()

    def _song_title(self):
        artist = self.beatmap.get("artist", "")
        title = self.beatmap.get("title", self.beatmap.get("name", "Unknown"))
        metadata = self.beatmap.get("metadata", {})
        if metadata:
            artist = metadata.get("Artist") or metadata.get("ArtistUnicode") or artist
            title = metadata.get("Title") or metadata.get("TitleUnicode") or title
        version = metadata.get("Version", "")
        base = " - ".join(part for part in (artist, title) if part)
        return f"{base} [{version}]" if version else base

    def _blit_text(self, screen, font, text, color, pos, center=False):
        key = (id(font), str(text), tuple(color))
        surf = self.text_cache.get(key)
        if surf is None:
            surf = font.render(str(text), True, color)
            if len(self.text_cache) > 96:
                self.text_cache.clear()
            self.text_cache[key] = surf
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        screen.blit(surf, rect)

    def _retry(self):
        pygame.mixer.music.stop()
        from scenes.gameplay_scene import GameplayScene
        stack = self.game.scene_manager.scene_stack
        previous_is_gameplay = (
            len(stack) >= 2
            and stack[-2].__class__.__name__ == "GameplayScene"
        )
        if len(stack) <= 1:
            self.game.scene_manager.set_scene_factory(
                lambda: GameplayScene(self.game, self.beatmap)
            )
            return
        self.game.scene_manager.pop_scene()
        if previous_is_gameplay and len(self.game.scene_manager.scene_stack) > 1:
            self.game.scene_manager.pop_scene()
        self.game.scene_manager.push_scene_factory(
            lambda: GameplayScene(self.game, self.beatmap)
        )

    def _quit(self):
        stack = self.game.scene_manager.scene_stack
        if len(stack) >= 2 and stack[-2].__class__.__name__ == "GameplayScene":
            self.game.scene_manager.pop_scene()
            if len(self.game.scene_manager.scene_stack) > 1:
                self.game.scene_manager.pop_scene()
            else:
                from scenes.song_select_scene import SongSelectScene
                self.game.scene_manager.set_scene_factory(
                    lambda: SongSelectScene(self.game)
                )
            return
        if len(stack) > 1:
            self.game.scene_manager.pop_scene()
            return
        from scenes.song_select_scene import SongSelectScene
        self.game.scene_manager.set_scene_factory(lambda: SongSelectScene(self.game))
