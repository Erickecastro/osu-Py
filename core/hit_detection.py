def find_best_hit_object(
    active_notes,
    current_time,
    pos,
    hit_radius,
    scale_position,
    hit_result_for_delta,
    can_attempt_hit=None
):
    best_note = None
    best_result = None
    best_delta = None

    for note in active_notes:
        if note.get("judged"):
            continue

        if note["type"] == "slider" and note.get("head_hit"):
            continue

        if note["type"] not in ("circle", "slider"):
            continue

        if can_attempt_hit is not None and not can_attempt_hit(note):
            continue

        delta = current_time - note["time"]
        result = hit_result_for_delta(delta)
        if result is None:
            continue

        scaled_pos = note.get("scaled_pos")
        if scaled_pos is None:
            scaled_pos = scale_position(
                note["x"],
                note["y"]
            )
        scaled_x, scaled_y = scaled_pos
        dx = pos[0] - scaled_x
        dy = pos[1] - scaled_y
        distance = (dx * dx + dy * dy) ** 0.5

        if distance > hit_radius:
            continue

        abs_delta = abs(delta)
        if best_delta is None or abs_delta < best_delta:
            best_note = note
            best_result = result
            best_delta = abs_delta

    return best_note, best_result
