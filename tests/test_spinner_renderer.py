import unittest

import pygame

from rendering.spinner import SpinnerRenderer


class SpinnerRendererCacheTests(unittest.TestCase):
    def test_spinner_center_uses_screen_midpoint(self):
        class Game:
            WIDTH = 1279
            HEIGHT = 719

        class Scene:
            game = Game()

        renderer = SpinnerRenderer.__new__(SpinnerRenderer)
        renderer.scene = Scene()

        self.assertEqual(renderer._spinner_center(), (640, 360))

    def test_trim_transparent_padding_keeps_visible_spinner_content(self):
        renderer = SpinnerRenderer.__new__(SpinnerRenderer)
        image = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(image, (255, 255, 255, 255), (32, 32), 8)

        trimmed = renderer._trim_transparent_padding(image, padding=2)

        self.assertLess(trimmed.get_width(), image.get_width())
        self.assertLess(trimmed.get_height(), image.get_height())
        self.assertGreaterEqual(trimmed.get_bounding_rect().width, 16)
        self.assertGreaterEqual(trimmed.get_bounding_rect().height, 16)

    def test_scaled_cache_is_bounded_for_many_approach_sizes(self):
        renderer = SpinnerRenderer.__new__(SpinnerRenderer)
        renderer.cache = {}
        renderer.cache_limit = 18
        renderer.scaled_cache_limit = 6
        renderer.rotated_cache_limit = 8

        image = pygame.Surface((32, 32), pygame.SRCALPHA)
        image.fill((255, 255, 255, 255))

        for diameter in range(48, 240, 4):
            renderer._scaled(image, diameter, quantize_step=8)

        scaled_keys = [
            key
            for key in renderer.cache
            if isinstance(key, tuple)
            and len(key) == 2
            and isinstance(key[1], int)
        ]

        self.assertLessEqual(len(renderer.cache), renderer.cache_limit)
        self.assertLessEqual(len(scaled_keys), renderer.scaled_cache_limit)


if __name__ == "__main__":
    unittest.main()
