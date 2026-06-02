import csv


def read_osu_lines(osu_file):
    with open(
        osu_file,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as file:
        return file.readlines()


def section_lines(lines, section_name):
    section_header = f"[{section_name}]"
    in_section = False

    for line in lines:
        line = line.strip()

        if line == section_header:
            in_section = True
            continue

        if in_section and line.startswith("["):
            break

        if in_section and line:
            yield line


def parse_metadata_section(lines):
    metadata = {
        "Title": "Unknown",
        "Artist": "Unknown",
        "Creator": "Unknown",
        "Version": "Unknown"
    }

    for line in section_lines(lines, "Metadata"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata


def parse_general_section(lines):
    general = {
        "AudioFilename": "",
        "AudioLeadIn": 0
    }

    for line in section_lines(lines, "General"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "AudioLeadIn":
            try:
                general[key] = int(float(value))
            except ValueError:
                general[key] = 0
        else:
            general[key] = value

    return general


def parse_timing_points_section(lines):
    timing_points = []

    for line in section_lines(lines, "TimingPoints"):
        parts = line.split(",")
        if len(parts) < 2:
            continue

        try:
            tp_time = float(parts[0])
            ms_per_beat = float(parts[1])
            uninherited = int(parts[6]) if len(parts) > 6 else 1
        except:
            continue

        timing_points.append({
            "time": tp_time,
            "ms_per_beat": ms_per_beat,
            "uninherited": uninherited
        })

    timing_points.sort(
        key=lambda tp: (
            tp["time"],
            0 if tp.get("uninherited", 1) == 1 else 1
        )
    )
    return timing_points


def parse_colours_section(lines):
    combo_colors = []

    for line in section_lines(lines, "Colours"):
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        if not key.lower().startswith("combo"):
            continue

        digits = "".join(ch for ch in key if ch.isdigit())
        try:
            index = int(digits) if digits else 0
        except:
            index = 0

        rgb = []
        for part in value.split(",")[:3]:
            try:
                rgb.append(int(part.strip()))
            except:
                break

        if len(rgb) == 3:
            combo_colors.append((index, tuple(rgb)))

    combo_colors.sort(key=lambda item: item[0])
    return [color for _, color in combo_colors]


def parse_background_event(lines):
    for line in section_lines(lines, "Events"):
        if line.startswith("//"):
            continue

        try:
            parts = next(csv.reader([line], skipinitialspace=True))
        except csv.Error:
            continue

        if len(parts) < 3:
            continue

        try:
            event_type = int(parts[0].strip())
        except:
            continue

        if event_type not in (0, 1):
            continue

        filename = parts[2].strip().strip('"')
        if filename:
            return filename

    return None


def parse_difficulty_section(lines):
    difficulty = {
        "CS": 4,
        "AR": 9,
        "OD": 8,
        "HP": 5,
        "SliderMultiplier": 1.4,
        "SliderTickRate": 1
    }

    key_map = {
        "CircleSize": "CS",
        "ApproachRate": "AR",
        "OverallDifficulty": "OD",
        "HPDrainRate": "HP",
        "SliderMultiplier": "SliderMultiplier",
        "SliderTickRate": "SliderTickRate"
    }

    for line in section_lines(lines, "Difficulty"):
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        target_key = key_map.get(key.strip())
        if target_key is None:
            continue

        try:
            difficulty[target_key] = float(value.strip())
        except:
            pass

    return difficulty
