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
        self.title_font = rounded_font(44, bold=True)
        self.large_font = rounded_font(34, bold=True)
        self.medium_font = rounded_font(24, bold=True)
        self.small_font = rounded_font(18, bold=False)
        self.tiny_font = rounded_font(14, bold=False)
        self.rank_image_cache = {}
        self.shade_surface = None
        self.shade_size = None
        self.panel_surface_cache = {}
        self._layout()

    def _layout(self):
        w, h = self.game.WIDTH, self.game.HEIGHT
        panel_w = int(_clamp(w * 0.64, 680, 920))
        panel_h = int(_clamp(h * 0.60, 420, 560))
        self.panel = pygame.Rect(0, 0, panel_w, panel_h)
        self.panel.center = (w // 2, h // 2)
        button_w = int(panel_w * 0.30)
        button_h = 44
        gap = 20
        y = self.panel.bottom - 78
        self.buttons = {
            "retry": pygame.Rect(
                self.panel.centerx - button_w - gap // 2,
                y,
                button_w,
                button_h
            ),
            "quit": pygame.Rect(
                self.panel.centerx + gap // 2,
                y,
                button_w,
                button_h
            )
        }
        self.panel_surface_cache.clear()

    def on_resize(self):
        self._layout()

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
                if rect.inflate(26, 14).collidepoint(pos):
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
        screen.fill((4, 4, 9))
        progress = _ease_out_cubic(
            (pygame.time.get_ticks() - self.created_at) / 420.0
        )
        size = screen.get_size()
        if self.shade_surface is None or self.shade_size != size:
            self.shade_surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
            self.shade_size = size
        shade = self.shade_surface
        shade.fill((0, 0, 0, int(145 * progress)))
        screen.blit(shade, (0, 0))

        panel = self.panel.copy()
        panel.y += int((1.0 - progress) * 26)
        panel_surface = self.panel_surface_cache.get(panel.size)
        if panel_surface is None:
            panel_surface = pygame.Surface(panel.size, pygame.SRCALPHA).convert_alpha()
            pygame.draw.rect(panel_surface, (15, 15, 29, 236), panel_surface.get_rect(), border_radius=18)
            pygame.draw.rect(panel_surface, (255, 215, 86, 230), panel_surface.get_rect(), 2, border_radius=18)
            pygame.draw.rect(panel_surface, (255, 255, 255, 20), panel_surface.get_rect().inflate(-8, -8), 1, border_radius=14)
            self.panel_surface_cache[panel.size] = panel_surface
        screen.blit(panel_surface, panel)

        title = self._song_title()
        self._blit_text(screen, self.medium_font, title, (245, 245, 255), (panel.x + 28, panel.y + 24))
        subtitle = "Results saved locally" if self.save_record else "Local score details"
        self._blit_text(screen, self.tiny_font, subtitle, (188, 198, 220), (panel.x + 30, panel.y + 55))

        rank = self.result.get("rank", "D")
        rank_img = self.rank_images.get(rank)
        rank_rect = pygame.Rect(panel.x + 34, panel.y + 98, 178, 178)
        if rank_img is not None:
            cache_key = (rank, rank_rect.size)
            scaled = self.rank_image_cache.get(cache_key)
            if scaled is None:
                scaled = pygame.transform.smoothscale(
                    rank_img,
                    rank_rect.size
                ).convert_alpha()
                self.rank_image_cache[cache_key] = scaled
            screen.blit(scaled, rank_rect)
        else:
            self._blit_text(screen, self.title_font, rank, (255, 235, 100), rank_rect.center, center=True)

        score = int(self.result.get("score", 0))
        accuracy = float(self.result.get("accuracy", 0.0))
        combo = int(self.result.get("combo", 0))
        count_300 = int(self.result.get("hit_300", 0))
        count_100 = int(self.result.get("hit_100", 0))
        count_50 = int(self.result.get("hit_50", 0))
        misses = int(self.result.get("misses", 0))

        stats_x = panel.x + 250
        stats_y = panel.y + 108
        self._blit_text(screen, self.large_font, f"{score:08d}", (255, 255, 255), (stats_x, stats_y))
        self._blit_text(screen, self.medium_font, f"{accuracy:05.2f}%", (145, 224, 255), (stats_x, stats_y + 48))
        self._blit_text(screen, self.small_font, f"Max Combo: {combo}x", (235, 235, 245), (stats_x, stats_y + 88))

        rows = (
            ("300", count_300, (130, 220, 255)),
            ("100", count_100, (120, 255, 145)),
            ("50", count_50, (255, 214, 90)),
            ("Miss", misses, (255, 104, 124))
        )
        row_y = stats_y + 132
        for label, value, color in rows:
            self._blit_text(screen, self.small_font, label, color, (stats_x, row_y))
            self._blit_text(screen, self.small_font, str(value), (245, 245, 255), (stats_x + 86, row_y))
            row_y += 30

        self._draw_button(screen, "retry", "Retry")
        self._draw_button(screen, "quit", "Quit")

    def _draw_button(self, screen, action, label):
        rect = self.buttons[action]
        hover = self.button_hover.get(action, 0.0)
        grow = int(10 * hover)
        draw_rect = rect.inflate(grow * 2, int(5 * hover))
        shadow_rect = draw_rect.move(int(8 + 4 * hover), int(8 + 2 * hover))
        pygame.draw.rect(screen, (0, 0, 0, 150), shadow_rect, border_radius=shadow_rect.height // 2)
        fill = int(242 + 13 * hover)
        pygame.draw.rect(screen, (fill, fill, fill, 248), draw_rect, border_radius=draw_rect.height // 2)
        pygame.draw.rect(screen, (66, 66, 72, int(155 + 45 * hover)), draw_rect, 1, border_radius=draw_rect.height // 2)
        self._blit_text(screen, self.medium_font, label, (58, 58, 64), draw_rect.center, center=True)

    def _song_title(self):
        artist = self.beatmap.get("artist", "")
        title = self.beatmap.get("title", self.beatmap.get("name", "Unknown"))
        version = self.beatmap.get("metadata", {}).get("Version", "")
        base = " - ".join(part for part in (artist, title) if part)
        return f"{base} [{version}]" if version else base

    def _blit_text(self, screen, font, text, color, pos, center=False):
        surf = font.render(str(text), True, color)
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        screen.blit(surf, rect)

    def _retry(self):
        from scenes.gameplay_scene import GameplayScene
        stack = self.game.scene_manager.scene_stack
        previous_is_gameplay = (
            len(stack) >= 2
            and stack[-2].__class__.__name__ == "GameplayScene"
        )
        if len(stack) <= 1:
            self.game.scene_manager.set_scene(GameplayScene(self.game, self.beatmap))
            return
        self.game.scene_manager.pop_scene()
        if previous_is_gameplay and len(self.game.scene_manager.scene_stack) > 1:
            self.game.scene_manager.pop_scene()
        self.game.scene_manager.push_scene(GameplayScene(self.game, self.beatmap))

    def _quit(self):
        stack = self.game.scene_manager.scene_stack
        if len(stack) >= 2 and stack[-2].__class__.__name__ == "GameplayScene":
            self.game.scene_manager.pop_scene()
            if len(self.game.scene_manager.scene_stack) > 1:
                self.game.scene_manager.pop_scene()
            else:
                from scenes.song_select_scene import SongSelectScene
                self.game.scene_manager.set_scene(SongSelectScene(self.game))
            return
        if len(stack) > 1:
            self.game.scene_manager.pop_scene()
            return
        from scenes.song_select_scene import SongSelectScene
        self.game.scene_manager.set_scene(SongSelectScene(self.game))
