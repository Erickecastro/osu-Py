import unittest
from unittest import mock

from core import audio


class FakeMusic:
    def __init__(self):
        self.loaded = None
        self.play_start = None

    def stop(self):
        pass

    def load(self, path):
        self.loaded = path

    def play(self, start=0.0):
        self.play_start = start


class AudioClockTests(unittest.TestCase):
    def tearDown(self):
        audio.clear_loaded_music()

    def test_start_music_clock_reports_elapsed_without_double_offset(self):
        fake_music = FakeMusic()
        with mock.patch.object(audio.pygame.mixer, "music", fake_music):
            with mock.patch.object(
                audio.pygame.time,
                "get_ticks",
                side_effect=(5000, 5000, 5123)
            ):
                start_time = audio.start_music("song.mp3", start_ms=1200)
                elapsed = audio.get_playback_time_ms()

        self.assertEqual(start_time, 3800)
        self.assertEqual(audio.get_last_start_offset_ms(), 1200)
        self.assertEqual(elapsed, 123)
        self.assertAlmostEqual(fake_music.play_start, 1.2)


if __name__ == "__main__":
    unittest.main()
