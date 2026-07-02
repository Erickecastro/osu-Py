import unittest

import pygame

from rendering.sprite_atlas import SpriteAtlasRegistry


class SpriteAtlasTests(unittest.TestCase):
    def test_reuses_existing_entry_for_same_key(self):
        atlas = SpriteAtlasRegistry(page_size=32)
        surface = pygame.Surface((8, 8), pygame.SRCALPHA)

        first = atlas.add(surface, key="cursor")
        second = atlas.add(surface, key="cursor")

        self.assertIs(first, second)
        self.assertEqual(atlas.page_count, 1)
        self.assertEqual(atlas.sprite_count, 1)

    def test_packs_multiple_surfaces_on_page(self):
        atlas = SpriteAtlasRegistry(page_size=32, padding=1)
        first = pygame.Surface((8, 8), pygame.SRCALPHA)
        second = pygame.Surface((8, 8), pygame.SRCALPHA)

        first_ref = atlas.add(first, key="a")
        second_ref = atlas.add(second, key="b")

        self.assertEqual(atlas.page_count, 1)
        self.assertEqual(atlas.sprite_count, 2)
        self.assertNotEqual(first_ref.rect.topleft, second_ref.rect.topleft)

    def test_large_surface_allocates_large_enough_page(self):
        atlas = SpriteAtlasRegistry(page_size=32, padding=1)
        surface = pygame.Surface((48, 10), pygame.SRCALPHA)

        ref = atlas.add(surface, key="wide")

        self.assertIsNotNone(ref)
        self.assertGreaterEqual(atlas.pages[ref.page_index].size, 50)


if __name__ == "__main__":
    unittest.main()
