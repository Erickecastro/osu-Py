import unittest

import pygame

from scenes.gameplay_scene import GameplayScene


class GameplaySkinScalingTests(unittest.TestCase):
    def test_visible_diameter_ignores_transparent_skin_padding(self):
        scene = GameplayScene.__new__(GameplayScene)
        scene.image_surface_cache = {}
        image = pygame.Surface((100, 100), pygame.SRCALPHA)
        image.fill((0, 0, 0, 0))
        pygame.draw.rect(image, (255, 255, 255, 255), (30, 30, 40, 40))

        diameter = scene._skin_surface_diameter_for_visible_diameter(
            image,
            20,
            threshold=96,
        )

        self.assertEqual(diameter, 50)


if __name__ == "__main__":
    unittest.main()
