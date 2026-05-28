import pygame


class GameplayHUDRenderer:
    def __init__(self, font):
        self.font = font
        self.text_cache = {}

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

    def draw(self, screen, beatmap, current_time, score, accuracy, combo):
        title = beatmap["metadata"].get(
            "Title",
            beatmap["name"]
        )
        version = beatmap["metadata"].get(
            "Version",
            "Unknown"
        )

        title_text = self.text_surface(
            f"{title} [{version}]",
            (255, 255, 255)
        )
        screen.blit(title_text, (20, 20))

        display_time = int(current_time // 25) * 25
        time_text = self.text_surface(
            f"{display_time} ms",
            (0, 255, 0)
        )
        screen.blit(time_text, (20, 60))

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
