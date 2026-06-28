import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.beatmap_info import LocalScoreManager
from core.osz_importer import OszImporter


OSU_TEXT = """osu file format v14

[General]
AudioFilename: audio.mp3

[Metadata]
Title: Import Test
Artist: Test Artist
Creator: Mapper
Version: Normal
BeatmapSetID: 12345

[Difficulty]
CircleSize:4
ApproachRate:9
OverallDifficulty:8
HPDrainRate:5
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
0,500,4,2,1,60,1,0

[HitObjects]
64,192,1000,1,0,0:0:0:0:
"""


class ImportAndScoreTests(unittest.TestCase):
    def test_osz_import_extracts_once_and_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            songs = root / "songs"
            imports = root / "imports"
            songs.mkdir()
            imports.mkdir()
            os.environ["PYOSU_SONGS_DIR"] = str(songs)
            os.environ["PYOSU_IMPORTS_DIR"] = str(imports)
            try:
                osz_path = root / "test.osz"
                with zipfile.ZipFile(osz_path, "w") as archive:
                    archive.writestr("test.osu", OSU_TEXT)
                    archive.writestr("audio.mp3", b"fake")

                importer = OszImporter(beatmap_loader=None)
                first = importer.import_file(osz_path)
                second = importer.import_file(osz_path)

                self.assertEqual(len(first.imported), 1)
                self.assertTrue((songs / "12345 Test Artist - Import Test").exists())
                self.assertEqual(second.imported, [])
                self.assertTrue(second.skipped)
            finally:
                os.environ.pop("PYOSU_SONGS_DIR", None)
                os.environ.pop("PYOSU_IMPORTS_DIR", None)

    def test_local_scores_keep_multiple_records_sorted_and_deletable(self):
        with tempfile.TemporaryDirectory() as tmp:
            score_path = Path(tmp) / "scores.json"
            manager = LocalScoreManager(score_path)

            manager.add_record("map.osu", {"score": 1000, "accuracy": 95.0, "combo": 20})
            manager.add_record("map.osu", {"score": 3000, "accuracy": 90.0, "combo": 10})
            manager.add_record("map.osu", {"score": 3000, "accuracy": 97.0, "combo": 30})

            records = manager.records_for("map.osu")
            self.assertEqual([record["score"] for record in records], [3000, 3000, 1000])
            self.assertEqual(records[0]["accuracy"], 97.0)

            self.assertTrue(manager.delete_record("map.osu", 1))
            self.assertEqual(len(manager.records_for("map.osu")), 2)
            self.assertFalse(manager.delete_record("map.osu", 99))

    def test_local_scores_can_be_removed_with_deleted_beatmap_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score_path = root / "scores.json"
            beatmap_folder = root / "songs" / "set"
            beatmap_folder.mkdir(parents=True)
            osu_file = beatmap_folder / "map.osu"
            other_file = root / "songs" / "other" / "map.osu"
            other_file.parent.mkdir(parents=True)

            manager = LocalScoreManager(score_path)
            manager.add_record(str(osu_file), {"score": 1000})
            manager.add_record(str(other_file), {"score": 2000})

            self.assertEqual(manager.delete_records_under(beatmap_folder), 1)
            self.assertEqual(manager.records_for(str(osu_file)), [])
            self.assertEqual(len(manager.records_for(str(other_file))), 1)


if __name__ == "__main__":
    unittest.main()
