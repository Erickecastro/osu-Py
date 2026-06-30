import unittest
from unittest.mock import patch

from core.game import Game


class _DummySettings:
    def __init__(self):
        self.mouse_sensitivity = 0.75
        self.raw_mouse_enabled = True
        self.tablet_input_enabled = False
        self.saved = False

    def save(self):
        self.saved = True
        return True


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

    def test_system_pointer_mode_ignores_in_game_sensitivity(self):
        game = object.__new__(Game)
        game.WIDTH = 100
        game.HEIGHT = 80
        game.mouse_pos = (50.0, 40.0)
        game.raw_mouse_enabled = False
        game.raw_mouse_preferred = False
        game.tablet_input_enabled = False
        game.raw_mouse_sensitivity = 0.5

        with patch("pygame.mouse.get_pos", return_value=(20, 30)), \
                patch("pygame.mouse.get_rel", return_value=(200, 200)):
            self.assertEqual(Game.sample_mouse_now(game), (20.0, 30.0))

    def test_disabling_raw_mouse_resets_visible_sensitivity_to_system_default(self):
        game = object.__new__(Game)
        game.mouse_pos = (10.0, 10.0)
        game.raw_mouse_preferred = True
        game.raw_mouse_sensitivity = 0.75
        game.tablet_input_enabled = False
        game.settings = _DummySettings()
        game.sync_input_mode = lambda pos=None: None

        Game.set_raw_mouse_enabled(game, False)

        self.assertFalse(game.raw_mouse_preferred)
        self.assertEqual(game.raw_mouse_sensitivity, 1.0)
        self.assertEqual(game.settings.mouse_sensitivity, 1.0)
        self.assertTrue(game.settings.saved)

    def test_loaded_raw_off_sensitivity_uses_system_default(self):
        game = object.__new__(Game)
        game.settings = _DummySettings()
        game.settings.raw_mouse_enabled = False
        game.settings.mouse_sensitivity = 0.8
        game.raw_mouse_preferred = False
        game.tablet_input_enabled = False
        game.raw_mouse_sensitivity = 0.8

        Game._normalize_system_pointer_sensitivity(game)

        self.assertEqual(game.raw_mouse_sensitivity, 1.0)
        self.assertEqual(game.settings.mouse_sensitivity, 1.0)
        self.assertTrue(game.settings.saved)


if __name__ == "__main__":
    unittest.main()
