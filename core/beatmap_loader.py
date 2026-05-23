import os


class BeatmapLoader:

    SONGS_PATH = "songs"

    def load_songs(self):

        beatmaps = []

        if not os.path.exists(self.SONGS_PATH):
            return beatmaps

        for folder in os.listdir(self.SONGS_PATH):

            path = os.path.join(self.SONGS_PATH, folder)

            if os.path.isdir(path):

                beatmap_data = {
                    "name": folder,
                    "path": path,
                    "notes": [],
                    "difficulty": {}
                }

                osu_file = self.find_osu_file(path)

                if osu_file:

                    notes = self.parse_hitobjects(osu_file)
                    difficulty = self.parse_difficulty(osu_file)
                    beatmap_data["difficulty"] = difficulty
                    
                    beatmap_data["notes"] = notes

                beatmaps.append(beatmap_data)

        return beatmaps

    def find_osu_file(self, path):

        for file in os.listdir(path):

            if file.endswith(".osu"):

                return os.path.join(path, file)

        return None

    def parse_hitobjects(self, osu_file):

        notes = []

        with open(osu_file, "r", encoding="utf-8") as file:

            lines = file.readlines()

        hitobjects_section = False

        for line in lines:

            line = line.strip()

            if line == "[HitObjects]":
                hitobjects_section = True
                continue

            if hitobjects_section:

                if line == "":
                    continue

                parts = line.split(",")

                if len(parts) >= 4:

                    x = int(parts[0])
                    y = int(parts[1])
                    time = int(parts[2])

                    object_type = int(parts[3])

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

                        curve_points = []

                        if len(parts) > 5:

                            curve_data = parts[5]

                            curve_parts = curve_data.split("|")

                            for point in curve_parts[1:]:

                                if ":" in point:

                                    px, py = point.split(":")

                                    curve_points.append({
                                        "x": int(px),
                                        "y": int(py)
                                    })

                        notes.append({
                            "type": "slider",
                            "x": x,
                            "y": y,
                            "time": time,
                            "curve_points": curve_points,
                            "active": False
                        })

        return notes
    
    def parse_difficulty(self, osu_file):

        difficulty = {
            "CS": 4,
            "AR": 9,
            "OD": 8,
            "HP": 5,
            "SliderMultiplier": 1.4,
            "SliderTickRate": 1
        }

        with open(osu_file, "r", encoding="utf-8") as file:

            lines = file.readlines()

        difficulty_section = False

        for line in lines:

            line = line.strip()

            if line == "[Difficulty]":
                difficulty_section = True
                continue

            # terminou seção
            if difficulty_section and line.startswith("["):
                break

            if difficulty_section:

                if ":" not in line:
                    continue

                key, value = line.split(":", 1)

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
                        difficulty["SliderMultiplier"] = float(value)

                    elif key == "SliderTickRate":
                        difficulty["SliderTickRate"] = float(value)

                except:
                    pass

        return difficulty