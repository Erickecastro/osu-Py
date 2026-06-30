import unittest

from core.game import Game


class InputLatencyTests(unittest.TestCase):
    def test_mouse_delta_uses_sensitivity_and_clamps_to_screen(self):
        game = object.__new__(Game)
        game.WIDTH = 100
        game.HEIGHT = 80
        game.mouse_pos = (50.0, 40.0)
        game.raw_mouse_sensitivity = 0.5

        Game._apply_mouse_delta(game, (20, -10))
        self.assertEqual(game.mouse_pos, (60.0, 35.0))

        Game._apply_mouse_delta(game, (400, 400))
        self.assertEqual(game.mouse_pos, (99, 79))


if __name__ == "__main__":
    unittest.main()
