import unittest

from core.scoring import ScoreLedger, rank_grade


class ScoringTests(unittest.TestCase):
    def test_hidden_slider_ticks_affect_accuracy_without_visible_counts(self):
        ledger = ScoreLedger()
        ledger.add_judgement(300, visible=True, statistic="hitcircle")
        ledger.advance_combo()
        ledger.add_combo_score(300)

        ledger.add_judgement(0, visible=False, statistic="slider_tick_miss")

        self.assertEqual(ledger.hit_counts[300], 1)
        self.assertEqual(ledger.hit_counts[0], 0)
        self.assertLess(ledger.accuracy(), 100.0)
        self.assertEqual(ledger.statistics["slider_tick_miss"], 1)

    def test_bonus_score_does_not_change_accuracy(self):
        ledger = ScoreLedger()
        ledger.add_judgement(300, visible=True)
        before_accuracy = ledger.accuracy()

        ledger.add_raw_score(1000)

        self.assertEqual(ledger.score, 1000)
        self.assertEqual(ledger.accuracy(), before_accuracy)

    def test_rank_uses_hidden_misses(self):
        self.assertEqual(rank_grade(100.0, 0), "SS")
        self.assertEqual(rank_grade(100.0, 1), "A")

        ledger = ScoreLedger()
        ledger.add_judgement(300, visible=True)
        ledger.add_judgement(0, visible=False)
        self.assertEqual(ledger.rank(), "D")


if __name__ == "__main__":
    unittest.main()
