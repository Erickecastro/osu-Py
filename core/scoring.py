from dataclasses import dataclass, field


HIT_RESULTS = (300, 100, 50, 0)


def clamp_hit_result(result):
    if result is None:
        return 0
    return max(0, min(300, int(result)))


def calculate_accuracy_from_points(points, max_points):
    if max_points <= 0:
        return 100.0
    return (float(points) / float(max_points)) * 100.0


def rank_grade(accuracy, misses=0):
    if misses == 0 and accuracy >= 100.0:
        return "SS"
    if misses == 0 and accuracy >= 95.0:
        return "S"
    if accuracy >= 90.0:
        return "A"
    if accuracy >= 80.0:
        return "B"
    if accuracy >= 70.0:
        return "C"
    return "D"


@dataclass
class ScoreLedger:
    hit_counts: dict = field(default_factory=lambda: {300: 0, 100: 0, 50: 0, 0: 0})
    accuracy_counts: dict = field(default_factory=lambda: {300: 0, 100: 0, 50: 0, 0: 0})
    score: int = 0
    combo: int = 0
    max_combo: int = 0
    accuracy_points: int = 0
    accuracy_max_points: int = 0
    judgement_events: int = 0
    miss_events: int = 0
    statistics: dict = field(default_factory=dict)

    def add_judgement(
        self,
        result,
        *,
        max_result=300,
        visible=True,
        statistic=None
    ):
        result = clamp_hit_result(result)
        max_result = max(1, int(max_result))
        self.accuracy_points += min(result, max_result)
        self.accuracy_max_points += max_result
        self.judgement_events += 1
        if result not in self.accuracy_counts:
            self.accuracy_counts[result] = 0
        self.accuracy_counts[result] += 1
        if result <= 0:
            self.miss_events += 1

        if visible:
            if result not in self.hit_counts:
                self.hit_counts[result] = 0
            self.hit_counts[result] += 1

        if statistic:
            self.statistics[statistic] = self.statistics.get(statistic, 0) + 1

    def add_raw_score(self, amount):
        self.score += max(0, int(amount))
        return self.score

    def add_combo_score(self, base_score, *, combo_weight=25, combo_bonus=True):
        base_score = max(0, int(base_score))
        if base_score <= 0:
            return self.score

        bonus = 0
        if combo_bonus and combo_weight > 0:
            bonus = max(0, self.combo - 1) * base_score // int(combo_weight)
        self.score += base_score + bonus
        return self.score

    def advance_combo(self, amount=1):
        self.combo += max(0, int(amount))
        self.max_combo = max(self.max_combo, self.combo)
        return self.combo

    def break_combo(self):
        self.combo = 0

    def accuracy(self):
        if self.accuracy_max_points > 0:
            return calculate_accuracy_from_points(
                self.accuracy_points,
                self.accuracy_max_points
            )

        total_hits = sum(self.hit_counts.values())
        if total_hits <= 0:
            return 100.0
        weighted = (
            (self.hit_counts.get(300, 0) * 300)
            + (self.hit_counts.get(100, 0) * 100)
            + (self.hit_counts.get(50, 0) * 50)
        )
        return (weighted / (total_hits * 300)) * 100.0

    def rank(self):
        total = sum(self.accuracy_counts.values())
        if total <= 0:
            return "SS"

        great_ratio = self.accuracy_counts.get(300, 0) / total
        meh_ratio = self.accuracy_counts.get(50, 0) / total
        if self.miss_events == 0 and self.accuracy() >= 100.0:
            return "SS"
        if self.miss_events == 0 and great_ratio > 0.90 and meh_ratio <= 0.01:
            return "S"
        if (self.miss_events == 0 and great_ratio > 0.80) or great_ratio > 0.90:
            return "A"
        if (self.miss_events == 0 and great_ratio > 0.70) or great_ratio > 0.80:
            return "B"
        if great_ratio > 0.60:
            return "C"
        return "D"
