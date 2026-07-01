import unittest

import pygame

from core.utils import is_object_visible


class UtilsPerformanceTests(unittest.TestCase):
    def test_object_visibility_with_margin(self):
        bounds = pygame.Rect(0, 0, 100, 100)
        self.assertTrue(is_object_visible((50, 50), bounds, radius=8, padding=2))
        self.assertTrue(is_object_visible((110, 50), bounds, radius=8, padding=2))
        self.assertFalse(is_object_visible((130, 50), bounds, radius=8, padding=2))

    def test_object_visibility_accepts_tuple_bounds(self):
        bounds = (0, 0, 100, 100)
        self.assertTrue(is_object_visible((50, 50), bounds, radius=8, padding=2))
        self.assertFalse(is_object_visible((140, 50), bounds, radius=8, padding=2))


if __name__ == "__main__":
    unittest.main()
