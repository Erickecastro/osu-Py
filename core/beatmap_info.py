import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from core.osu_sections import read_osu_lines, section_lines
from core.utils import application_path


@dataclass
class BeatmapInfo:
    title: str
    artist: str
    creator: str
    version: str
    source: str
    tags: str
    display_name: str
    bpm_text: str
    bpm_min: float
    bpm_max: float
    length_ms: int
    object_count: int
    circle_count: int
    slider_count: int
    spinner_count: int
    cs: float
    ar: float
    od: float
    hp: float
    stars: float
    background_path: str | None
    osu_file: str
    folder_path: str
    added_time: float
    difficulty_data: dict

    @property
    def length_text(self):
        total_seconds = max(0, int(self.length_ms / 1000))
        return f"{total_seconds // 60}:{total_seconds % 60:02d}"

    @property
    def search_text(self):
        return " ".join((
            self.title,
            self.artist,
            self.creator,
            self.version,
            self.source,
            self.tags
        )).lower()


class BeatmapParser:
    @classmethod
    def from_loaded_beatmaps(cls, beatmaps):
        infos = []
        for beatmap in beatmaps:
            for difficulty in beatmap.get("difficulties", []):
                try:
                    infos.append(cls.from_difficulty(beatmap, difficulty))
                except Exception:
                    continue

        infos.sort(key=lambda info: (info.artist.lower(), info.title.lower(), info.stars))
        return infos

    @classmethod
    def from_difficulty(cls, beatmap, difficulty):
        metadata = difficulty.get("metadata", {})
        diff = difficulty.get("difficulty", {})
        timing_points = difficulty.get("timing_points", [])
        notes = difficulty.get("notes")
        osu_file = difficulty.get("osu_file", "")
        lines = read_osu_lines(osu_file) if osu_file else []
        raw_counts = cls._hitobject_counts(lines)
        general = cls._parse_section_key_values(lines, "General")
        events_bg = difficulty.get("background")

        title = cls._clean(metadata.get("Title") or metadata.get("TitleUnicode") or beatmap.get("name", "Unknown"))
        artist = cls._clean(metadata.get("Artist") or metadata.get("ArtistUnicode") or "Unknown")
        creator = cls._clean(metadata.get("Creator") or "Unknown")
        version = cls._clean(metadata.get("Version") or "Unknown")
        source = cls._clean(metadata.get("Source") or "")
        tags = cls._clean(metadata.get("Tags") or "")

        bpm_min, bpm_max = cls._bpm_range(timing_points)
        length_ms = (
            cls._length_ms(notes)
            if notes
            else cls._length_ms_from_lines(lines)
        )
        circle_count = raw_counts.get("circle", 0)
        slider_count = raw_counts.get("slider", 0)
        spinner_count = raw_counts.get("spinner", 0)
        object_count = circle_count + slider_count + spinner_count

        cs = float(diff.get("CS", 4))
        ar = float(diff.get("AR", 9))
        od = float(diff.get("OD", 8))
        hp = float(diff.get("HP", 5))
        stars = cls._estimate_stars(
            ar,
            od,
            cs,
            hp,
            object_count,
            bpm_max,
            length_ms
        )

        background_path = cls._resolve_background(
            difficulty.get("path") or beatmap.get("path", ""),
            events_bg
        )

        return BeatmapInfo(
            title=title,
            artist=artist,
            creator=creator,
            version=version,
            source=source,
            tags=tags,
            display_name=f"{artist} - {title}",
            bpm_text=cls._bpm_text(bpm_min, bpm_max),
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            length_ms=length_ms,
            object_count=object_count,
            circle_count=circle_count,
            slider_count=slider_count,
            spinner_count=spinner_count,
            cs=cs,
            ar=ar,
            od=od,
            hp=hp,
            stars=stars,
            background_path=background_path,
            osu_file=osu_file,
            folder_path=difficulty.get("path") or beatmap.get("path", ""),
            added_time=os.path.getmtime(osu_file) if osu_file and os.path.exists(osu_file) else 0,
            difficulty_data=difficulty
        )

    @staticmethod
    def _parse_section_key_values(lines, section_name):
        values = {}
        for line in section_lines(lines, section_name):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _hitobject_counts(lines):
        counts = {
            "circle": 0,
            "slider": 0,
            "spinner": 0
        }
        for line in section_lines(lines, "HitObjects"):
            parts = line.split(",")
            if len(parts) < 4:
                continue
            try:
                object_type = int(parts[3])
            except ValueError:
                continue
            if object_type & 1:
                counts["circle"] += 1
            elif object_type & 2:
                counts["slider"] += 1
            elif object_type & 8:
                counts["spinner"] += 1
        return counts

    @staticmethod
    def _bpm_range(timing_points):
        bpms = []
        for point in timing_points:
            ms_per_beat = point.get("ms_per_beat", 0)
            if point.get("uninherited", 1) == 1 and ms_per_beat > 0:
                bpms.append(60000.0 / ms_per_beat)
        if not bpms:
            return 0.0, 0.0
        return min(bpms), max(bpms)

    @staticmethod
    def _bpm_text(bpm_min, bpm_max):
        if bpm_min <= 0 or bpm_max <= 0:
            return "Unknown"
        if abs(bpm_min - bpm_max) < 0.5:
            return str(int(round(bpm_max)))
        return f"{int(round(bpm_min))}-{int(round(bpm_max))}"

    @staticmethod
    def _length_ms_from_lines(lines):
        times = []
        for line in section_lines(lines, "HitObjects"):
            parts = line.split(",")
            if len(parts) < 3:
                continue
            try:
                times.append(int(parts[2]))
            except ValueError:
                continue
        if not times:
            return 0
        return max(0, max(times) - min(times))

    @staticmethod
    def _length_ms(notes):
        if not notes:
            return 0
        first = min(note.get("time", 0) for note in notes)
        last = max(note.get("time", 0) for note in notes)
        return max(0, int(last - first))

    @staticmethod
    def _estimate_stars(ar, od, cs, hp, objects, bpm, length_ms):
        # Local approximation only; it intentionally does not replicate osu!'s official star algorithm.
        length_minutes = max(0.5, length_ms / 60000.0)
        density = objects / length_minutes
        bpm_factor = min(3.0, max(0.0, bpm) / 90.0)
        stats = (ar * 0.28) + (od * 0.25) + (cs * 0.12) + (hp * 0.08)
        density_factor = math.sqrt(max(0.0, density)) * 0.18
        stars = 0.55 + stats * 0.35 + bpm_factor * 0.42 + density_factor
        return max(0.5, min(10.0, round(stars, 2)))

    @staticmethod
    def _resolve_background(folder, filename):
        if not folder or not filename:
            return None
        path = Path(folder) / filename
        return str(path) if path.exists() else None

    @staticmethod
    def _clean(text):
        text = "".join(
            ch
            for ch in str(text)
            if ch.isprintable() and ch not in "\ufffd□■"
        )
        return " ".join(text.split()).strip() or "Unknown"


class LocalScoreManager:
    def __init__(self, path=None):
        self.path = Path(path or application_path("scores/local_scores.json"))
        self.scores = {}
        self.load()

    def load(self):
        if not self.path.exists():
            self.scores = {}
            return
        try:
            self.scores = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.scores = {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.scores, indent=2),
            encoding="utf-8"
        )

    def records_for(self, osu_file):
        return self.scores.get(str(osu_file), [])
