def effective_beat_length_at(timing_points, time_ms):
    if not timing_points:
        return 500.0

    base_tp = None
    inherited_tp = None

    for tp in timing_points:
        if tp["time"] > time_ms:
            break
        if tp.get("uninherited", 1) == 1:
            base_tp = tp
        else:
            inherited_tp = tp

    if base_tp is None:
        base_tp = timing_points[0]

    base_beat_len = float(base_tp.get("ms_per_beat", 500.0))

    if inherited_tp is None:
        return base_beat_len

    mpb = float(inherited_tp.get("ms_per_beat", 0.0))
    if mpb >= 0:
        return base_beat_len

    sv_mult = -100.0 / mpb if mpb != 0 else 1.0
    if sv_mult <= 0:
        sv_mult = 1.0

    return base_beat_len / sv_mult


def slider_span_duration(
    timing_points,
    slider_multiplier,
    slider_start_time_ms,
    pixel_length
):
    if pixel_length <= 0:
        return 0.0

    effective_beat_len = effective_beat_length_at(
        timing_points,
        slider_start_time_ms
    )
    denom = max(1e-6, 100.0 * float(slider_multiplier))
    beats = pixel_length / denom
    return effective_beat_len * beats
