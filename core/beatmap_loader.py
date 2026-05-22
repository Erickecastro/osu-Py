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
                    "notes": []
                }

                osu_file = self.find_osu_file(path)

                if osu_file:

                    notes = self.parse_hitobjects(osu_file)

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

                if len(parts) >= 3:

                    x = int(parts[0])
                    y = int(parts[1])
                    time = int(parts[2])

                    notes.append({
                        "x": x,
                        "y": y,
                        "time": time,
                        "active": False
                    })

        return notes