import os


class BeatmapLoader:

    def __init__(self, songs_folder="songs"):

        self.songs_folder = songs_folder
        self.beatmaps = []

    def load_songs(self):

        self.beatmaps = []

        if not os.path.exists(self.songs_folder):
            return []

        for folder in os.listdir(self.songs_folder):

            path = os.path.join(self.songs_folder, folder)

            if os.path.isdir(path):

                self.beatmaps.append({
                    "name": folder,
                    "path": path
                })

        return self.beatmaps