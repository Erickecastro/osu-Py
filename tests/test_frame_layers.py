import unittest

import pygame

from rendering.frame_layers import FrameLayerStack


class DummyBatch:
    def __init__(self):
        self.commands = []

    def add_surface(self, surface, dest, area=None, alpha=None, atlas_key=None):
        self.commands.append((surface, dest, area, alpha, atlas_key))


class FrameLayerStackTests(unittest.TestCase):
    def test_layers_reuse_surfaces_until_size_changes(self):
        stack = FrameLayerStack(("approach", "hitobjects"))

        stack.ensure((16, 16))
        first = stack.surface("approach")
        stack.ensure((16, 16))
        second = stack.surface("approach")
        stack.ensure((32, 16))
        third = stack.surface("approach")

        self.assertIs(first, second)
        self.assertIsNot(second, third)
        self.assertEqual(third.get_size(), (32, 16))

    def test_clear_named_rect_preserves_pixels_outside_rect(self):
        stack = FrameLayerStack(("hitobjects",))
        stack.ensure((8, 8))
        surface = stack.surface("hitobjects")
        surface.fill((255, 255, 255, 255))

        stack.clear_named("hitobjects", pygame.Rect(0, 0, 4, 4))

        self.assertEqual(surface.get_at((1, 1)), (0, 0, 0, 0))
        self.assertEqual(surface.get_at((6, 6)), (255, 255, 255, 255))

    def test_composite_respects_layer_order(self):
        stack = FrameLayerStack(("bottom", "top"))
        stack.ensure((4, 4))
        stack.surface("bottom").fill((255, 0, 0, 255))
        stack.surface("top").fill((0, 0, 255, 255), pygame.Rect(1, 1, 2, 2))
        target = pygame.Surface((4, 4), pygame.SRCALPHA)

        count = stack.composite(target, ("bottom", "top"))

        self.assertEqual(count, 2)
        self.assertEqual(target.get_at((0, 0)), (255, 0, 0, 255))
        self.assertEqual(target.get_at((1, 1)), (0, 0, 255, 255))

    def test_composite_can_queue_layers_into_render_batch(self):
        stack = FrameLayerStack(("slider_paths", "hitobjects"))
        stack.ensure((16, 16))
        batch = DummyBatch()
        rect = pygame.Rect(2, 3, 8, 9)

        count = stack.composite(
            None,
            ("slider_paths", "hitobjects"),
            rect=rect,
            batch=batch,
            atlas_key_prefix="gameplay_layer"
        )

        self.assertEqual(count, 2)
        self.assertEqual(len(batch.commands), 2)
        self.assertEqual(batch.commands[0][1], (2, 3))
        self.assertEqual(batch.commands[0][2], rect)
        self.assertEqual(
            batch.commands[0][4],
            ("gameplay_layer", "slider_paths", (16, 16))
        )


if __name__ == "__main__":
    unittest.main()
