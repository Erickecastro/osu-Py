import unittest

from core.profiler import FrameProfiler


class FrameProfilerTests(unittest.TestCase):
    def test_metrics_are_recorded_only_when_enabled(self):
        disabled = FrameProfiler(enabled=False)
        disabled.set_metric("backend", "pygame")
        self.assertEqual(disabled.metrics, {})

        enabled = FrameProfiler(enabled=True)
        enabled.set_metric("backend", "pygame")
        self.assertEqual(enabled.metrics["backend"], "pygame")

    def test_metric_lines_wrap(self):
        pygame = __import__("pygame")
        pygame.font.init()
        profiler = FrameProfiler(enabled=True)
        profiler.metrics = {
            "backend": "pygame",
            "target": 480,
            "mode": "borderless",
            "surfaces": 20,
        }
        font = pygame.font.Font(None, 16)
        lines = profiler._metric_lines(font, 120)

        self.assertGreaterEqual(len(lines), 1)
        self.assertTrue(all(line.startswith("metrics") for line in lines))

    def test_stats_include_p50_and_p99(self):
        profiler = FrameProfiler(enabled=True)
        for value in (1.0, 2.0, 3.0, 4.0):
            profiler.add("frame", value)

        stats = profiler.stats("frame")

        self.assertEqual(stats["avg"], 2.5)
        self.assertEqual(stats["p50"], 3.0)
        self.assertEqual(stats["p95"], 4.0)
        self.assertEqual(stats["p99"], 4.0)
        self.assertEqual(stats["max"], 4.0)


if __name__ == "__main__":
    unittest.main()
