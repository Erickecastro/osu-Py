from bisect import bisect_right

import pygame

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


class SliderRenderer:
    def __init__(self, scene):
        self.scene = scene

    def build_points(self, note):
        all_points = note.get("curve_points", [])
        if not all_points:
            all_points = [{
                "x": note["x"],
                "y": note["y"]
            }]

        scaled_points = []
        for point in all_points:
            try:
                scaled_x, scaled_y = self.scene.scale_position(
                    point["x"],
                    point["y"]
                )
                scaled_points.append((
                    float(scaled_x),
                    float(scaled_y)
                ))
            except:
                continue

        filtered_points = []
        for point in scaled_points:
            if not filtered_points or point != filtered_points[-1]:
                filtered_points.append(point)

        if len(filtered_points) > self.scene.MAX_SLIDER_POINTS:
            filtered_points = filtered_points[::2]

        return filtered_points

    def path_metrics(self, points):
        cumulative = [0.0]
        total = 0.0
        if len(points) < 2:
            return cumulative, total

        for i in range(len(points) - 1):
            dx = points[i + 1][0] - points[i][0]
            dy = points[i + 1][1] - points[i][1]
            seg = (dx * dx + dy * dy) ** 0.5
            total += seg
            cumulative.append(total)

        return cumulative, total

    def point_at_distance(self, points, distance, cumulative=None, total=None):
        if not points:
            return (0, 0)
        if len(points) == 1:
            return points[0]

        if cumulative is None or total is None:
            cumulative, total = self.path_metrics(points)

        if total <= 0:
            return points[-1]

        d = max(0.0, min(total, float(distance)))
        idx = bisect_right(cumulative, d) - 1
        idx = max(0, min(idx, len(points) - 2))

        seg_start = cumulative[idx]
        seg_end = cumulative[idx + 1]
        seg_len = max(1e-9, seg_end - seg_start)
        t = max(0.0, min(1.0, (d - seg_start) / seg_len))

        x = points[idx][0] + (points[idx + 1][0] - points[idx][0]) * t
        y = points[idx][1] + (points[idx + 1][1] - points[idx][1]) * t

        return (int(round(x)), int(round(y)))

    def precache_surfaces(self):
        for note in self.scene.notes:
            if note["type"] != "slider":
                continue
            self.cache_full_surface(note)

    def cache_full_surface(self, note, slider_points=None):
        cache_key = note.get("render_index")
        if cache_key is None:
            return

        if cache_key in self.scene.slider_surface_cache:
            return

        if slider_points is None:
            slider_points = note.get("scaled_slider_points")

        if slider_points is None:
            slider_points = self.build_points(note)
            note["scaled_slider_points"] = slider_points

        cumulative, total = self.path_metrics(slider_points)
        note["scaled_slider_cumulative"] = cumulative
        note["scaled_slider_length"] = total

        geometry = self._surface_geometry(slider_points)
        if geometry is None:
            return

        size, local_points, surface_pos = geometry
        outline_radius = self.scene.slider_path_radius
        body_radius = int(self.scene.slider_path_radius * 0.76)
        slider_surface = self._render_track_surface(
            size,
            local_points,
            outline_radius,
            body_radius
        )
        self.scene.slider_surface_cache[cache_key] = (
            slider_surface,
            surface_pos
        )

    def draw(
        self,
        screen,
        slider_points,
        alpha=255,
        object_color=(0, 150, 255),
        draw_head_marker=True,
        draw_tail_marker=False,
        cache_key=None,
        repeat_count=1,
        draw_reverse_markers=False
    ):
        if len(slider_points) < 2 or alpha <= 0:
            return

        a = max(0, min(255, int(alpha)))

        cached = None
        if cache_key is not None:
            cached = self.scene.slider_surface_cache.get(cache_key)

        if cached is not None:
            slider_surface, surface_pos = cached
            slider_surface.set_alpha(a)
            screen.blit(slider_surface, surface_pos)
            self._draw_markers(
                screen,
                slider_points,
                a,
                draw_head_marker,
                draw_tail_marker,
                draw_reverse_markers,
                repeat_count,
                object_color
            )
            return

        geometry = self._surface_geometry(slider_points)
        if geometry is None:
            return

        size, local_points, surface_pos = geometry
        outline_radius = self.scene.slider_path_radius
        body_radius = int(self.scene.slider_path_radius * 0.76)
        slider_surface = self._render_track_surface(
            size,
            local_points,
            outline_radius,
            body_radius
        )

        if cache_key is not None:
            self.scene.slider_surface_cache[cache_key] = (
                slider_surface,
                surface_pos
            )

        slider_surface.set_alpha(a)
        screen.blit(slider_surface, surface_pos)
        self._draw_markers(
            screen,
            slider_points,
            a,
            draw_head_marker,
            draw_tail_marker,
            draw_reverse_markers,
            repeat_count,
            object_color
        )

    def _draw_markers(
        self,
        screen,
        slider_points,
        alpha,
        draw_head_marker,
        draw_tail_marker,
        draw_reverse_markers,
        repeat_count,
        object_color
    ):
        if draw_head_marker:
            self.scene._draw_aa_circle(
                screen,
                slider_points[0],
                self.scene.slider_head_radius,
                fill_color=object_color,
                outline_color=(255, 255, 255),
                outline_width=3,
                alpha=alpha
            )

        if draw_tail_marker:
            self.scene._draw_aa_circle(
                screen,
                slider_points[-1],
                self.scene.scaled_radius,
                fill_color=object_color,
                outline_color=(255, 255, 255),
                outline_width=3,
                alpha=alpha
            )

        if draw_reverse_markers and repeat_count > 1:
            self.draw_reverse_markers(
                screen,
                slider_points,
                repeat_count,
                alpha=alpha
            )

    def draw_reverse_markers(
        self,
        target,
        slider_points,
        repeat_count,
        alpha=255
    ):
        if len(slider_points) < 2 or repeat_count <= 1:
            return

        arrow_len = max(12, int(self.scene.scaled_radius * 0.45))
        arrow_width = max(6, int(self.scene.scaled_radius * 0.25))

        for repeat_index in range(1, repeat_count):
            if repeat_index % 2 == 1:
                pos = slider_points[-1]
                reference = slider_points[-2]
            else:
                pos = slider_points[0]
                reference = slider_points[1]

            dx = reference[0] - pos[0]
            dy = reference[1] - pos[1]
            distance = (dx * dx + dy * dy) ** 0.5
            if distance < 1e-3:
                continue

            ux = dx / distance
            uy = dy / distance
            perp_x = -uy
            perp_y = ux
            base = (
                pos[0] + ux * arrow_len,
                pos[1] + uy * arrow_len
            )
            left = (
                base[0] + perp_x * arrow_width,
                base[1] + perp_y * arrow_width
            )
            right = (
                base[0] - perp_x * arrow_width,
                base[1] - perp_y * arrow_width
            )
            pygame.draw.polygon(
                target,
                (255, 255, 255, int(alpha)),
                [pos, left, right]
            )

    def _point_line_distance(self, point, start, end):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if dx == 0 and dy == 0:
            px = point[0] - start[0]
            py = point[1] - start[1]
            return (px * px + py * py) ** 0.5

        return abs(
            dy * point[0]
            - dx * point[1]
            + end[0] * start[1]
            - end[1] * start[0]
        ) / ((dx * dx + dy * dy) ** 0.5)

    def _simplify_points(self, points, tolerance=0.35):
        if len(points) <= 2:
            return points

        keep = {0, len(points) - 1}
        stack = [(0, len(points) - 1)]
        while stack:
            start_idx, end_idx = stack.pop()
            max_distance = 0.0
            max_idx = None
            for idx in range(start_idx + 1, end_idx):
                distance = self._point_line_distance(
                    points[idx],
                    points[start_idx],
                    points[end_idx]
                )
                if distance > max_distance:
                    max_distance = distance
                    max_idx = idx

            if max_idx is not None and max_distance > tolerance:
                keep.add(max_idx)
                stack.append((start_idx, max_idx))
                stack.append((max_idx, end_idx))

        return [points[idx] for idx in sorted(keep)]

    def _surface_geometry(self, slider_points):
        if len(slider_points) < 2:
            return None

        if np is not None:
            min_x = int(np.floor(min(p[0] for p in slider_points)))
            max_x = int(np.ceil(max(p[0] for p in slider_points)))
            min_y = int(np.floor(min(p[1] for p in slider_points)))
            max_y = int(np.ceil(max(p[1] for p in slider_points)))
        else:
            min_x = int(min(p[0] for p in slider_points))
            max_x = int(max(p[0] for p in slider_points))
            min_y = int(min(p[1] for p in slider_points))
            max_y = int(max(p[1] for p in slider_points))

        padding = int(self.scene.slider_path_radius * 2)
        width = int((max_x - min_x) + padding * 2)
        height = int((max_y - min_y) + padding * 2)
        if width <= 0 or height <= 0:
            return None

        width = min(width, self.scene.MAX_SLIDER_SURFACE_SIZE)
        height = min(height, self.scene.MAX_SLIDER_SURFACE_SIZE)

        local_points = []
        for point in slider_points:
            local_x = int(point[0] - min_x + padding)
            local_y = int(point[1] - min_y + padding)
            if -100 <= local_x <= width + 100 and -100 <= local_y <= height + 100:
                local_points.append((
                    point[0] - min_x + padding,
                    point[1] - min_y + padding
                ))

        if np is None:
            local_points = self._simplify_points(local_points)

        if len(local_points) < 2:
            return None

        return (
            (width, height),
            local_points,
            (min_x - padding, min_y - padding)
        )

    def _render_track_surface(self, size, points, outline_radius, body_radius):
        width, height = size
        surface = pygame.Surface(size, pygame.SRCALPHA)
        if len(points) < 2 or width <= 0 or height <= 0:
            return surface

        if np is None:
            return self._render_track_surface_supersampled(
                size,
                points,
                outline_radius,
                body_radius
            )

        distances = self._distance_field(
            width,
            height,
            points,
            outline_radius + 2
        )
        if distances is None:
            return surface

        rgb = pygame.surfarray.pixels3d(surface)
        alpha = pygame.surfarray.pixels_alpha(surface)
        outline_alpha = self._alpha_from_distance(
            distances,
            outline_radius,
            220
        )
        body_alpha = self._alpha_from_distance(
            distances,
            body_radius,
            255
        )
        body_mask = body_alpha > 0
        rgb[:, :, :] = (30, 30, 30)
        alpha[:, :] = np.where(
            body_mask.T,
            body_alpha.T,
            outline_alpha.T
        )
        rgb[body_mask.T] = (80, 80, 80)
        del rgb
        del alpha
        return surface

    def _render_track_surface_supersampled(
        self,
        size,
        points,
        outline_radius,
        body_radius
    ):
        width, height = size
        surface = pygame.Surface(size, pygame.SRCALPHA)
        if len(points) < 2 or width <= 0 or height <= 0:
            return surface

        aa_scale = 3
        high_surface = pygame.Surface(
            (width * aa_scale, height * aa_scale),
            pygame.SRCALPHA
        )
        high_points = [
            (
                int(round(point[0] * aa_scale)),
                int(round(point[1] * aa_scale))
            )
            for point in points
        ]
        tracks = (
            (outline_radius, (30, 30, 30, 220)),
            (body_radius, (80, 80, 80, 255))
        )
        for radius, color in tracks:
            high_radius = max(1, int(round(radius * aa_scale)))
            high_width = max(1, high_radius * 2)
            for i in range(len(high_points) - 1):
                pygame.draw.line(
                    high_surface,
                    color,
                    high_points[i],
                    high_points[i + 1],
                    high_width
                )
            for point in high_points:
                pygame.draw.circle(
                    high_surface,
                    color,
                    point,
                    high_radius
                )
        return pygame.transform.smoothscale(high_surface, size)

    def _distance_field(self, width, height, points, max_distance):
        if len(points) < 2:
            return None

        max_distance = float(max_distance)
        distances = np.full(
            (height, width),
            max_distance + 2.0,
            dtype=np.float32
        )
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dx = float(x2 - x1)
            dy = float(y2 - y1)
            length_sq = (dx * dx) + (dy * dy)
            if length_sq <= 1e-6:
                continue

            min_x = max(0, int(np.floor(min(x1, x2) - max_distance - 2)))
            max_x = min(width - 1, int(np.ceil(max(x1, x2) + max_distance + 2)))
            min_y = max(0, int(np.floor(min(y1, y2) - max_distance - 2)))
            max_y = min(height - 1, int(np.ceil(max(y1, y2) + max_distance + 2)))
            if min_x > max_x or min_y > max_y:
                continue

            ys, xs = np.mgrid[min_y:max_y + 1, min_x:max_x + 1]
            sample_x = xs.astype(np.float32) + 0.5
            sample_y = ys.astype(np.float32) + 0.5
            px = sample_x - float(x1)
            py = sample_y - float(y1)
            t = np.clip(
                ((px * dx) + (py * dy)) / length_sq,
                0.0,
                1.0
            )
            nearest_x = float(x1) + (t * dx)
            nearest_y = float(y1) + (t * dy)
            segment_distance = np.sqrt(
                ((sample_x - nearest_x) ** 2)
                + ((sample_y - nearest_y) ** 2)
            )
            current = distances[min_y:max_y + 1, min_x:max_x + 1]
            np.minimum(
                current,
                segment_distance,
                out=current
            )
        return distances

    def _alpha_from_distance(self, distances, radius, alpha):
        coverage = np.clip(
            float(radius) + 0.5 - distances,
            0.0,
            1.0
        )
        return (coverage * float(alpha)).astype(np.uint8)
