import unittest
from unittest.mock import patch

from core.game import Game


class DisplayConfigTests(unittest.TestCase):
    def test_auto_target_fps_uses_refresh_multiplier_with_minimum(self):
        game = object.__new__(Game)
        game.display_refresh_rate = 80

        self.assertGreaterEqual(Game._resolve_target_fps(game), 480)

    def test_fullscreen_mode_defaults_invalid_values_to_desktop(self):
        game = object.__new__(Game)

        with patch("core.game.FULLSCREEN_MODE", "nonsense"):
            self.assertEqual(Game._fullscreen_mode(game), "desktop")

        with patch("core.game.FULLSCREEN_MODE", "exclusive"):
            self.assertEqual(Game._fullscreen_mode(game), "exclusive")


if __name__ == "__main__":
    unittest.main()
