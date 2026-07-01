import os
import unittest

import pygame

from rendering.render_backend import (
    PygameRenderBackend,
    RenderCommandBatch,
    create_render_backend,
)


class RenderBackendTests(unittest.TestCase):
    def test_render_command_batch_flushes_surface_commands(self):
        target = pygame.Surface((8, 8), pygame.SRCALPHA)
        target.fill((0, 0, 0, 0))

        source = pygame.Surface((4, 4), pygame.SRCALPHA)
        source.fill((255, 0, 0, 255))

        source_alpha = source.get_alpha()
        batch = RenderCommandBatch()
        batch.add_surface(source, (2, 2), alpha=128)
        batch.flush(target)

        self.assertNotEqual(target.get_at((3, 3)), (0, 0, 0, 0))
        self.assertEqual(source.get_alpha(), source_alpha)
        self.assertEqual(len(batch), 0)

    def test_disable_modern_gl_env_uses_pygame_backend(self):
        previous = os.environ.get("PYOSU_DISABLE_MODERNGL")
        os.environ["PYOSU_DISABLE_MODERNGL"] = "1"
        try:
            backend = create_render_backend(pygame.Surface((4, 4)))
        finally:
            if previous is None:
                os.environ.pop("PYOSU_DISABLE_MODERNGL", None)
            else:
                os.environ["PYOSU_DISABLE_MODERNGL"] = previous

        self.assertIsInstance(backend, PygameRenderBackend)


if __name__ == "__main__":
    unittest.main()
