from core.scoring import calculate_accuracy_from_points


def calculate_accuracy(hit_counts):
    total_hits = sum(hit_counts.values())
    if total_hits <= 0:
        return 100.0

    weighted = (
        (hit_counts[300] * 300)
        + (hit_counts[100] * 100)
        + (hit_counts[50] * 50)
    )

    return calculate_accuracy_from_points(weighted, total_hits * 300)


def hit_result_for_delta(
    delta,
    hit_window_300,
    hit_window_100,
    hit_window_50
):
    delta = abs(delta)
    if delta <= hit_window_300:
        return 300
    if delta <= hit_window_100:
        return 100
    if delta <= hit_window_50:
        return 50
    return None
