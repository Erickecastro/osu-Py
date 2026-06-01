from core.osu_sections import section_lines


def parse_combo_offset(object_type):
    return (int(object_type) >> 4) & 7


def parse_hitobjects_section(lines, generate_slider_path):
    notes = []

    for line in section_lines(lines, "HitObjects"):
        parts = line.split(",")
        if len(parts) < 4:
            continue

        try:
            x = int(parts[0])
            y = int(parts[1])
            time = int(parts[2])
            object_type = int(parts[3])
        except:
            continue

        if object_type & 1:
            combo_offset = 0
            if object_type & 4:
                combo_offset = parse_combo_offset(object_type)

            notes.append({
                "type": "circle",
                "x": x,
                "y": y,
                "time": time,
                "new_combo": bool(object_type & 4),
                "combo_offset": combo_offset,
                "active": False
            })
            continue

        if object_type & 2:
            curve_type = "L"
            curve_points = []
            repeat_count = 1
            slider_distance = 0.0

            if len(parts) > 5:
                curve_parts = parts[5].split("|")
                if curve_parts:
                    curve_type = curve_parts[0]

                for point in curve_parts[1:]:
                    if ":" not in point:
                        continue
                    try:
                        px, py = point.split(":")
                        curve_points.append({
                            "x": int(px),
                            "y": int(py)
                        })
                    except:
                        pass

            if len(parts) > 7:
                try:
                    slider_distance = float(parts[7])
                except:
                    slider_distance = 0.0

            if len(parts) > 6:
                try:
                    repeat_count = int(parts[6])
                except:
                    repeat_count = 1

            smooth_points = generate_slider_path(
                curve_points,
                curve_type,
                slider_distance,
                x,
                y
            )

            notes.append({
                "type": "slider",
                "x": x,
                "y": y,
                "time": time,
                "curve_points": smooth_points,
                "curve_type": curve_type,
                "slider_distance": slider_distance,
                "repeat_count": repeat_count,
                "new_combo": bool(object_type & 4),
                "combo_offset": parse_combo_offset(object_type),
                "active": False
            })
            continue

        if object_type & 8:
            try:
                end_time = int(parts[5])
            except (IndexError, ValueError):
                continue

            notes.append({
                "type": "spinner",
                "x": 256,
                "y": 192,
                "time": time,
                "end_time": max(time, end_time),
                "spinner_duration": max(0, end_time - time),
                "new_combo": bool(object_type & 4),
                "combo_offset": parse_combo_offset(object_type),
                "active": False
            })

    notes.sort(
        key=lambda note: note["time"]
    )
    return notes
