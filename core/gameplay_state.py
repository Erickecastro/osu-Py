def activate_due_notes(
    notes,
    active_notes,
    next_note_index,
    current_time,
    approach_time
):
    while next_note_index < len(notes):
        note = notes[next_note_index]
        start_time = note.get(
            "start_time",
            note["time"] - approach_time
        )
        if current_time < start_time:
            break

        note["active"] = True
        active_notes.append(note)
        next_note_index += 1

    return next_note_index


def judge_missed_notes(active_notes, current_time, hit_window_50, add_hit_result):
    for note in active_notes:
        if note.get("judged"):
            continue
        if note["type"] not in ("circle", "slider"):
            continue
        if current_time > note["time"] + hit_window_50:
            add_hit_result(note, 0)


def prune_inactive_notes(
    active_notes,
    current_time,
    hit_fade_out_time,
    hit_explosion_duration
):
    return [
        note
        for note in active_notes
        if current_time <= (
            note.get(
                "end_time",
                note["time"] + hit_fade_out_time
            )
            + hit_explosion_duration
        )
    ]
