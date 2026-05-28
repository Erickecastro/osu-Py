import pygame


def aa_circle_surface(
    cache,
    radius,
    fill_color=None,
    outline_color=None,
    outline_width=0
):
    radius = max(1, int(round(radius)))
    outline_width = max(0, int(round(outline_width)))

    fill_key = None
    if fill_color is not None:
        fill_key = tuple(fill_color[:3])

    outline_key = None
    if outline_color is not None and outline_width > 0:
        outline_key = tuple(outline_color[:3])

    key = (radius, fill_key, outline_key, outline_width)
    cached = cache.get(key)
    if cached is not None:
        return cached

    aa_scale = 3
    padding = max(4, outline_width + 2)
    size = (radius + padding) * 2
    high_size = size * aa_scale
    high_radius = radius * aa_scale
    high_padding = padding * aa_scale
    high_center = (
        high_radius + high_padding,
        high_radius + high_padding
    )

    high_surface = pygame.Surface(
        (high_size, high_size),
        pygame.SRCALPHA
    )

    if fill_key is not None:
        pygame.draw.circle(
            high_surface,
            (*fill_key, 255),
            high_center,
            high_radius
        )

    if outline_key is not None:
        pygame.draw.circle(
            high_surface,
            (*outline_key, 255),
            high_center,
            high_radius,
            max(1, outline_width * aa_scale)
        )

    surface = pygame.transform.smoothscale(
        high_surface,
        (size, size)
    )
    cache[key] = surface

    return surface


def blit_centered(target, surface, center, alpha=255):
    alpha = max(0, min(255, int(alpha)))
    if alpha <= 0:
        return

    surface.set_alpha(alpha)
    rect = surface.get_rect(
        center=(
            int(round(center[0])),
            int(round(center[1]))
        )
    )
    target.blit(surface, rect)


def draw_aa_circle(
    target,
    cache,
    center,
    radius,
    fill_color=None,
    outline_color=None,
    outline_width=0,
    alpha=255
):
    surface = aa_circle_surface(
        cache,
        radius,
        fill_color=fill_color,
        outline_color=outline_color,
        outline_width=outline_width
    )
    blit_centered(target, surface, center, alpha)


def draw_centered_text(target, surface, center, alpha=255):
    blit_centered(
        target,
        surface,
        center,
        alpha=alpha
    )
