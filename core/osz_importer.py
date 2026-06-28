import os
import re
import shutil
import zipfile
import hashlib
from pathlib import Path, PurePosixPath

from core.utils import (
    application_base_dirs,
    discover_user_data_directories,
    resolve_user_data_path
)


class OszImportResult:
    def __init__(self):
        self.imported = []
        self.skipped = []
        self.errors = []

    @property
    def changed(self):
        return bool(self.imported)

    def extend(self, other):
        self.imported.extend(other.imported)
        self.skipped.extend(other.skipped)
        self.errors.extend(other.errors)


class OszImporter:
    def __init__(self, beatmap_loader):
        self.beatmap_loader = beatmap_loader

    def import_pending(self):
        result = OszImportResult()
        seen = set()
        import_dirs = list(discover_user_data_directories("imports"))
        import_dirs.append(resolve_user_data_path("imports"))
        import_dirs.extend(application_base_dirs())

        for import_dir in import_dirs:
            import_path = Path(import_dir)
            if not import_path.exists():
                continue
            try:
                osz_files = sorted(import_path.glob("*.osz"))
            except OSError as exc:
                result.errors.append((str(import_path), str(exc)))
                continue

            for osz_file in osz_files:
                key = os.path.normcase(str(osz_file.resolve()))
                if key in seen:
                    continue
                seen.add(key)
                single_result = self.import_file(osz_file)
                result.extend(single_result)
                if single_result.imported or single_result.skipped:
                    self._archive_import_file(osz_file)

        return result

    def import_file(self, osz_path):
        result = OszImportResult()
        osz_path = Path(osz_path)
        if osz_path.suffix.lower() != ".osz":
            result.skipped.append((str(osz_path), "not an .osz file"))
            return result
        if not osz_path.exists():
            result.errors.append((str(osz_path), "file not found"))
            return result

        songs_dir = Path(resolve_user_data_path("songs"))
        songs_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(osz_path) as archive:
                members = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir()
                ]
                osu_members = [
                    info
                    for info in members
                    if info.filename.lower().endswith(".osu")
                ]
                if not osu_members:
                    result.errors.append((str(osz_path), "no .osu files found"))
                    return result

                archive_identity = self._archive_identity(archive, osu_members)
                duplicate_reason = self._duplicate_reason(archive_identity)
                if duplicate_reason:
                    result.skipped.append((str(osz_path), duplicate_reason))
                    return result

                folder_name = self._folder_name_from_archive(
                    archive,
                    osu_members[0],
                    osz_path.stem
                )
                target_dir = songs_dir / folder_name
                if target_dir.exists() and any(target_dir.glob("*.osu")):
                    result.skipped.append((str(osz_path), f"already imported: {folder_name}"))
                    return result

                target_dir = self._unique_directory(target_dir)
                target_dir.mkdir(parents=True, exist_ok=False)
                try:
                    for member in members:
                        self._extract_member(archive, member, target_dir)
                except Exception:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    raise

                result.imported.append(str(target_dir))
        except zipfile.BadZipFile:
            result.errors.append((str(osz_path), "invalid .osz archive"))
        except (OSError, RuntimeError, ValueError) as exc:
            result.errors.append((str(osz_path), str(exc)))

        return result

    def _archive_identity(self, archive, osu_members):
        set_ids = set()
        hashes = set()
        title_keys = set()
        for member in osu_members:
            try:
                data = archive.read(member)
            except (KeyError, OSError):
                continue
            hashes.add(hashlib.sha1(data).hexdigest())
            text = self._decode_osu_bytes(data)
            metadata = self._parse_osu_metadata(text)
            set_id = metadata.get("BeatmapSetID", "").strip()
            if set_id and set_id != "-1":
                set_ids.add(set_id)
            artist = (metadata.get("ArtistUnicode") or metadata.get("Artist") or "").strip().lower()
            title = (metadata.get("TitleUnicode") or metadata.get("Title") or "").strip().lower()
            creator = metadata.get("Creator", "").strip().lower()
            if artist and title:
                title_keys.add((artist, title, creator))
        return {
            "set_ids": set_ids,
            "hashes": hashes,
            "title_keys": title_keys
        }

    def _duplicate_reason(self, archive_identity):
        existing = self._existing_beatmap_identities()
        set_overlap = archive_identity["set_ids"] & existing["set_ids"]
        if set_overlap:
            return f"already imported beatmap set: {sorted(set_overlap)[0]}"

        hash_overlap = archive_identity["hashes"] & existing["hashes"]
        if hash_overlap:
            return "already imported identical .osu difficulty"

        if not archive_identity["set_ids"]:
            title_overlap = archive_identity["title_keys"] & existing["title_keys"]
            if title_overlap:
                artist, title, _creator = sorted(title_overlap)[0]
                return f"possibly already imported: {artist} - {title}"

        return None

    def _existing_beatmap_identities(self):
        identities = {
            "set_ids": set(),
            "hashes": set(),
            "title_keys": set()
        }
        seen_dirs = set()
        for songs_dir in discover_user_data_directories("songs"):
            songs_path = Path(songs_dir)
            if not songs_path.exists():
                continue
            try:
                resolved_dir = os.path.normcase(str(songs_path.resolve()))
            except OSError:
                resolved_dir = os.path.normcase(str(songs_path))
            if resolved_dir in seen_dirs:
                continue
            seen_dirs.add(resolved_dir)
            try:
                osu_files = songs_path.rglob("*.osu")
                for osu_file in osu_files:
                    self._add_existing_osu_identity(osu_file, identities)
            except OSError:
                continue
        return identities

    def _add_existing_osu_identity(self, osu_file, identities):
        try:
            data = Path(osu_file).read_bytes()
        except OSError:
            return
        identities["hashes"].add(hashlib.sha1(data).hexdigest())
        text = self._decode_osu_bytes(data)
        metadata = self._parse_osu_metadata(text)
        set_id = metadata.get("BeatmapSetID", "").strip()
        if set_id and set_id != "-1":
            identities["set_ids"].add(set_id)
        artist = (metadata.get("ArtistUnicode") or metadata.get("Artist") or "").strip().lower()
        title = (metadata.get("TitleUnicode") or metadata.get("Title") or "").strip().lower()
        creator = metadata.get("Creator", "").strip().lower()
        if artist and title:
            identities["title_keys"].add((artist, title, creator))

    def _archive_import_file(self, osz_path):
        osz_path = Path(osz_path)
        try:
            imported_dir = osz_path.parent / "imported"
            imported_dir.mkdir(parents=True, exist_ok=True)
            target = imported_dir / osz_path.name
            if target.exists():
                target = imported_dir / self._unique_file_name(osz_path.name, imported_dir)
            shutil.move(str(osz_path), str(target))
        except OSError:
            pass

    def _folder_name_from_archive(self, archive, osu_member, fallback):
        text = self._read_osu_member_text(archive, osu_member)
        metadata = self._parse_osu_metadata(text)
        set_id = metadata.get("BeatmapSetID", "").strip()
        artist = metadata.get("ArtistUnicode") or metadata.get("Artist") or ""
        title = metadata.get("TitleUnicode") or metadata.get("Title") or ""
        if artist and title:
            name = f"{set_id} {artist} - {title}" if set_id and set_id != "-1" else f"{artist} - {title}"
        else:
            name = fallback
        return self._sanitize_folder_name(name)

    def _read_osu_member_text(self, archive, member):
        data = archive.read(member)
        return self._decode_osu_bytes(data)

    def _decode_osu_bytes(self, data):
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")

    def _parse_osu_metadata(self, text):
        metadata = {}
        in_metadata = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line == "[Metadata]":
                in_metadata = True
                continue
            if in_metadata and line.startswith("["):
                break
            if not in_metadata or ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
        return metadata

    def _extract_member(self, archive, member, target_dir):
        relative = self._safe_relative_path(member.filename)
        if relative is None:
            return

        destination = target_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, open(destination, "wb") as output:
            shutil.copyfileobj(source, output)

    def _safe_relative_path(self, filename):
        normalized = filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            return None
        parts = [
            self._sanitize_path_part(part)
            for part in path.parts
            if part and part != "."
        ]
        if not parts:
            return None
        return Path(*parts)

    def _sanitize_folder_name(self, name):
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
        name = " ".join(name.split()).strip(" .")
        return name[:140] or "Imported beatmap"

    def _sanitize_path_part(self, name):
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
        sanitized = sanitized.strip(" .")
        return sanitized or "_"

    def _unique_directory(self, target_dir):
        if not target_dir.exists():
            return target_dir
        parent = target_dir.parent
        stem = target_dir.name
        for index in range(2, 1000):
            candidate = parent / f"{stem} ({index})"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"could not create unique folder for {target_dir}")

    def _unique_file_name(self, file_name, directory):
        path = Path(file_name)
        for index in range(2, 1000):
            candidate = f"{path.stem} ({index}){path.suffix}"
            if not (directory / candidate).exists():
                return candidate
        return f"{path.stem} imported{path.suffix}"
