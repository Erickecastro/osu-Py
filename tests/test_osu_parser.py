import unittest

from core.osu_hitobjects import parse_hitobjects_section
from core.osu_sections import (
    parse_difficulty_section,
    parse_file_format_version,
    parse_general_section,
    parse_metadata_section,
    parse_timing_points_section,
)


class OsuParserTests(unittest.TestCase):
    def test_sections_and_hitobjects_parse_core_fields(self):
        lines = [
            "osu file format v14\n",
            "\n",
            "[General]\n",
            "AudioFilename: audio.mp3\n",
            "AudioLeadIn: 250\n",
            "\n",
            "[Metadata]\n",
            "Title: Test Song\n",
            "Artist: Test Artist\n",
            "Creator: Mapper\n",
            "Version: Hard\n",
            "\n",
            "[Difficulty]\n",
            "CircleSize:4\n",
            "ApproachRate:9.5\n",
            "OverallDifficulty:8\n",
            "HPDrainRate:6\n",
            "SliderMultiplier:1.4\n",
            "SliderTickRate:2\n",
            "\n",
            "[TimingPoints]\n",
            "0,500,4,2,1,60,1,0\n",
            "1000,-50,4,2,1,60,0,8\n",
            "\n",
            "[HitObjects]\n",
            "64,192,1000,5,0,0:0:0:0:\n",
            "128,192,1500,2,0,B|256:192|256:256,2,280\n",
            "256,192,3000,8,0,4200\n",
        ]

        def fake_slider_path(points, curve_type, slider_distance, start_x, start_y):
            return [{"x": start_x, "y": start_y}, *points]

        general = parse_general_section(lines)
        metadata = parse_metadata_section(lines)
        difficulty = parse_difficulty_section(lines)
        format_version = parse_file_format_version(lines)
        timing_points = parse_timing_points_section(lines)
        notes = parse_hitobjects_section(lines, fake_slider_path)

        self.assertEqual(format_version, 14)
        self.assertEqual(general["AudioFilename"], "audio.mp3")
        self.assertEqual(general["AudioLeadIn"], 250)
        self.assertEqual(metadata["Title"], "Test Song")
        self.assertEqual(difficulty["AR"], 9.5)
        self.assertEqual(difficulty["SliderTickRate"], 2.0)
        self.assertEqual(len(timing_points), 2)
        self.assertEqual(timing_points[1]["effects"], 8)

        self.assertEqual([note["type"] for note in notes], ["circle", "slider", "spinner"])
        self.assertTrue(notes[0]["new_combo"])
        self.assertEqual(notes[1]["repeat_count"], 2)
        self.assertEqual(notes[1]["slider_distance"], 280.0)
        self.assertEqual(notes[2]["end_time"], 4200)


if __name__ == "__main__":
    unittest.main()
