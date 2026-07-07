import os
import unittest

import pygame

from rendering.render_backend import (
    GPUTextureCache,
    ModernGLRenderBackend,
    PygameRenderBackend,
    RenderBackend,
    RenderCommandBatch,
    create_render_backend,
    _gpu_sprites_enabled_by_default,
)
from rendering.sprite_atlas import SpriteAtlasRegistry
from scenes.gameplay_scene import GameplayScene


class FakeTexture:
    def __init__(self, size, components, data):
        self.size = size
        self.components = components
        self.data = data
        self.filter = None
        self.released = False

    def release(self):
        self.released = True


class FakeContext:
    def __init__(self):
        self.textures = []

    def texture(self, size, components, data):
        texture = FakeTexture(size, components, data)
        self.textures.append(texture)
        return texture


class FakeModernGL:
    LINEAR = 1
    BLEND = 2
    SRC_ALPHA = 3
    ONE_MINUS_SRC_ALPHA = 4


class FakeBlendContext:
    def __init__(self):
        self.enabled = []
        self.blend_func = None

    def enable(self, flag):
        self.enabled.append(flag)


class FakeSpriteRenderer:
    def __init__(self, texture_cache=None):
        self.reset_count = 0
        self.texture_cache = texture_cache

    def reset_frame_metrics(self):
        self.reset_count += 1

    def flush_batch(self, backend, batch):
        drawn = len(batch)
        backend.last_gpu_sprite_count = drawn
        backend.last_gpu_flush_count = 1 if drawn else 0
        backend.last_gpu_texture_upload_count = 2 if drawn else 0
        batch.clear()
        return drawn


class FakeFailingSpriteRenderer:
    def reset_frame_metrics(self):
        return None

    def flush_batch(self, backend, batch):
        return None


class RenderBackendTests(unittest.TestCase):
    def test_render_command_batch_flushes_surface_commands(self):
        target = pygame.Surface((8, 8), pygame.SRCALPHA)
        target.fill((0, 0, 0, 0))

        source = pygame.Surface((4, 4), pygame.SRCALPHA)
        source.fill((255, 0, 0, 255))

        source_alpha = source.get_alpha()
        batch = RenderCommandBatch()
        batch.add_surface(source, (2, 2), alpha=128)
        flushed = batch.flush(target)

        self.assertEqual(flushed, 1)
        self.assertNotEqual(target.get_at((3, 3)), (0, 0, 0, 0))
        self.assertEqual(source.get_alpha(), source_alpha)
        self.assertEqual(len(batch), 0)


    def test_batch_skips_fully_transparent_commands(self):
        target = pygame.Surface((8, 8), pygame.SRCALPHA)
        source = pygame.Surface((4, 4), pygame.SRCALPHA)
        source.fill((255, 0, 0, 255))

        batch = RenderCommandBatch()
        batch.add_surface(source, (2, 2), alpha=0)

        self.assertEqual(len(batch), 0)
        self.assertEqual(batch.flush(target), 0)

    def test_backend_reuses_render_batch_between_frames(self):
        backend = PygameRenderBackend(pygame.Surface((8, 8), pygame.SRCALPHA))
        first = backend.create_batch()
        source = pygame.Surface((2, 2), pygame.SRCALPHA)
        first.add_surface(source, (0, 0))

        second = backend.create_batch()

        self.assertIs(first, second)
        self.assertEqual(len(second), 0)


    def test_backend_target_swap_clears_pending_batch(self):
        first_target = pygame.Surface((8, 8), pygame.SRCALPHA)
        second_target = pygame.Surface((8, 8), pygame.SRCALPHA)
        backend = PygameRenderBackend(first_target)
        source = pygame.Surface((2, 2), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(source, (0, 0))
        backend.set_target_surface(second_target)

        self.assertEqual(len(batch), 0)
        self.assertIs(backend.target_surface, second_target)
        self.assertEqual(backend.last_flush_count, 0)


    def test_backend_tracks_unique_surfaces_in_last_flush(self):
        backend = PygameRenderBackend(pygame.Surface((8, 8), pygame.SRCALPHA))
        first = pygame.Surface((2, 2), pygame.SRCALPHA)
        second = pygame.Surface((2, 2), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(first, (0, 0))
        batch.add_surface(first, (1, 1))
        batch.add_surface(second, (2, 2))
        backend.flush_batch(batch)

        self.assertEqual(backend.last_flush_count, 3)
        self.assertEqual(backend.last_unique_surface_count, 2)
        self.assertEqual(backend.registered_surface_count, 2)

    def test_batch_can_register_atlas_sprites(self):
        backend = PygameRenderBackend(pygame.Surface((16, 16), pygame.SRCALPHA))
        source = pygame.Surface((4, 4), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(source, (0, 0), atlas_key=("hud", "marker"))
        backend.flush_batch(batch)

        self.assertEqual(backend.last_flush_count, 1)
        self.assertEqual(backend.last_atlas_pages, 1)
        self.assertEqual(backend.last_atlas_sprites, 1)
        self.assertEqual(backend.last_atlas_command_count, 1)
        self.assertEqual(backend.last_atlas_group_count, 1)
        self.assertEqual(backend.last_atlas_run_count, 1)
        self.assertEqual(backend.last_batchable_command_count, 1)

    def test_batch_tracks_atlas_groups_without_changing_draw_order(self):
        backend = PygameRenderBackend(pygame.Surface((16, 16), pygame.SRCALPHA))
        first = pygame.Surface((2, 2), pygame.SRCALPHA)
        second = pygame.Surface((2, 2), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(first, (0, 0), atlas_key=("hud", "a"))
        batch.add_surface(first, (1, 1), atlas_key=("hud", "a"))
        batch.add_surface(second, (2, 2), atlas_key=("hud", "b"))
        backend.flush_batch(batch)

        self.assertEqual(backend.last_flush_count, 3)
        self.assertEqual(backend.last_atlas_command_count, 3)
        self.assertEqual(backend.last_atlas_group_count, 2)

    def test_batch_reports_atlas_runs_and_batchable_commands(self):
        backend = PygameRenderBackend(pygame.Surface((16, 16), pygame.SRCALPHA))
        first = pygame.Surface((2, 2), pygame.SRCALPHA)
        second = pygame.Surface((2, 2), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(first, (0, 0), atlas_key=("hud", "a"))
        batch.add_surface(first, (1, 1), atlas_key=("hud", "a"))
        batch.add_surface(second, (2, 2), atlas_key=("hud", "b"), alpha=128)
        batch.add_surface(first, (3, 3), atlas_key=("hud", "a"))
        backend.flush_batch(batch)

        self.assertEqual(backend.last_atlas_command_count, 4)
        self.assertEqual(backend.last_atlas_group_count, 2)
        self.assertEqual(backend.last_atlas_run_count, 3)
        self.assertEqual(backend.last_batchable_command_count, 3)

    def test_sprite_atlas_page_versions_increment_when_sprites_are_added(self):
        atlas = SpriteAtlasRegistry(page_size=16, padding=1)
        first = pygame.Surface((2, 2), pygame.SRCALPHA)
        second = pygame.Surface((2, 2), pygame.SRCALPHA)

        first_ref = atlas.add(first, key=("sprite", "a"))
        first_version = atlas.pages[first_ref.page_index].version
        second_ref = atlas.add(second, key=("sprite", "b"))
        second_version = atlas.pages[second_ref.page_index].version

        self.assertEqual(first_ref.page_index, second_ref.page_index)
        self.assertGreater(second_version, first_version)

    def test_gpu_texture_cache_reuses_texture_until_version_changes(self):
        ctx = FakeContext()
        cache = GPUTextureCache(ctx, moderngl_module=FakeModernGL())
        surface = pygame.Surface((4, 4), pygame.SRCALPHA)

        first = cache.get_surface_texture(
            surface,
            key=("atlas", 0),
            version=1,
        )
        second = cache.get_surface_texture(
            surface,
            key=("atlas", 0),
            version=1,
        )
        third = cache.get_surface_texture(
            surface,
            key=("atlas", 0),
            version=2,
        )

        self.assertIs(first, second)
        self.assertIsNot(second, third)
        self.assertTrue(first.released)
        self.assertEqual(cache.last_upload_count, 2)
        self.assertEqual(len(ctx.textures), 2)

    def test_gpu_sprite_path_is_enabled_by_default_with_disable_override(self):
        previous_disable = os.environ.get("PYOSU_DISABLE_GPU_SPRITES")
        previous_enable = os.environ.get("PYOSU_ENABLE_GPU_SPRITES")
        previous_legacy = os.environ.get("PYOSU_GPU_SPRITES")
        try:
            os.environ.pop("PYOSU_DISABLE_GPU_SPRITES", None)
            os.environ.pop("PYOSU_ENABLE_GPU_SPRITES", None)
            os.environ.pop("PYOSU_GPU_SPRITES", None)
            self.assertTrue(_gpu_sprites_enabled_by_default())

            os.environ["PYOSU_DISABLE_GPU_SPRITES"] = "1"
            self.assertFalse(_gpu_sprites_enabled_by_default())
        finally:
            for name, value in (
                ("PYOSU_DISABLE_GPU_SPRITES", previous_disable),
                ("PYOSU_ENABLE_GPU_SPRITES", previous_enable),
                ("PYOSU_GPU_SPRITES", previous_legacy),
            ):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_gameplay_gpu_layers_are_opt_in_until_present_path_is_stable(self):
        previous_disable = os.environ.get("PYOSU_DISABLE_GPU_GAMEPLAY_LAYERS")
        previous_enable = os.environ.get("PYOSU_ENABLE_GPU_GAMEPLAY_LAYERS")
        try:
            os.environ.pop("PYOSU_DISABLE_GPU_GAMEPLAY_LAYERS", None)
            os.environ.pop("PYOSU_ENABLE_GPU_GAMEPLAY_LAYERS", None)
            self.assertFalse(
                GameplayScene._gpu_gameplay_layers_enabled_by_default()
            )

            os.environ["PYOSU_ENABLE_GPU_GAMEPLAY_LAYERS"] = "1"
            self.assertTrue(
                GameplayScene._gpu_gameplay_layers_enabled_by_default()
            )

            os.environ["PYOSU_DISABLE_GPU_GAMEPLAY_LAYERS"] = "1"
            self.assertFalse(
                GameplayScene._gpu_gameplay_layers_enabled_by_default()
            )

            os.environ.pop("PYOSU_DISABLE_GPU_GAMEPLAY_LAYERS", None)
            os.environ["PYOSU_ENABLE_GPU_GAMEPLAY_LAYERS"] = "0"
            self.assertFalse(
                GameplayScene._gpu_gameplay_layers_enabled_by_default()
            )
        finally:
            for name, value in (
                ("PYOSU_DISABLE_GPU_GAMEPLAY_LAYERS", previous_disable),
                ("PYOSU_ENABLE_GPU_GAMEPLAY_LAYERS", previous_enable),
            ):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_present_layer_queue_accumulates_gpu_metrics_after_frame(self):
        backend = ModernGLRenderBackend.__new__(ModernGLRenderBackend)
        RenderBackend.__init__(
            backend,
            pygame.Surface((32, 32), pygame.SRCALPHA)
        )
        backend.present_frame_surface = True
        backend._enabled = True
        backend._ctx = FakeBlendContext()
        backend._moderngl = FakeModernGL()
        backend._present_layer_batch = RenderCommandBatch()
        backend._present_layer_renderer = FakeSpriteRenderer()
        backend.last_gpu_sprite_count = 1
        backend.last_gpu_flush_count = 1
        backend.last_gpu_texture_upload_count = 1
        source = pygame.Surface((2, 2), pygame.SRCALPHA)

        queued = backend.queue_present_layer_surface(
            source,
            (3, 4),
            atlas_key=("gameplay_layer", "slider_paths")
        )
        backend._flush_present_layer_batch()

        self.assertTrue(queued)
        self.assertEqual(backend.last_present_layer_count, 1)
        self.assertEqual(backend.last_gpu_sprite_count, 2)
        self.assertEqual(backend.last_gpu_flush_count, 2)
        self.assertEqual(backend.last_gpu_texture_upload_count, 3)
        self.assertEqual(len(backend._present_layer_batch), 0)

    def test_present_layer_batch_moves_commands_atomically(self):
        backend = ModernGLRenderBackend.__new__(ModernGLRenderBackend)
        RenderBackend.__init__(
            backend,
            pygame.Surface((32, 32), pygame.SRCALPHA)
        )
        backend.present_frame_surface = True
        backend._enabled = True
        backend._ctx = FakeBlendContext()
        backend._present_layer_renderer = FakeSpriteRenderer()
        backend._present_layer_batch = RenderCommandBatch()
        source = pygame.Surface((2, 2), pygame.SRCALPHA)
        batch = RenderCommandBatch()
        batch.add_surface(
            source,
            (1, 2),
            atlas_key=("gameplay_layer", "slider_paths")
        )
        batch.add_surface(
            source,
            (3, 4),
            atlas_key=("gameplay_layer", "hitobjects")
        )

        queued = backend.queue_present_layer_batch(batch)

        self.assertTrue(queued)
        self.assertEqual(len(batch), 0)
        self.assertEqual(len(backend._present_layer_batch), 2)

    def test_present_layer_gpu_failure_falls_back_to_cpu_surface(self):
        target = pygame.Surface((8, 8), pygame.SRCALPHA)
        target.fill((0, 0, 0, 0))
        backend = ModernGLRenderBackend.__new__(ModernGLRenderBackend)
        RenderBackend.__init__(backend, target)
        backend.present_frame_surface = True
        backend._enabled = True
        backend._ctx = FakeBlendContext()
        backend._moderngl = FakeModernGL()
        backend._present_layer_renderer = FakeFailingSpriteRenderer()
        backend._present_layer_batch = RenderCommandBatch()
        source = pygame.Surface((2, 2), pygame.SRCALPHA)
        source.fill((255, 0, 0, 255))
        backend.queue_present_layer_surface(source, (3, 3))

        result = backend._flush_present_layer_batch()

        self.assertFalse(result)
        self.assertEqual(target.get_at((3, 3)), (255, 0, 0, 255))
        self.assertEqual(backend.last_gpu_fallback_count, 1)
        self.assertEqual(len(backend._present_layer_batch), 0)

    def test_prepare_gpu_surface_reuses_preuploaded_texture(self):
        ctx = FakeContext()
        backend = ModernGLRenderBackend.__new__(ModernGLRenderBackend)
        RenderBackend.__init__(
            backend,
            pygame.Surface((32, 32), pygame.SRCALPHA)
        )
        backend.present_frame_surface = True
        backend._enabled = True
        backend._ctx = ctx
        backend._sprite_renderer = None
        backend._present_layer_renderer = FakeSpriteRenderer(
            GPUTextureCache(ctx, moderngl_module=FakeModernGL())
        )
        source = pygame.Surface((4, 4), pygame.SRCALPHA)

        first = backend.prepare_gpu_surface(source, key=("slider", "path", 1))
        second = backend.prepare_gpu_surface(source, key=("slider", "path", 1))

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(len(ctx.textures), 1)

    def test_gpu_surface_prepare_queue_respects_warm_budget(self):
        ctx = FakeContext()
        backend = ModernGLRenderBackend.__new__(ModernGLRenderBackend)
        RenderBackend.__init__(
            backend,
            pygame.Surface((32, 32), pygame.SRCALPHA)
        )
        backend.present_frame_surface = True
        backend._enabled = True
        backend._ctx = ctx
        backend._sprite_renderer = None
        backend._gpu_prepare_queue = []
        backend._gpu_prepare_keys = set()
        backend._present_layer_renderer = FakeSpriteRenderer(
            GPUTextureCache(ctx, moderngl_module=FakeModernGL())
        )
        first = pygame.Surface((4, 4), pygame.SRCALPHA)
        second = pygame.Surface((5, 5), pygame.SRCALPHA)

        self.assertTrue(
            backend.queue_gpu_surface_prepare(first, key=("slider", 1))
        )
        self.assertTrue(
            backend.queue_gpu_surface_prepare(second, key=("slider", 2))
        )

        warmed = backend.warm_gpu_surface_cache(max_items=1)

        self.assertEqual(warmed, 1)
        self.assertEqual(backend.last_gpu_prepare_count, 1)
        self.assertEqual(backend.last_gpu_prepare_pending, 1)
        self.assertEqual(len(ctx.textures), 1)

    def test_batch_culls_fully_offscreen_surfaces(self):
        backend = PygameRenderBackend(pygame.Surface((8, 8), pygame.SRCALPHA))
        source = pygame.Surface((2, 2), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(source, (100, 100))
        batch.add_surface(source, (1, 1))
        backend.flush_batch(batch)

        self.assertEqual(backend.last_flush_count, 1)
        self.assertEqual(backend.last_culled_count, 1)
        self.assertEqual(backend.last_unique_surface_count, 1)



    def test_rect_destination_uses_source_size_for_culling(self):
        backend = PygameRenderBackend(pygame.Surface((8, 8), pygame.SRCALPHA))
        source = pygame.Surface((2, 2), pygame.SRCALPHA)

        batch = backend.create_batch()
        batch.add_surface(source, pygame.Rect(7, 7, 100, 100))
        backend.flush_batch(batch)

        self.assertEqual(backend.last_flush_count, 1)
        self.assertEqual(backend.last_culled_count, 0)

    def test_direct_blit_culling_is_reported(self):
        backend = PygameRenderBackend(pygame.Surface((8, 8), pygame.SRCALPHA))
        source = pygame.Surface((2, 2), pygame.SRCALPHA)

        backend.blit_surface(source, (20, 20))

        self.assertEqual(backend.last_direct_culled_count, 1)
        self.assertEqual(backend.last_culled_count, 1)

        backend.begin_frame()

        self.assertEqual(backend.last_direct_culled_count, 0)
        self.assertEqual(backend.last_culled_count, 0)

    def test_direct_blit_can_register_atlas_sprite(self):
        backend = PygameRenderBackend(pygame.Surface((8, 8), pygame.SRCALPHA))
        source = pygame.Surface((2, 2), pygame.SRCALPHA)

        backend.blit_surface(source, (1, 1), atlas_key=("cursor", "main"))

        self.assertEqual(backend.last_atlas_pages, 1)
        self.assertEqual(backend.last_atlas_sprites, 1)
        self.assertEqual(backend.last_atlas_command_count, 1)
        self.assertEqual(backend.last_atlas_group_count, 1)

    def test_gameplay_slider_surface_registration_uses_stable_atlas_key(self):
        scene = GameplayScene.__new__(GameplayScene)
        scene.render_backend = PygameRenderBackend(
            pygame.Surface((32, 32), pygame.SRCALPHA)
        )
        slider_surface = pygame.Surface((8, 6), pygame.SRCALPHA)

        scene._register_slider_surface_atlas(("slider", 4), slider_surface)

        self.assertEqual(scene.render_backend.last_atlas_pages, 1)
        self.assertEqual(scene.render_backend.last_atlas_sprites, 1)
        key = ("slider", "path", ("slider", 4), 8, 6)
        self.assertIn(key, scene.render_backend.sprite_atlas.entries)

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
