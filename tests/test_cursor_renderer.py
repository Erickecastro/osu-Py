import unittest

import pygame

from rendering.cursor import CursorRenderer


class QueueBackend:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.queued = []
        self.blit_calls = []

    def queue_post_present_surface(
        self,
        surface,
        dest,
        area=None,
        alpha=None,
        atlas_key=None
    ):
        self.queued.append((surface, dest, area, alpha, atlas_key))
        return self.accepted

    def blit_surface(
        self,
        surface,
        dest,
        area=None,
        alpha=None,
        atlas_key=None
    ):
        self.blit_calls.append((surface, dest, area, alpha, atlas_key))


class CursorRendererTests(unittest.TestCase):
    def _renderer(self):
        renderer = CursorRenderer.__new__(CursorRenderer)
        renderer.scaled_image_cache = {}
        return renderer

    def test_post_present_path_queues_cursor_sprite(self):
        renderer = self._renderer()
        target = pygame.Surface((16, 16), pygame.SRCALPHA)
        image = pygame.Surface((4, 4), pygame.SRCALPHA)
        backend = QueueBackend(accepted=True)

        renderer._blit_centered(
            target,
            image,
            (8, 8),
            alpha=128,
            backend=backend,
            atlas_key=("cursor", "main"),
            post_present=True
        )

        self.assertEqual(len(backend.queued), 1)
        self.assertEqual(len(backend.blit_calls), 0)
        _surface, dest, _area, alpha, atlas_key = backend.queued[0]
        self.assertEqual(dest.center, (8, 8))
        self.assertEqual(alpha, 128)
        self.assertEqual(atlas_key, ("cursor", "main", 4, 4))

    def test_post_present_falls_back_to_backend_blit(self):
        renderer = self._renderer()
        target = pygame.Surface((16, 16), pygame.SRCALPHA)
        image = pygame.Surface((4, 4), pygame.SRCALPHA)
        backend = QueueBackend(accepted=False)

        renderer._blit_centered(
            target,
            image,
            (8, 8),
            alpha=200,
            backend=backend,
            atlas_key=("cursor", "trail"),
            post_present=True
        )

        self.assertEqual(len(backend.queued), 1)
        self.assertEqual(len(backend.blit_calls), 1)
        _surface, dest, _area, alpha, atlas_key = backend.blit_calls[0]
        self.assertEqual(dest.center, (8, 8))
        self.assertEqual(alpha, 200)
        self.assertEqual(atlas_key, ("cursor", "trail", 4, 4))


if __name__ == "__main__":
    unittest.main()
