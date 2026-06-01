import math
from bisect import bisect_right


class SliderPathGenerator:
    def bezier_point(self, points, t):
        if not points:
            return {"x": 0, "y": 0}
        if len(points) == 1:
            return points[0]

        current_points = []
        for point in points:
            x = float(point.get("x", 0))
            y = float(point.get("y", 0))
            if x != x or x in (float("inf"), float("-inf")):
                x = 0
            if y != y or y in (float("inf"), float("-inf")):
                y = 0
            current_points.append({"x": x, "y": y})

        t = max(0.0, min(1.0, t))
        while len(current_points) > 1:
            current_points = [
                {
                    "x": current_points[i]["x"]
                    + (current_points[i + 1]["x"] - current_points[i]["x"]) * t,
                    "y": current_points[i]["y"]
                    + (current_points[i + 1]["y"] - current_points[i]["y"]) * t
                }
                for i in range(len(current_points) - 1)
            ]

        return current_points[0] if current_points else {"x": 0, "y": 0}

    def _distance(self, p1, p2):
        return math.hypot(
            p1.get("x", 0) - p2.get("x", 0),
            p1.get("y", 0) - p2.get("y", 0)
        )

    def _adaptive_subdivide(
        self,
        points,
        t0,
        t1,
        p0,
        p1,
        tolerance,
        depth,
        max_depth
    ):
        midpoint_t = (t0 + t1) / 2.0
        midpoint = self.bezier_point(points, midpoint_t)
        chord_midpoint = {
            "x": (p0["x"] + p1["x"]) / 2.0,
            "y": (p0["y"] + p1["y"]) / 2.0
        }

        if (
            self._distance(midpoint, chord_midpoint) <= tolerance
            or depth >= max_depth
        ):
            return [p0, p1]

        left = self._adaptive_subdivide(
            points,
            t0,
            midpoint_t,
            p0,
            midpoint,
            tolerance,
            depth + 1,
            max_depth
        )
        right = self._adaptive_subdivide(
            points,
            midpoint_t,
            t1,
            midpoint,
            p1,
            tolerance,
            depth + 1,
            max_depth
        )
        return left[:-1] + right

    def _split_bezier_segments(self, points):
        if not points:
            return []

        segments = []
        current = [points[0]]
        for point in points[1:]:
            if point["x"] == current[-1]["x"] and point["y"] == current[-1]["y"]:
                if len(current) > 1:
                    segments.append(current)
                current = [point]
            else:
                current.append(point)

        if len(current) > 1:
            segments.append(current)
        return segments

    def generate_bezier_path_adaptive(
        self,
        points,
        tolerance=0.15,
        max_depth=22
    ):
        if not points:
            return []

        output = []
        previous = None
        for segment in self._split_bezier_segments(points):
            if len(segment) < 3:
                if len(segment) == 2:
                    p0 = segment[0]
                    p2 = segment[1]
                    p1 = {
                        "x": (p0["x"] + p2["x"]) / 2.0,
                        "y": (p0["y"] + p2["y"]) / 2.0
                    }
                    curve_points = [p0, p1, p2]
                    points_for_segment = self._adaptive_subdivide(
                        curve_points,
                        0.0,
                        1.0,
                        p0,
                        p2,
                        tolerance,
                        0,
                        max_depth
                    )
                else:
                    points_for_segment = segment
            else:
                p0 = self.bezier_point(segment, 0.0)
                p1 = self.bezier_point(segment, 1.0)
                points_for_segment = self._adaptive_subdivide(
                    segment,
                    0.0,
                    1.0,
                    p0,
                    p1,
                    tolerance,
                    0,
                    max_depth
                )

            for point in points_for_segment:
                if (
                    previous is None
                    or point["x"] != previous["x"]
                    or point["y"] != previous["y"]
                ):
                    output.append(point)
                    previous = point

        return output

    def generate_catmull_path(self, points, steps=30):
        if not points:
            return []

        def catmull_rom(p0, p1, p2, p3, t):
            t2 = t * t
            t3 = t2 * t
            return {
                "x": 0.5 * (
                    (2 * p1["x"])
                    + (-p0["x"] + p2["x"]) * t
                    + (2 * p0["x"] - 5 * p1["x"] + 4 * p2["x"] - p3["x"]) * t2
                    + (-p0["x"] + 3 * p1["x"] - 3 * p2["x"] + p3["x"]) * t3
                ),
                "y": 0.5 * (
                    (2 * p1["y"])
                    + (-p0["y"] + p2["y"]) * t
                    + (2 * p0["y"] - 5 * p1["y"] + 4 * p2["y"] - p3["y"]) * t2
                    + (-p0["y"] + 3 * p1["y"] - 3 * p2["y"] + p3["y"]) * t3
                )
            }

        output = []
        extended = [points[0]] + points + [points[-1]]
        for index in range(len(points) - 1):
            p0 = extended[index]
            p1 = extended[index + 1]
            p2 = extended[index + 2]
            p3 = extended[index + 3]
            for step in range(steps):
                output.append(catmull_rom(p0, p1, p2, p3, step / steps))

        output.append({"x": points[-1]["x"], "y": points[-1]["y"]})
        return self._dedupe_points(output)

    def generate_perfect_path(
        self,
        points,
        steps_per_rad=12,
        slider_distance=0.0
    ):
        if not points:
            return []
        if len(points) < 3 or len(points) != 3:
            return self.generate_bezier_path_adaptive(points)

        circle = self._circle_from_three(points[0], points[1], points[2])
        if circle is None:
            return self.generate_linear_path([points[0], points[2]], steps=32)

        cx, cy, radius = circle
        start_angle = self._normalized_angle(points[0], cx, cy)
        mid_angle = self._normalized_angle(points[1], cx, cy)
        end_angle = self._normalized_angle(points[2], cx, cy)

        ccw_start_end = self._ccw_delta(start_angle, end_angle)
        ccw_start_mid = self._ccw_delta(start_angle, mid_angle)
        span = (
            ccw_start_end
            if ccw_start_mid <= ccw_start_end
            else ccw_start_end - (2 * math.pi)
        )

        arc_length = abs(span) * radius
        samples = max(
            16,
            int(max(abs(span) * steps_per_rad, arc_length / 1.25))
        )
        samples = min(3000, samples)
        output = []
        for sample in range(samples + 1):
            t = sample / samples
            angle = start_angle + (t * span)
            output.append({
                "x": cx + math.cos(angle) * radius,
                "y": cy + math.sin(angle) * radius
            })

        return self._dedupe_points(output)

    def generate_linear_path(self, points, steps=25):
        if not points:
            return []

        output = []
        for index in range(len(points) - 1):
            start = points[index]
            end = points[index + 1]
            for step in range(steps):
                t = step / steps
                output.append({
                    "x": start["x"] + (end["x"] - start["x"]) * t,
                    "y": start["y"] + (end["y"] - start["y"]) * t
                })

        output.append({"x": points[-1]["x"], "y": points[-1]["y"]})
        return output

    def generate_slider_path(
        self,
        points,
        curve_type="L",
        slider_distance=0.0,
        start_x=0,
        start_y=0
    ):
        if len(points) < 1:
            return []

        if len(points) == 1:
            return self._single_point_slider_path(
                points[0],
                slider_distance,
                start_x,
                start_y
            )

        path_points = [{"x": float(start_x), "y": float(start_y)}] + points
        if curve_type == "B":
            smooth_points = self.generate_bezier_path_adaptive(path_points)
        elif curve_type == "C":
            smooth_points = self.generate_catmull_path(path_points, steps=35)
        elif curve_type == "P":
            smooth_points = self.generate_perfect_path(
                path_points,
                steps_per_rad=36,
                slider_distance=slider_distance
            )
        else:
            smooth_points = self.generate_linear_path(path_points, steps=32)

        smooth_points = self._densify_uniform(smooth_points, spacing=2.5)
        if slider_distance > 0 and len(smooth_points) > 1:
            smooth_points = self._fit_path_to_length(
                smooth_points,
                slider_distance
            )

        smooth_points = self._resample_slider_path(
            smooth_points,
            min_points=120,
            spacing=1.5
        )
        smooth_points = self._validate_slider_points(smooth_points)

        if len(smooth_points) > 2500:
            smooth_points = smooth_points[::2]
        return smooth_points

    def _single_point_slider_path(
        self,
        point,
        slider_distance,
        start_x,
        start_y
    ):
        if slider_distance <= 0:
            return [point]

        direction_x = point["x"] - start_x
        direction_y = point["y"] - start_y
        distance_to_point = math.hypot(direction_x, direction_y)
        if distance_to_point <= 0:
            return [point]

        direction_x /= distance_to_point
        direction_y /= distance_to_point
        steps = max(16, int(slider_distance / 2))
        return [
            {
                "x": start_x + direction_x * (slider_distance * (i / steps)),
                "y": start_y + direction_y * (slider_distance * (i / steps))
            }
            for i in range(steps + 1)
        ]

    def _circle_from_three(self, a, b, c):
        ax, ay = a["x"], a["y"]
        bx, by = b["x"], b["y"]
        cx, cy = c["x"], c["y"]
        determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(determinant) < 1e-6:
            return None

        ux = (
            (ax * ax + ay * ay) * (by - cy)
            + (bx * bx + by * by) * (cy - ay)
            + (cx * cx + cy * cy) * (ay - by)
        ) / determinant
        uy = (
            (ax * ax + ay * ay) * (cx - bx)
            + (bx * bx + by * by) * (ax - cx)
            + (cx * cx + cy * cy) * (bx - ax)
        ) / determinant
        return ux, uy, math.hypot(ax - ux, ay - uy)

    def _normalized_angle(self, point, cx, cy):
        return math.atan2(point["y"] - cy, point["x"] - cx) % (2 * math.pi)

    def _ccw_delta(self, start, end):
        delta = end - start
        if delta < 0:
            delta += 2 * math.pi
        return delta

    def _dedupe_points(self, points):
        filtered = []
        previous = None
        for point in points:
            if (
                previous is None
                or point["x"] != previous["x"]
                or point["y"] != previous["y"]
            ):
                filtered.append(point)
                previous = point
        return filtered

    def _validate_slider_points(self, points):
        return [
            {
                "x": float(point.get("x", 0)),
                "y": float(point.get("y", 0))
            }
            for point in points
        ]

    def _resample_slider_path(self, points, min_points=24, spacing=3.5):
        if len(points) < 2:
            return points

        cumulative = [0.0]
        total_length = 0.0
        for index in range(len(points) - 1):
            segment = math.hypot(
                points[index + 1]["x"] - points[index]["x"],
                points[index + 1]["y"] - points[index]["y"]
            )
            total_length += segment
            cumulative.append(total_length)

        if total_length <= 0:
            return points

        target_count = max(min_points, min(1400, int(total_length / spacing)))
        if len(points) >= target_count:
            return points

        resampled = []
        for index in range(target_count):
            target_distance = cumulative[-1] * (index / (target_count - 1))
            segment_index = bisect_right(cumulative, target_distance) - 1
            segment_index = max(0, min(segment_index, len(points) - 2))

            start = points[segment_index]
            end = points[segment_index + 1]
            segment_start = cumulative[segment_index]
            segment_end = cumulative[segment_index + 1]
            segment_length = max(segment_end - segment_start, 1e-6)
            t = max(
                0.0,
                min(1.0, (target_distance - segment_start) / segment_length)
            )
            resampled.append({
                "x": start["x"] + (end["x"] - start["x"]) * t,
                "y": start["y"] + (end["y"] - start["y"]) * t
            })

        return resampled

    def _densify_uniform(self, points, spacing=6.0):
        if len(points) < 2:
            return points

        densified = []
        for index in range(len(points) - 1):
            p1 = points[index]
            p2 = points[index + 1]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            distance = math.hypot(dx, dy)
            if distance <= 0:
                continue

            steps = max(1, int(distance / spacing))
            for step in range(steps):
                if len(densified) > 5000:
                    break
                t = step / steps
                densified.append({
                    "x": p1["x"] + dx * t,
                    "y": p1["y"] + dy * t
                })

        densified.append(points[-1])
        return densified

    def _normalize_slider_length(self, points, target_length):
        if len(points) < 2 or target_length <= 0:
            return points

        total_length = 0.0
        arc_lengths = [0.0]
        for index in range(1, len(points)):
            segment = math.hypot(
                points[index]["x"] - points[index - 1]["x"],
                points[index]["y"] - points[index - 1]["y"]
            )
            total_length += segment
            arc_lengths.append(total_length)

        if total_length <= 0:
            return points

        scale_factor = target_length / total_length
        if 0.9 <= scale_factor <= 1.1:
            return points

        resampled = [points[0]]
        num_samples = max(32, int(target_length / 2.5))
        for sample in range(1, num_samples + 1):
            target_distance = (sample / num_samples) * target_length
            original_distance = (
                target_distance / scale_factor
                if scale_factor > 0
                else 0
            )
            segment_index = bisect_right(arc_lengths, original_distance) - 1
            segment_index = max(0, min(segment_index, len(points) - 2))
            start = points[segment_index]
            end = points[segment_index + 1]
            segment_start = arc_lengths[segment_index]
            segment_end = arc_lengths[segment_index + 1]
            segment_length = segment_end - segment_start
            t = (
                (original_distance - segment_start) / segment_length
                if segment_length > 0
                else 0.0
            )
            t = max(0.0, min(1.0, t))
            resampled.append({
                "x": start["x"] + (end["x"] - start["x"]) * t,
                "y": start["y"] + (end["y"] - start["y"]) * t
            })

        final_length = 0.0
        for index in range(len(resampled) - 1):
            final_length += math.hypot(
                resampled[index + 1]["x"] - resampled[index]["x"],
                resampled[index + 1]["y"] - resampled[index]["y"]
            )

        if abs(final_length - target_length) > target_length * 0.3:
            return points
        return resampled

    def _path_length(self, points):
        total = 0.0
        for index in range(len(points) - 1):
            total += math.hypot(
                points[index + 1]["x"] - points[index]["x"],
                points[index + 1]["y"] - points[index]["y"]
            )
        return total

    def _fit_path_to_length(self, points, target_length):
        current_length = self._path_length(points)
        if current_length <= 1e-6:
            return points

        if current_length >= target_length:
            return self._trim_path_to_length(points, target_length)

        extended = list(points)
        remaining = target_length - current_length
        last = extended[-1]
        previous = extended[-2]
        dx = last["x"] - previous["x"]
        dy = last["y"] - previous["y"]
        distance = math.hypot(dx, dy)
        if distance <= 1e-6:
            return extended

        ux = dx / distance
        uy = dy / distance
        steps = max(1, int(remaining / 2.5))
        for step in range(1, steps + 1):
            amount = remaining * (step / steps)
            extended.append({
                "x": last["x"] + (ux * amount),
                "y": last["y"] + (uy * amount)
            })

        return self._dedupe_points(extended)

    def _trim_path_to_length(self, points, target_length):
        if len(points) < 2 or target_length <= 0:
            return points

        trimmed = [points[0]]
        travelled = 0.0
        for index in range(len(points) - 1):
            start = points[index]
            end = points[index + 1]
            segment = math.hypot(
                end["x"] - start["x"],
                end["y"] - start["y"]
            )
            if segment <= 1e-6:
                continue

            if travelled + segment >= target_length:
                t = (target_length - travelled) / segment
                trimmed.append({
                    "x": start["x"] + ((end["x"] - start["x"]) * t),
                    "y": start["y"] + ((end["y"] - start["y"]) * t)
                })
                return self._dedupe_points(trimmed)

            trimmed.append(end)
            travelled += segment

        return self._dedupe_points(trimmed)
