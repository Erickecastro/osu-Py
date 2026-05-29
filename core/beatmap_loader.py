import os

from core.osu_hitobjects import parse_hitobjects_section
from core.osu_sections import (
    parse_background_event,
    parse_colours_section,
    parse_difficulty_section,
    parse_metadata_section,
    parse_timing_points_section,
    read_osu_lines
)
from core.slider_paths import SliderPathGenerator


class BeatmapLoader:

    SONGS_PATH = "songs"

    def __init__(self):
        self.slider_paths = SliderPathGenerator()
        self.load_errors = []

    def load_songs(self):
        beatmaps = []
        self.load_errors.clear()

        if not os.path.exists(self.SONGS_PATH):
            os.makedirs(self.SONGS_PATH)
            return beatmaps

        for folder in os.listdir(self.SONGS_PATH):
            path = os.path.join(self.SONGS_PATH, folder)
            if not os.path.isdir(path):
                continue

            beatmap_data = {
                "name": folder,
                "path": path,
                "difficulties": []
            }

            for osu_file in self.find_osu_files(path):
                try:
                    beatmap_data["difficulties"].append(
                        self.load_difficulty(path, folder, osu_file)
                    )
                except Exception as exc:
                    self.load_errors.append((osu_file, str(exc)))

            if beatmap_data["difficulties"]:
                beatmaps.append(beatmap_data)

        beatmaps.sort(key=lambda item: item["name"].lower())
        return beatmaps

    def load_difficulty(self, path, folder, osu_file):
        lines = read_osu_lines(osu_file)
        return {
            "name": folder,
            "path": path,
            "osu_file": osu_file,
            "notes": parse_hitobjects_section(
                lines,
                self.generate_slider_path
            ),
            "metadata": parse_metadata_section(lines),
            "difficulty": parse_difficulty_section(lines),
            "timing_points": parse_timing_points_section(lines),
            "combo_colors": parse_colours_section(lines),
            "background": parse_background_event(lines)
        }

    def parse_metadata(self, osu_file):
        return parse_metadata_section(read_osu_lines(osu_file))

    def parse_timing_points(self, osu_file):
        return parse_timing_points_section(read_osu_lines(osu_file))

    def parse_colours(self, osu_file):
        return parse_colours_section(read_osu_lines(osu_file))

    def parse_difficulty(self, osu_file):
        return parse_difficulty_section(read_osu_lines(osu_file))

    def find_osu_files(self, path):
        return [
            os.path.join(path, filename)
            for filename in os.listdir(path)
            if filename.endswith(".osu")
        ]

    def parse_hitobjects(self, osu_file):
        return parse_hitobjects_section(
            read_osu_lines(osu_file),
            self.generate_slider_path
        )

    def generate_slider_path(
        self,
        points,
        curve_type="L",
        slider_distance=0.0,
        start_x=0,
        start_y=0
    ):
        return self.slider_paths.generate_slider_path(
            points,
            curve_type,
            slider_distance,
            start_x,
            start_y
        )
