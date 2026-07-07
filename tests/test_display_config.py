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

    def test_opengl_window_is_opt_in_while_texture_bridge_is_experimental(self):
        game = object.__new__(Game)
        game.opengl_window_failed = False

        with patch.dict(
            "os.environ",
            {
                "PYOSU_ENABLE_OPENGL_WINDOW": "",
                "PYOSU_FORCE_MODERNGL": "",
                "PYOSU_DISABLE_OPENGL_WINDOW": "",
                "PYOSU_DISABLE_MODERNGL": "",
            },
            clear=False
        ):
            self.assertFalse(Game._should_use_opengl_window(game))
            self.assertEqual(
                game.opengl_window_status,
                "disabled_window_default"
            )

    def test_opengl_window_opt_in_checks_moderngl_availability(self):
        game = object.__new__(Game)
        game.opengl_window_failed = False

        with patch.dict(
            "os.environ",
            {"PYOSU_ENABLE_OPENGL_WINDOW": "1"},
            clear=False
        ), patch.dict(
            "sys.modules",
            {"moderngl": object()}
        ):
            self.assertTrue(Game._should_use_opengl_window(game))
            self.assertEqual(game.opengl_window_status, "ready")


if __name__ == "__main__":
    unittest.main()
