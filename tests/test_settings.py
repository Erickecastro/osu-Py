import unittest
import os
import tempfile

from core.settings import (
    GameSettings,
    clamp_cursor_scale,
    clamp_gameplay_dim,
    clamp_sensitivity
)


class SettingsTests(unittest.TestCase):
    def test_sensitivity_and_gameplay_dim_are_clamped(self):
        self.assertEqual(clamp_sensitivity("bad"), 1.0)
        self.assertEqual(clamp_sensitivity(0.1), 0.4)
        self.assertEqual(clamp_sensitivity(3.0), 2.0)
        self.assertEqual(clamp_gameplay_dim("bad"), 94)
        self.assertEqual(clamp_gameplay_dim(-20), 0)
        self.assertEqual(clamp_gameplay_dim(140), 100)

    def test_cursor_scale_is_clamped_and_serialisable(self):
        self.assertEqual(clamp_cursor_scale("bad"), 1.0)
        self.assertEqual(clamp_cursor_scale(0.1), 0.5)
        self.assertEqual(clamp_cursor_scale(3.0), 2.0)

        settings = GameSettings(cursor_scale=1.37)
        self.assertEqual(settings.cursor_scale, 1.37)

    def test_settings_are_saved_and_loaded_locally(self):
        previous_appdata = os.environ.get("APPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["APPDATA"] = tmpdir
                settings = GameSettings(
                    mouse_sensitivity=1.47,
                    cursor_scale=1.22,
                    hit_key_1=118,
                    hit_key_2=98,
                    raw_mouse_enabled=False,
                    tablet_input_enabled=True,
                    block_mouse_buttons_in_gameplay=True,
                    gameplay_dim=73
                )

                self.assertTrue(settings.save())
                loaded = GameSettings.load()

                self.assertEqual(loaded.mouse_sensitivity, 1.47)
                self.assertEqual(loaded.cursor_scale, 1.22)
                self.assertEqual(loaded.hit_key_1, 118)
                self.assertEqual(loaded.hit_key_2, 98)
                self.assertFalse(loaded.raw_mouse_enabled)
                self.assertTrue(loaded.tablet_input_enabled)
                self.assertTrue(loaded.block_mouse_buttons_in_gameplay)
                self.assertEqual(loaded.gameplay_dim, 73)
        finally:
            if previous_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = previous_appdata


if __name__ == "__main__":
    unittest.main()
