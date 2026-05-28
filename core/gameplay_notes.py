import copy

from core.beatmap_timing import slider_span_duration


def clone_notes_with_combo_data(notes, combo_colors):
    prepared_notes = copy.deepcopy(notes)
    current_combo_color = 0
    current_combo_count = 0

    for note_index, note in enumerate(prepared_notes):
        note["active"] = False
        note["hit_index"] = note_index + 1

        if note.get("new_combo") or current_combo_count == 0:
            if current_combo_count != 0:
                offset = note.get("combo_offset", 0)
                current_combo_color = (
                    current_combo_color + offset + 1
                ) % len(combo_colors)
            current_combo_count = 1
        else:
            current_combo_count += 1

        note["combo_index"] = current_combo_count
        note["combo_color"] = combo_colors[current_combo_color]

    return prepared_notes


def prepare_note_lifecycle(
    notes,
    approach_time,
    hit_fade_out_time,
    timing_points,
    slider_multiplier
):
    for render_index, note in enumerate(notes):
        note["render_index"] = render_index
        note["start_time"] = note["time"] - approach_time

        if note["type"] == "slider":
            repeat_count = note.get("repeat_count", 1)
            pixel_length = float(note.get("slider_distance", 0.0))
            span_duration = slider_span_duration(
                timing_points,
                slider_multiplier,
                note["time"],
                pixel_length
            )
            note["span_duration"] = span_duration
            note["slider_total_duration"] = span_duration * repeat_count
            note["end_time"] = (
                note["time"]
                + note["slider_total_duration"]
                + hit_fade_out_time
            )
        else:
            note["end_time"] = note["time"] + hit_fade_out_time

    return notes
