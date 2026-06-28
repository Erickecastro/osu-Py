import unittest

from core.settings import GameSettings, clamp_cursor_scale


class SettingsTests(unittest.TestCase):
    def test_cursor_scale_is_clamped_and_serialisable(self):
        self.assertEqual(clamp_cursor_scale("bad"), 1.0)
        self.assertEqual(clamp_cursor_scale(0.1), 0.5)
        self.assertEqual(clamp_cursor_scale(3.0), 2.0)

        settings = GameSettings(cursor_scale=1.37)
        self.assertEqual(settings.cursor_scale, 1.37)


if __name__ == "__main__":
    unittest.main()
