from core.beatmap_loader import BeatmapLoader


BEATMAP = (
    "songs/158023 UNDEAD CORPORATION - Everything will freeze/"
    "UNDEAD CORPORATION - Everything will freeze (Ekoro) [Normal].osu"
)


def max_gap(points):
    if len(points) < 2:
        return 0
    return max(
        ((points[i + 1]["x"] - points[i]["x"]) ** 2 + (points[i + 1]["y"] - points[i]["y"]) ** 2) ** 0.5
        for i in range(len(points) - 1)
    )


def main():
    loader = BeatmapLoader()
    notes = loader.parse_hitobjects(BEATMAP)
    sliders = [note for note in notes if note["type"] == "slider"]

    if not sliders:
        raise SystemExit("No sliders found in beatmap")

    point_counts = [len(note["curve_points"]) for note in sliders]
    average_points = sum(point_counts) / len(point_counts)
    worst_gap = max(max_gap(note["curve_points"]) for note in sliders)

    print(f"sliders={len(sliders)} average_points={average_points:.2f} worst_gap={worst_gap:.2f}")

    assert average_points >= 20, f"Average points too low: {average_points:.2f}"
    assert worst_gap <= 20, f"Worst gap too large: {worst_gap:.2f}"


if __name__ == "__main__":
    main()
