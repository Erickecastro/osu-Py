def health_drain_per_second(hp_drain_rate):
    hp = max(0.0, min(10.0, float(hp_drain_rate)))
    return 0.004 + (hp * 0.002)


def health_delta_for_result(result, hp_drain_rate):
    hp = max(0.0, min(10.0, float(hp_drain_rate)))
    hp_factor = hp / 10.0

    if result == 300:
        return 0.034 - (0.010 * hp_factor)
    if result == 100:
        return 0.018 - (0.006 * hp_factor)
    if result == 50:
        return -0.018 - (0.022 * hp_factor)
    return -0.055 - (0.014 * hp)


def apply_health_drain(health, dt, hp_drain_rate):
    return max(
        0.0,
        min(
            1.0,
            float(health) - (health_drain_per_second(hp_drain_rate) * dt)
        )
    )


def apply_health_result(health, result, hp_drain_rate):
    return max(
        0.0,
        min(
            1.0,
            float(health) + health_delta_for_result(result, hp_drain_rate)
        )
    )
