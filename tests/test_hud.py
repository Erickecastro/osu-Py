import unittest

import pygame

from rendering.hud import GameplayHUDRenderer


class GameplayHUDRendererTests(unittest.TestCase):
    def setUp(self):
        if not pygame.get_init():
            pygame.init()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1, 1))

    def test_score_animation_normalizes_complex_state(self):
        font = pygame.font.Font(None, 18)
        hud = GameplayHUDRenderer(font)
        hud.display_score = 0.0J

        value = hud._animated_score(123, 0.0)

        self.assertIsInstance(value, int)
        self.assertEqual(value, 123)


if __name__ == "__main__":
    unittest.main()
