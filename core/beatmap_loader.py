import os
import hashlib
import math
from bisect import bisect_right


class BeatmapLoader:

    SONGS_PATH = "songs"
    
    def __init__(self):
        """Inicializa o loader com cache de curvas interpoladas"""
        self._curve_cache = {}  # Cache para curvas já interpoladas

    # -------------------------
    # LOAD SONGS
    # -------------------------
    def load_songs(self):

        beatmaps = []

        # cria pasta songs caso não exista
        if not os.path.exists(self.SONGS_PATH):

            os.makedirs(self.SONGS_PATH)

            return beatmaps

        # percorre todas as músicas
        for folder in os.listdir(self.SONGS_PATH):

            path = os.path.join(
                self.SONGS_PATH,
                folder
            )

            if not os.path.isdir(path):

                continue

            beatmap_data = {
                "name": folder,
                "path": path,
                "difficulties": []
            }

            osu_files = self.find_osu_files(path)

            # sem .osu
            if len(osu_files) == 0:

                continue

            # carrega dificuldades
            for osu_file in osu_files:

                try:

                    notes = self.parse_hitobjects(
                        osu_file
                    )

                    difficulty = self.parse_difficulty(
                        osu_file
                    )

                    metadata = self.parse_metadata(
                        osu_file
                    )

                    timing_points = self.parse_timing_points(
                        osu_file
                    )

                    difficulty_data = {
                        "name": folder,
                        "path": path,
                        "osu_file": osu_file,
                        "notes": notes,
                        "metadata": metadata,
                        "difficulty": difficulty,
                        "timing_points": timing_points
                    }

                    beatmap_data[
                        "difficulties"
                    ].append(
                        difficulty_data
                    )

                except Exception as e:

                    print(
                        f"Erro ao carregar {osu_file}"
                    )

                    print(e)

            # adiciona apenas se houver dificuldades
            if len(
                beatmap_data["difficulties"]
            ) > 0:

                beatmaps.append(beatmap_data)

        # ordena alfabeticamente
        beatmaps.sort(
            key=lambda x: x["name"].lower()
        )

        return beatmaps

    # -------------------------
    # METADATA
    # -------------------------
    def parse_metadata(self, osu_file):

        metadata = {
            "Title": "Unknown",
            "Artist": "Unknown",
            "Creator": "Unknown",
            "Version": "Unknown"
        }

        with open(
            osu_file,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            lines = file.readlines()

        metadata_section = False

        for line in lines:

            line = line.strip()

            if line == "[Metadata]":

                metadata_section = True

                continue

            if (
                metadata_section
                and
                line.startswith("[")
            ):

                break

            if metadata_section:

                if ":" not in line:

                    continue

                key, value = line.split(
                    ":",
                    1
                )

                metadata[
                    key.strip()
                ] = value.strip()

        return metadata

    # -------------------------
    # TIMING POINTS
    # -------------------------
    def parse_timing_points(self, osu_file):
        """
        Parse `[TimingPoints]` from an .osu file.

        We only keep:
        - `time` (ms)
        - `ms_per_beat` (can be negative for inherited points)
        - `uninherited` (1 = base point, 0 = inherited point)
        """
        timing_points = []

        with open(
            osu_file,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:
            lines = file.readlines()

        timing_section = False

        for line in lines:
            line = line.strip()

            if line == "[TimingPoints]":
                timing_section = True
                continue

            if timing_section and line.startswith("["):
                break

            if not timing_section or not line:
                continue

            parts = line.split(",")
            if len(parts) < 2:
                continue

            try:
                tp_time = float(parts[0])
                ms_per_beat = float(parts[1])
                uninherited = int(parts[6]) if len(parts) > 6 else 1
            except:
                continue

            timing_points.append({
                "time": tp_time,
                "ms_per_beat": ms_per_beat,
                "uninherited": uninherited
            })

        timing_points.sort(key=lambda tp: tp["time"])
        return timing_points

    # -------------------------
    # FIND .OSU FILES
    # -------------------------
    def find_osu_files(self, path):

        osu_files = []

        for file in os.listdir(path):

            if file.endswith(".osu"):

                osu_files.append(
                    os.path.join(path, file)
                )

        return osu_files

    # -------------------------
    # HITOBJECTS
    # -------------------------
    def parse_hitobjects(self, osu_file):

        notes = []

        with open(
            osu_file,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            lines = file.readlines()

        hitobjects_section = False

        for line in lines:

            line = line.strip()

            if line == "[HitObjects]":

                hitobjects_section = True

                continue

            if not hitobjects_section:

                continue

            if line == "":

                continue

            parts = line.split(",")

            if len(parts) < 4:

                continue

            try:

                x = int(parts[0])
                y = int(parts[1])
                time = int(parts[2])

                object_type = int(parts[3])

            except:

                continue

            # -------------------------
            # HIT CIRCLE
            # -------------------------
            if object_type & 1:

                notes.append({
                    "type": "circle",
                    "x": x,
                    "y": y,
                    "time": time,
                    "active": False
                })

            # -------------------------
            # SLIDER
            # -------------------------
            elif object_type & 2:

                curve_type = "L"
                curve_points = []
                repeat_count = 1
                slider_distance = 0.0

                if len(parts) > 5:

                    curve_data = parts[5]

                    curve_parts = curve_data.split("|")

                    # extrai tipo de curva (L, B, C, P)
                    if len(curve_parts) > 0:
                        curve_type = curve_parts[0]

                    # extrai pontos de controle
                    for point in curve_parts[1:]:

                        if ":" in point:

                            try:

                                px, py = point.split(":")

                                curve_points.append({
                                    "x": int(px),
                                    "y": int(py)
                                })

                            except:

                                pass

                # extrai slider_distance (comprimento do slider)
                if len(parts) > 7:
                    try:
                        slider_distance = float(parts[7])
                    except:
                        slider_distance = 0.0

                # extrai repeat_count (quantidade de repetições/voltas do slider)
                if len(parts) > 6:
                    try:
                        repeat_count = int(parts[6])
                    except:
                        repeat_count = 1

                # gera pontos suavizados baseado no tipo
                smooth_points = (
                    self.generate_slider_path(
                        curve_points,
                        curve_type,
                        slider_distance,
                        x,
                        y
                    )
                )

                notes.append({
                    "type": "slider",
                    "x": x,
                    "y": y,
                    "time": time,
                    "curve_points": smooth_points,
                    "curve_type": curve_type,
                    "slider_distance": slider_distance,
                    "repeat_count": repeat_count,
                    "active": False
                })

        notes.sort(
            key=lambda note: note["time"]
        )

        return notes


    def bezier_point(self, points, t):
        """Calcula um ponto em uma curva Bezier usando De Casteljau (iterativo)"""
        if not points:
            return {"x": 0, "y": 0}
        
        if len(points) == 1:
            return points[0]
        
        # Cria uma cópia dos pontos, com proteção contra valores inválidos
        current_points = []
        for p in points:
            x = float(p.get("x", 0))
            y = float(p.get("y", 0))
            
            # Proteção contra NaN e infinito
            if x != x or x == float('inf') or x == float('-inf'):
                x = 0
            if y != y or y == float('inf') or y == float('-inf'):
                y = 0
                
            current_points.append({"x": x, "y": y})
        
        if len(current_points) == 1:
            return current_points[0]
        
        # De Casteljau iterativo com proteção
        max_iterations = 1000  # Proteção contra loop infinito
        iteration = 0
        
        # Clamp t entre 0 e 1
        t = max(0.0, min(1.0, t))
        
        while len(current_points) > 1 and iteration < max_iterations:
            new_points = []
            for i in range(len(current_points) - 1):
                x = current_points[i]["x"] + (current_points[i + 1]["x"] - current_points[i]["x"]) * t
                y = current_points[i]["y"] + (current_points[i + 1]["y"] - current_points[i]["y"]) * t
                
                # Proteção contra overflow em curvas muito agressivas
                if abs(x) > 10000 or abs(y) > 10000:
                    # Limita valores extremos
                    x = max(-10000, min(10000, x))
                    y = max(-10000, min(10000, y))
                
                new_points.append({"x": x, "y": y})
            current_points = new_points
            iteration += 1
        
        result = current_points[0] if current_points else {"x": 0, "y": 0}
        return result


    def _distance(self, p1, p2):
        return math.hypot(p1.get("x", 0) - p2.get("x", 0), p1.get("y", 0) - p2.get("y", 0))


    def _adaptive_subdivide(self, points, t0, t1, p0, p1, tol, depth, max_depth):
        """Subdivide curve between t0 and t1 until flatness <= tol.

        Returns a list of points approximating the curve segment.
        """
        tm = (t0 + t1) / 2.0
        pm = self.bezier_point(points, tm)

        # mid point of chord
        mid_chord = {"x": (p0["x"] + p1["x"]) / 2.0, "y": (p0["y"] + p1["y"]) / 2.0}

        # flatness measure: distance between real midpoint and chord midpoint
        d = self._distance(pm, mid_chord)

        if d <= tol or depth >= max_depth:
            return [p0, p1]

        left = self._adaptive_subdivide(points, t0, tm, p0, pm, tol, depth + 1, max_depth)
        right = self._adaptive_subdivide(points, tm, t1, pm, p1, tol, depth + 1, max_depth)

        # combine, avoiding duplicate midpoint
        return left[:-1] + right


    def _split_bezier_segments(self, points):
        """Split Bezier control points into contiguous segments.

        In osu!, repeated control points are used to break a Bezier slider into
        multiple consecutive curve segments.
        """
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


    def generate_bezier_path_adaptive(self, points, tol=0.15, max_depth=22):
        """Generate an adaptive polyline approximation for a Bezier-like curve.

        Uses recursive subdivision based on midpoint chord error. Returns list of float points.
        """
        if not points:
            return []

        segments = self._split_bezier_segments(points)
        out = []
        prev = None

        for segment in segments:
            if len(segment) < 3:
                # For 2-point segments, create a synthetic control point for smooth transition
                if len(segment) == 2:
                    p0 = segment[0]
                    p2 = segment[1]
                    # Create midpoint control for smoother curve
                    p1 = {"x": (p0["x"] + p2["x"]) / 2.0, "y": (p0["y"] + p2["y"]) / 2.0}
                    pts = self._adaptive_subdivide([p0, p1, p2], 0.0, 1.0, p0, p2, tol, 0, max_depth)
                else:
                    pts = segment
            else:
                p0 = self.bezier_point(segment, 0.0)
                p1 = self.bezier_point(segment, 1.0)
                pts = self._adaptive_subdivide(segment, 0.0, 1.0, p0, p1, tol, 0, max_depth)

            for p in pts:
                if prev is None or p["x"] != prev["x"] or p["y"] != prev["y"]:
                    out.append(p)
                    prev = p

        return out


    def generate_catmull_path(self, points, steps=30):
        """Generate Catmull-Rom spline through the given points."""
        if not points:
            return []

        def catmull_rom(p0, p1, p2, p3, t):
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1["x"]) + (-p0["x"] + p2["x"]) * t + (2*p0["x"] - 5*p1["x"] + 4*p2["x"] - p3["x"]) * t2 + (-p0["x"] + 3*p1["x"] - 3*p2["x"] + p3["x"]) * t3)
            y = 0.5 * ((2 * p1["y"]) + (-p0["y"] + p2["y"]) * t + (2*p0["y"] - 5*p1["y"] + 4*p2["y"] - p3["y"]) * t2 + (-p0["y"] + 3*p1["y"] - 3*p2["y"] + p3["y"]) * t3)
            return {"x": x, "y": y}

        out = []
        n = len(points)
        pts = [points[0]] + points + [points[-1]]
        for i in range(0, n - 1):
            p0 = pts[i]
            p1 = pts[i+1]
            p2 = pts[i+2]
            p3 = pts[i+3]
            for s in range(steps):
                t = s / steps
                p = catmull_rom(p0, p1, p2, p3, t)
                out.append({"x": p["x"], "y": p["y"]})
        out.append({"x": points[-1]["x"], "y": points[-1]["y"]})
        filtered = []
        prev = None
        for p in out:
            if prev is None or p["x"] != prev["x"] or p["y"] != prev["y"]:
                filtered.append(p)
                prev = p
        return filtered


    def _rdp(self, points, epsilon=1.0):
        """Ramer-Douglas-Peucker algorithm for polyline simplification."""
        if not points:
            return []

        def perp_dist(a, b, c):
            # distance from c to line a-b
            ax, ay = a['x'], a['y']
            bx, by = b['x'], b['y']
            cx, cy = c['x'], c['y']
            dx = bx - ax
            dy = by - ay
            if dx == 0 and dy == 0:
                return math.hypot(cx - ax, cy - ay)
            return abs(dy*cx - dx*cy + bx*ay - by*ax) / math.hypot(dx, dy)

        def rdp_rec(pts):
            if len(pts) < 3:
                return pts
            maxd = 0.0
            idx = 0
            for i in range(1, len(pts)-1):
                d = perp_dist(pts[0], pts[-1], pts[i])
                if d > maxd:
                    maxd = d
                    idx = i
            if maxd > epsilon:
                left = rdp_rec(pts[:idx+1])
                right = rdp_rec(pts[idx:])
                return left[:-1] + right
            else:
                return [pts[0], pts[-1]]

        return rdp_rec(points)


    def generate_perfect_path(self, points, steps_per_rad=12):
        """Approximate osu! perfect-circle (arc) sliders.

        In osu!, `P` sliders are circular arcs defined by exactly 3 points:
        start, control, end. If the control point set doesn't define a circle
        (collinear) or if there are more than 3 points, fall back to Bezier/linear.
        """
        if not points:
            return []
        if len(points) < 3:
            return self.generate_bezier_path_adaptive(points)
        if len(points) != 3:
            # `P` with more points should not be stitched as multiple arcs here;
            # treat it like a regular Bezier to avoid wrong shapes.
            return self.generate_bezier_path_adaptive(points)

        def circle_from_three(a, b, c):
            # returns (cx, cy, r) or None if collinear
            ax, ay = a["x"], a["y"]
            bx, by = b["x"], b["y"]
            cx, cy = c["x"], c["y"]
            d = 2 * (ax*(by-cy) + bx*(cy-ay) + cx*(ay-by))
            if abs(d) < 1e-6:
                return None
            ux = ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) + (cx*cx+cy*cy)*(ay-by)) / d
            uy = ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) + (cx*cx+cy*cy)*(bx-ax)) / d
            r = math.hypot(ax-ux, ay-uy)
            return ux, uy, r

        def angle_of(p, cx, cy):
            return math.atan2(p["y"] - cy, p["x"] - cx)

        a, b, c = points[0], points[1], points[2]
        circ = circle_from_three(a, b, c)
        if circ is None:
            # Collinear: treat as straight line from a to c
            return self.generate_linear_path([a, c], steps=32)

        cx, cy, r = circ

        def norm(angle):
            angle = angle % (2 * math.pi)
            if angle < 0:
                angle += 2 * math.pi
            return angle

        a_n = norm(angle_of(a, cx, cy))
        b_n = norm(angle_of(b, cx, cy))
        c_n = norm(angle_of(c, cx, cy))

        def ccw_delta(start, end):
            d = end - start
            if d < 0:
                d += 2 * math.pi
            return d

        # Choose the unique arc from a -> c that passes through b.
        # If b lies on the counter-clockwise sweep from a to c, go CCW; otherwise go CW.
        ccw_ac = ccw_delta(a_n, c_n)
        ccw_ab = ccw_delta(a_n, b_n)

        if ccw_ab <= ccw_ac:
            span = ccw_ac  # CCW
        else:
            span = ccw_ac - 2 * math.pi  # CW (negative span)

        samp = max(6, int(abs(span) * steps_per_rad))
        out = []
        for s in range(samp + 1):
            t = s / samp
            ang = a_n + t * span
            x = cx + math.cos(ang) * r
            y = cy + math.sin(ang) * r
            out.append({"x": x, "y": y})
        filtered = []
        prev = None
        for p in out:
            if prev is None or p["x"] != prev["x"] or p["y"] != prev["y"]:
                filtered.append(p)
                prev = p
        return filtered


    def generate_linear_path(self, points, steps=25):
        """Gera uma linha reta entre os pontos"""
        smooth_points = []
        
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i + 1]
            
            for step in range(steps):
                t = step / steps
                x = start["x"] + (end["x"] - start["x"]) * t
                y = start["y"] + (end["y"] - start["y"]) * t
                smooth_points.append({"x": x, "y": y})
        
        smooth_points.append({
            "x": points[-1]["x"],
            "y": points[-1]["y"]
        })
        
        return smooth_points

    # -------------------------
    # SLIDER SMOOTHING (MAIN)
    # -------------------------
    def _curve_hash(self, points, curve_type):
        """Cria uma chave hash para cache de curvas"""
        # Cria string dos pontos para hash
        points_str = str([(p["x"], p["y"]) for p in points])
        combined = f"{points_str}_{curve_type}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _validate_slider_points(self, points):
        """Valida pontos do slider - apenas converte para int, sem limitar"""
        validated = []
        for point in points:
            x = point.get("x", 0)
            y = point.get("y", 0)

            # Apenas converte para int, permite pontos fora dos limites
            # (pygame fará clipping na renderização)
            validated.append({"x": int(x), "y": int(y)})

        return validated

    def _resample_slider_path(self, points, min_points=24, spacing=3.5):
        """Reamostra o caminho do slider com densidade mínima para evitar buracos."""
        if len(points) < 2:
            return points

        total_length = 0.0
        cumulative = [0.0]

        for i in range(len(points) - 1):
            dx = points[i + 1]["x"] - points[i]["x"]
            dy = points[i + 1]["y"] - points[i]["y"]
            segment = math.hypot(dx, dy)
            total_length += segment
            cumulative.append(total_length)

        if total_length <= 0:
            return points

        target_count = max(min_points, min(320, int(total_length / spacing)))

        if len(points) >= target_count:
            return points

        resampled = []
        for i in range(target_count):
            target_distance = cumulative[-1] * (i / (target_count - 1))
            idx = bisect_right(cumulative, target_distance) - 1
            idx = max(0, min(idx, len(points) - 2))

            start = points[idx]
            end = points[idx + 1]
            segment_start = cumulative[idx]
            segment_end = cumulative[idx + 1]
            segment_length = max(segment_end - segment_start, 1e-6)
            t = (target_distance - segment_start) / segment_length
            t = max(0.0, min(1.0, t))

            x = start["x"] + (end["x"] - start["x"]) * t
            y = start["y"] + (end["y"] - start["y"]) * t
            resampled.append({"x": x, "y": y})

        return resampled



    # -------------------------
    # DIFFICULTY
    # -------------------------
    def parse_difficulty(self, osu_file):

        difficulty = {
            "CS": 4,
            "AR": 9,
            "OD": 8,
            "HP": 5,
            "SliderMultiplier": 1.4,
            "SliderTickRate": 1
        }

        with open(
            osu_file,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            lines = file.readlines()

        difficulty_section = False

        for line in lines:

            line = line.strip()

            if line == "[Difficulty]":

                difficulty_section = True

                continue

            if (
                difficulty_section
                and
                line.startswith("[")
            ):

                break

            if not difficulty_section:

                continue

            if ":" not in line:

                continue

            key, value = line.split(
                ":",
                1
            )

            key = key.strip()
            value = value.strip()

            try:

                if key == "CircleSize":

                    difficulty["CS"] = float(value)

                elif key == "ApproachRate":

                    difficulty["AR"] = float(value)

                elif key == "OverallDifficulty":

                    difficulty["OD"] = float(value)

                elif key == "HPDrainRate":

                    difficulty["HP"] = float(value)

                elif key == "SliderMultiplier":

                    difficulty[
                        "SliderMultiplier"
                    ] = float(value)

                elif key == "SliderTickRate":

                    difficulty[
                        "SliderTickRate"
                    ] = float(value)

            except:

                pass

        return difficulty
    

    def _densify_uniform(self, points, spacing=6.0):

        if len(points) < 2:
            return points

        densified = []

        for i in range(len(points) - 1):

            p1 = points[i]
            p2 = points[i + 1]

            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]

            dist = math.hypot(dx, dy)

            if dist <= 0:
                continue

            steps = max(
                1,
                int(dist / spacing)
            )

            for s in range(steps):

                if len(densified) > 5000:
                    break

                t = s / steps

                x = p1["x"] + dx * t
                y = p1["y"] + dy * t

                densified.append({
                    "x": x,
                    "y": y
                })

        densified.append(points[-1])

        return densified



    def generate_slider_path(self, points, curve_type="L", slider_distance=0.0, start_x=0, start_y=0):
        """Gera caminho do slider com normalização de comprimento"""

        smooth_points = []

        if len(points) < 1:
            return smooth_points

        if len(points) == 1:
            # Se tem apenas um ponto de controle, estende em linha reta
            if slider_distance > 0:
                end_x = points[0]["x"]
                end_y = points[0]["y"]
                direction_x = end_x - start_x
                direction_y = end_y - start_y
                dist_to_point = math.hypot(direction_x, direction_y)
                
                if dist_to_point > 0:
                    # Normaliza direção
                    direction_x /= dist_to_point
                    direction_y /= dist_to_point
                    
                    # Calcula ponto final na distância correta
                    final_x = start_x + direction_x * slider_distance
                    final_y = start_y + direction_y * slider_distance
                    
                    # Cria pontos intermediários
                    steps = max(16, int(slider_distance / 2))
                    for i in range(steps + 1):
                        t = i / max(1, steps)
                        x = start_x + direction_x * (slider_distance * t)
                        y = start_y + direction_y * (slider_distance * t)
                        smooth_points.append({"x": int(round(x)), "y": int(round(y))})
                    return smooth_points
            
            return points

        # CRITICAL: The curve must start from the slider position
        # osu! curve_points define control points, but the Bezier must begin at slider start
        # Add slider start position as the first control point
        path_points = [{"x": float(start_x), "y": float(start_y)}] + points

        # Interpola baseado no tipo de curva
        if curve_type == "B":
            smooth_points = self.generate_bezier_path_adaptive(
                path_points,
                tol=0.15,
                max_depth=22
            )
        elif curve_type == "C":
            smooth_points = self.generate_catmull_path(
                path_points,
                steps=35
            )
        elif curve_type == "P":
            smooth_points = self.generate_perfect_path(
                path_points,
                steps_per_rad=14
            )
        else:  # Linear
            smooth_points = self.generate_linear_path(
                path_points,
                steps=32
            )

        # Lighter densification - only fill gaps
        smooth_points = self._densify_uniform(
            smooth_points,
            spacing=2.5
        )

        # Normaliza o comprimento do slider se foi especificado
        if slider_distance > 0 and len(smooth_points) > 1:
            smooth_points = self._normalize_slider_length(
                smooth_points,
                slider_distance
            )
        
        # Final resampling with better parameters
        smooth_points = self._resample_slider_path(
            smooth_points,
            min_points=80,
            spacing=2.5
        )

        smooth_points = self._validate_slider_points(smooth_points)

        if len(smooth_points) > 2500:
            smooth_points = smooth_points[::2]

        return smooth_points

    def _normalize_slider_length(self, points, target_length):
        """Normaliza o comprimento do slider para corresponder ao slider_distance especificado"""
        
        if len(points) < 2 or target_length <= 0:
            return points
        
        # Calcula comprimento total do caminho interpolado
        total_length = 0.0
        arc_lengths = [0.0]
        
        for i in range(1, len(points)):
            p1 = points[i - 1]
            p2 = points[i]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            segment_length = math.hypot(dx, dy)
            total_length += segment_length
            arc_lengths.append(total_length)
        
        if total_length <= 0:
            return points
        
        # Se o caminho é muito curto ou muito longo, tenta resampling
        scale_factor = target_length / total_length
        
        # Se a proporção está muito próxima (90-110%), retorna como está
        if scale_factor >= 0.9 and scale_factor <= 1.1:
            return points
        
        # Cria novo caminho resamplado no comprimento alvo
        # Usa interpolação paramétrica ao longo da curva original
        resampled = [points[0]]
        num_samples = max(32, int(target_length / 2.5))
        
        for sample in range(1, num_samples + 1):
            # Distância no caminho original que corresponde ao sample
            target_distance_scaled = (sample / num_samples) * target_length
            
            # Encontra qual segmento contém esse comprimento no mapa original
            # Usa proporção inversa para encontrar no caminho original
            distance_in_original = target_distance_scaled / scale_factor if scale_factor > 0 else 0
            
            # Busca binária para encontrar o índice do ponto mais próximo
            for i in range(len(arc_lengths) - 1):
                if arc_lengths[i] <= distance_in_original <= arc_lengths[i + 1]:
                    p1 = points[i]
                    p2 = points[i + 1]
                    
                    # Interpola linearmente dentro do segmento
                    segment_length = arc_lengths[i + 1] - arc_lengths[i]
                    
                    if segment_length > 0:
                        t = (distance_in_original - arc_lengths[i]) / segment_length
                        t = max(0.0, min(1.0, t))
                    else:
                        t = 0.0
                    
                    x = p1["x"] + (p2["x"] - p1["x"]) * t
                    y = p1["y"] + (p2["y"] - p1["y"]) * t
                    
                    resampled.append({"x": x, "y": y})
                    break
        
        # Garante que o último ponto está incluído
        if len(resampled) > 0 and (len(resampled) < 2 or resampled[-1] != points[-1]):
            resampled.append(points[-1])
        
        # Recalcula para verificar o comprimento final
        final_length = 0.0
        for i in range(len(resampled) - 1):
            p1 = resampled[i]
            p2 = resampled[i + 1]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            final_length += math.hypot(dx, dy)
        
        # Se o resultado está muito distante, retorna o original
        if abs(final_length - target_length) > target_length * 0.3:
            return points
        
        return resampled