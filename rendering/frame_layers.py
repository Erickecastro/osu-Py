import pygame


class FrameLayer:
    __slots__ = ("name", "surface", "size")

    def __init__(self, name):
        self.name = name
        self.surface = None
        self.size = None

    def ensure(self, size):
        if self.surface is not None and self.size == size:
            return self.surface

        try:
            self.surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
        except pygame.error:
            self.surface = pygame.Surface(size, pygame.SRCALPHA)
        self.size = size
        return self.surface

    def clear(self, rect=None):
        if self.surface is None:
            return
        if rect is None:
            self.surface.fill((0, 0, 0, 0))
        else:
            self.surface.fill((0, 0, 0, 0), rect)


class FrameLayerStack:
    """CPU layer stack shaped like the future GPU/FBO render pipeline."""

    def __init__(self, names):
        self.layers = {name: FrameLayer(name) for name in names}
        self.size = None

    def ensure(self, size):
        if self.size != size:
            self.size = size
        for layer in self.layers.values():
            layer.ensure(size)

    def surface(self, name):
        return self.layers[name].surface

    def clear_all(self):
        for layer in self.layers.values():
            layer.clear()

    def clear_named(self, name, rect=None):
        self.layers[name].clear(rect)

    def clear_names(self, names, rect=None):
        for name in names:
            self.clear_named(name, rect=rect)

    def composite(self, target, names, rect=None, batch=None, atlas_key_prefix=None):
        drawn = 0
        for name in names:
            surface = self.surface(name)
            if surface is None:
                continue
            atlas_key = None
            if atlas_key_prefix is not None:
                atlas_key = (atlas_key_prefix, name, surface.get_size())
            if batch is not None:
                if rect is None:
                    batch.add_surface(surface, (0, 0), atlas_key=atlas_key)
                else:
                    batch.add_surface(
                        surface,
                        (rect.left, rect.top),
                        area=rect,
                        atlas_key=atlas_key
                    )
                drawn += 1
            elif rect is None:
                target.blit(surface, (0, 0))
                drawn += 1
            else:
                target.blit(surface, rect, rect)
                drawn += 1
        return drawn
