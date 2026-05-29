import pygame


class GameplayHUDRenderer:
    def __init__(self, font):
        self.font = font
        self.text_cache = {}
        self.health_bar_cache = {}

    def text_surface(self, text, color=(255, 255, 255)):
        key = (text, tuple(color))
        cached = self.text_cache.get(key)
        if cached is not None:
            return cached

        if len(self.text_cache) > 96:
            self.text_cache.clear()

        surface = self.font.render(
            text,
            True,
            color
        )
        self.text_cache[key] = surface
        return surface

    def draw(
        self,
        screen,
        beatmap,
        current_time,
        score,
        accuracy,
        combo,
        health=1.0
    ):
        score_text = self.text_surface(
            f"{score:08d}",
            (255, 255, 255)
        )
        accuracy_text = self.text_surface(
            f"{accuracy:05.2f}%",
            (255, 255, 255)
        )
        combo_text = self.text_surface(
            f"{combo}x",
            (255, 255, 255)
        )

        screen.blit(
            score_text,
            (
                screen.get_width() - score_text.get_width() - 20,
                20
            )
        )
        screen.blit(
            accuracy_text,
            (
                screen.get_width() - accuracy_text.get_width() - 20,
                60
            )
        )
        screen.blit(
            combo_text,
            (
                20,
                screen.get_height() - combo_text.get_height() - 20
            )
        )

        self.draw_health_bar(screen, health)

    def draw_health_bar(self, screen, health):
        health = max(0.0, min(1.0, float(health)))
        width = min(420, max(220, int(screen.get_width() * 0.28)))
        height = 16
        x = (screen.get_width() - width) // 2
        y = 22
        fill_width = int(width * health)
        cache_key = (width, height, fill_width)
        cached = self.health_bar_cache.get(cache_key)
        if cached is not None:
            screen.blit(cached, (x, y))
            return

        if len(self.health_bar_cache) > 128:
            self.health_bar_cache.clear()

        surface = pygame.Surface(
            (width, height),
            pygame.SRCALPHA
        )

        pygame.draw.rect(
            surface,
            (18, 18, 18),
            (0, 0, width, height),
            border_radius=height // 2
        )
        if fill_width > 0:
            if health > 0.55:
                fill_color = (104, 220, 116)
            elif health > 0.25:
                fill_color = (235, 202, 83)
            else:
                fill_color = (230, 86, 86)

            pygame.draw.rect(
                surface,
                fill_color,
                (0, 0, fill_width, height),
                border_radius=height // 2
            )
        pygame.draw.rect(
            surface,
            (255, 255, 255),
            (0, 0, width, height),
            width=2,
            border_radius=height // 2
        )
        self.health_bar_cache[cache_key] = surface
        screen.blit(surface, (x, y))
