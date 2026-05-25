import os


class BeatmapLoader:

    SONGS_PATH = "songs"

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

                    difficulty_data = {
                        "name": folder,
                        "path": path,
                        "osu_file": osu_file,
                        "notes": notes,
                        "metadata": metadata,
                        "difficulty": difficulty
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

                # gera pontos suavizados baseado no tipo
                smooth_points = (
                    self.generate_slider_path(
                        curve_points,
                        curve_type
                    )
                )

                notes.append({
                    "type": "slider",
                    "x": x,
                    "y": y,
                    "time": time,
                    "curve_points": smooth_points,
                    "curve_type": curve_type,
                    "active": False
                })

        # ordena notas por tempo
        notes.sort(
            key=lambda note: note["time"]
        )

        return notes

    # -------------------------
    # BEZIER CURVE
    # -------------------------
    def bezier_point(self, points, t):
        """Calcula um ponto em uma curva Bezier usando De Casteljau (iterativo)"""
        # cópia dos pontos para não modificar original
        current_points = [{"x": p["x"], "y": p["y"]} for p in points]
        
        # aplica interpolação linear até restar um ponto
        while len(current_points) > 1:
            new_points = []
            for i in range(len(current_points) - 1):
                x = current_points[i]["x"] + (current_points[i + 1]["x"] - current_points[i]["x"]) * t
                y = current_points[i]["y"] + (current_points[i + 1]["y"] - current_points[i]["y"]) * t
                new_points.append({"x": x, "y": y})
            current_points = new_points
        
        return current_points[0]

    # -------------------------
    # LINEAR CURVE
    # -------------------------
    def generate_linear_path(self, points, steps=25):
        """Gera uma linha reta entre os pontos"""
        smooth_points = []
        
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i + 1]
            
            for step in range(steps):
                t = step / steps
                
                x = int(start["x"] + (end["x"] - start["x"]) * t)
                y = int(start["y"] + (end["y"] - start["y"]) * t)
                
                smooth_points.append({"x": x, "y": y})
        
        smooth_points.append({
            "x": int(points[-1]["x"]),
            "y": int(points[-1]["y"])
        })
        
        return smooth_points

    # -------------------------
    # SLIDER SMOOTHING (MAIN)
    # -------------------------
    def generate_slider_path(self, points, curve_type="L"):
        """Gera caminho suavizado do slider baseado no tipo de curva"""
        
        smooth_points = []
        
        if len(points) < 1:
            return smooth_points
        
        if len(points) == 1:
            return points
        
        # tipos de curva: L (Linear), B (Bezier), C (Catmull), P (Perfect Circle)
        if curve_type in ["B", "P", "C"]:
            # Bezier, Perfect Circle e Catmull usam interpolação suave
            # Reduzido para 25 passos para performance
            steps = 25
            for step in range(steps + 1):
                t = step / steps
                point = self.bezier_point(points, t)
                smooth_points.append({
                    "x": int(point["x"]),
                    "y": int(point["y"])
                })
        
        else:
            # Linear ou desconhecido
            smooth_points = self.generate_linear_path(points, steps=25)
        
        return smooth_points

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