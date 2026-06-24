import os
import re

from core.utils import discover_user_data_directories, resolve_user_data_path
from core.osu_hitobjects import parse_hitobjects_section
from core.osu_sections import (
    parse_background_event,
    parse_colours_section,
    parse_difficulty_section,
    parse_general_section,
    parse_metadata_section,
    parse_timing_points_section,
    read_osu_lines
)
from core.slider_paths import SliderPathGenerator


class BeatmapLoader:

    def __init__(self):
        self.songs_path = resolve_user_data_path("songs")
        self.slider_paths = SliderPathGenerator()
        self.load_errors = []

    def load_songs(self):
        beatmaps = []
        self.load_errors.clear()
        beatmaps_by_path = {}

        for songs_path in discover_user_data_directories("songs"):
            for beatmap in self._load_songs_from_directory(songs_path):
                key = os.path.normcase(beatmap["path"])
                if key not in beatmaps_by_path:
                    beatmaps_by_path[key] = beatmap

        beatmaps = list(beatmaps_by_path.values())
        beatmaps.sort(key=lambda item: item["display_name"].lower())

        if beatmaps:
            self.songs_path = discover_user_data_directories("songs")[0]

        return beatmaps

    def _load_songs_from_directory(self, songs_path):
        beatmaps = []

        if not os.path.isdir(songs_path):
            return beatmaps

        try:
            folders = os.listdir(songs_path)
        except OSError as exc:
            self.load_errors.append((songs_path, str(exc)))
            return beatmaps

        for folder in folders:
            path = os.path.join(songs_path, folder)
            if not os.path.isdir(path):
                continue

            beatmap_data = {
                "name": folder,
                "display_name": self.clean_folder_name(folder),
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
                beatmap_data["display_name"] = self.display_name_from_metadata(
                    beatmap_data["difficulties"][0]["metadata"],
                    folder
                )
                beatmaps.append(beatmap_data)

        return beatmaps

    def ensure_notes_loaded(self, difficulty):
        notes = difficulty.get("notes")
        if notes is not None:
            return notes

        osu_file = difficulty.get("osu_file")
        if not osu_file:
            difficulty["notes"] = []
            return difficulty["notes"]

        lines = read_osu_lines(osu_file)
        difficulty["notes"] = parse_hitobjects_section(
            lines,
            self.generate_slider_path
        )
        return difficulty["notes"]

    def load_difficulty(self, path, folder, osu_file):
        lines = read_osu_lines(osu_file)
        metadata = parse_metadata_section(lines)
        general = parse_general_section(lines)
        return {
            "name": folder,
            "display_name": self.display_name_from_metadata(
                metadata,
                folder
            ),
            "path": path,
            "osu_file": osu_file,
            "notes": None,
            "metadata": metadata,
            "general": general,
            "audio_filename": general.get("AudioFilename", ""),
            "audio_lead_in": general.get("AudioLeadIn", 0),
            "difficulty": parse_difficulty_section(lines),
            "timing_points": parse_timing_points_section(lines),
            "combo_colors": parse_colours_section(lines),
            "background": parse_background_event(lines)
        }

    def clean_folder_name(self, folder):
        name = re.sub(r"^\s*\d+\s+", "", folder).strip()
        return name or folder

    def display_name_from_metadata(self, metadata, fallback):
        title = metadata.get("Title") or metadata.get("TitleUnicode") or ""
        artist = metadata.get("Artist") or metadata.get("ArtistUnicode") or ""

        title = self.clean_display_text(title)
        artist = self.clean_display_text(artist)

        if title and title != "Unknown" and artist and artist != "Unknown":
            return f"{artist} - {title}"

        if title and title != "Unknown":
            return title

        return self.clean_folder_name(fallback)

    def clean_display_text(self, text):
        text = "".join(
            ch
            for ch in str(text)
            if ch.isprintable() and ch not in "\ufffd□■"
        ).strip()
        return " ".join(text.split())

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
