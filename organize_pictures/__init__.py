import atexit
import os
from datetime import timedelta
import pathlib
import shutil
from glob import glob

import sqlite3
from pillow_heif import register_heif_opener

from organize_pictures.TruImage import TruImage
from organize_pictures.TruVideo import TruVideo
from organize_pictures.utils import (
    get_logger,
    MEDIA_TYPES,
    OFFSET_CHARS,
    DATE_FORMATS,
    FILE_EXTS,
)

register_heif_opener()


# pylint: disable=too-many-instance-attributes
class OrganizePictures:

    # pylint: disable=too-many-arguments
    def __init__(
            self,
            source_directory: str,
            destination_directory: str,
            extensions: list = None,
            media_type: str = None,
            dry_run: bool = False,
            cleanup: bool = False,
            sub_dirs: bool = True,
            offset: dict = None,
            minus: bool = False,
            verbose: bool = False,
    ):
        self.logger = get_logger(verbose)
        self.source_dir = source_directory
        self.dest_dir = destination_directory
        self.media_type = media_type
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.sub_dirs = sub_dirs
        self.offset = offset or self.init_offset()
        self.excluded = []
        self.minus = minus
        self.verbose = verbose

        self.results = {"moved": 0, "duplicate": 0, "failed": 0, "manual": 0, "invalid": 0, "deleted": 0}
        self.manual_review_files: list[str] = []
        self.failed_files: list[str] = []
        self.invalid_files: list[str] = []

        self.extensions = extensions
        if self.extensions is None:
            if media_type is not None:
                self.extensions = MEDIA_TYPES.get(media_type)
            else:
                self.extensions = []
                for exts in MEDIA_TYPES.values():
                    self.extensions += exts

        self.current_hash = None
        self.current_media = None
        self.db_filename = 'pictures.db'
        self.table_name = "image_hashes"
        if os.path.isfile(f'/raid2/{self.db_filename}'):
            db_file = f'/raid2/{self.db_filename}'
        else:
            db_file = f'./{self.db_filename}'

        if self.dry_run and not os.path.isfile(db_file):
            # No DB yet: in dry-run mode, use an in-memory DB so we don't create a real one.
            db_file = ":memory:"
            create = True
        else:
            create = not os.path.isfile(db_file)

        self.db_conn = sqlite3.connect(db_file)
        self.dbc = self.db_conn.cursor()

        if create:
            self.dbc.execute(
                f"CREATE TABLE {self.table_name} (image_path text, hash text, UNIQUE(image_path) ON CONFLICT IGNORE)"
            )
        atexit.register(self._complete)

    def _complete(self):
        try:
            self.logger.debug("EXIT: Committing final records")
            self.db_conn.commit()
            self.db_conn.close()
        except (sqlite3.OperationalError, sqlite3.ProgrammingError):
            # Database connection already closed or database file deleted
            pass

    @staticmethod
    def init_offset():
        return dict.fromkeys(list(OFFSET_CHARS), 0)

    def _apply_offset(self, date_taken):
        """
        Apply the configured offset to a datetime object
        :param date_taken: datetime object to apply offset to
        :return: datetime object with offset applied
        """
        if date_taken is None:
            return None

        # Calculate the timedelta from the offset dictionary
        delta = timedelta(
            days=self.offset.get('Y', 0) * 365 + self.offset.get('M', 0) * 30 + self.offset.get('D', 0),
            hours=self.offset.get('h', 0),
            minutes=self.offset.get('m', 0),
            seconds=self.offset.get('s', 0)
        )

        # Apply the offset (add or subtract based on minus flag)
        if self.minus:
            return date_taken - delta
        else:
            return date_taken + delta

    @staticmethod
    def _file_path(file_info):
        """
        File path for the given file info
        :param file_info: Dict of file info containing dir and filename
        :return:
        """
        return f"{file_info.get('dir')}/{file_info.get('filename')}{file_info.get('ext')}"

    def _check_db_for_media_path(self, media_path):
        sql = f"SELECT * FROM {self.table_name} WHERE image_path = ?"
        return dict(self.dbc.execute(sql, (media_path,)).fetchall())

    def _check_db_for_media_hash(self, media_hash):
        sql = f"SELECT * FROM {self.table_name} WHERE hash = ?"
        return dict(self.dbc.execute(sql, (media_hash,)).fetchall())

    def _check_db_for_media_path_hash(self, media):
        return self._check_db_for_media_hash(media.hash)

    def _insert_media_hash(self, media_path: str):
        if not os.path.isfile(media_path):
            self.logger.error(f"Media path does not exist: {media_path}")
            return False
        media = self._init_media_file(media_file_path=media_path)
        if media and media.hash:
            sql = f"INSERT INTO {self.table_name} VALUES (?, ?)"
            self.dbc.execute(sql, (media_path, media.hash))
            self.current_hash = None
            return True
        return False

    def _get_file_paths(
            self,
            base_dir: str = '.',
            extensions: list = None,
            recursive: bool = True
    ):
        """
        Get all files in the given path matching the given pattern and extensions.
        Files inside `self.dest_dir` are excluded so a previous run's output is never
        re-ingested.
        :param base_dir: Base directory to search
        :param extensions: Extensions to search for
        :param recursive:
        :return:
        """
        if extensions is None:
            extensions = self.extensions
        dest_real = os.path.realpath(self.dest_dir) if self.dest_dir else None
        results = []
        for _file in sorted(glob(f"{base_dir}/**/*", recursive=recursive)):
            if pathlib.Path(_file).suffix.lower() not in extensions:
                continue
            abs_path = os.path.abspath(_file)
            if dest_real:
                real = os.path.realpath(abs_path)
                if real == dest_real or real.startswith(dest_real + os.sep):
                    continue
            results.append(abs_path)
        return results

    def _init_media_file(self, media_file_path: str):
        for media_type in MEDIA_TYPES:
            if pathlib.Path(media_file_path).suffix.lower() in MEDIA_TYPES.get(media_type):
                match media_type:
                    case 'image':
                        return TruImage(
                            media_path=media_file_path, logger=self.logger, dry_run=self.dry_run
                        )
                    case 'video':
                        return TruVideo(
                            media_path=media_file_path, logger=self.logger, dry_run=self.dry_run
                        )
        return None

    def _get_medias(self, base_dir: str):
        """
        Get objects for media in the given path. Group files by base name first so duplicate
        base names can be flagged for manual intervention without partial-state bugs.
        :param base_dir: Path to search for media files
        :return:
        """
        self.logger.debug(f"Pre-processing media files in {base_dir}")
        media_files = self._get_file_paths(base_dir=base_dir)

        groups: dict[str, list[str]] = {}
        for media_file_path in media_files:
            file_base_name = pathlib.Path(media_file_path).stem

            if "(" in file_base_name or ")" in file_base_name or len(os.path.basename(media_file_path)) >= 146:
                self.logger.error(
                    f"Manual intervention required for file (filename inconsistencies): {media_file_path}"
                )
                self.manual_review_files.append(media_file_path)
                self.results['manual'] += 1
                continue

            groups.setdefault(file_base_name, []).append(media_file_path)

        media_files_count = len(media_files)
        medias = {}
        index = 0
        for file_base_name, paths in groups.items():
            if len(paths) > 1:
                for path in paths:
                    self.logger.error(
                        f"Manual intervention required for file (duplicate filename base): {path}"
                    )
                    self.excluded.append(path)
                    self.manual_review_files.append(path)
                self.results['manual'] += len(paths)
                continue

            index += 1
            self.logger.debug(f"Pre-processing media file {index} / {media_files_count}: {paths[0]}")
            media = self._init_media_file(media_file_path=paths[0])
            if media is None:
                self.logger.error(f"Unable to initialize media file: {paths[0]}")
                self.invalid_files.append(paths[0])
                self.results['invalid'] += 1
                continue
            medias[file_base_name] = media

        return dict(sorted(medias.items()))

    def _get_new_fileinfo(self, media: TruImage | TruVideo):
        _ext_lower = media.ext.lower()
        _year = media.date_taken.strftime("%Y")
        _month = media.date_taken.strftime("%b")
        _dir = self.dest_dir
        if self.sub_dirs:
            _dir += f"/{_year}/{_month}"

        _filename = f"{media.date_taken.strftime(DATE_FORMATS.get('filename'))}"
        _new_file_info = {
            'dir': _dir,
            'filename': _filename,
            'ext': media.preferred_ext,
        }
        new_file_path = self._file_path(_new_file_info)

        if not os.path.isdir(_dir):
            self.logger.debug(f"Destination path does not exist, creating: {_dir}")
            if not self.dry_run:
                os.makedirs(_dir)
        if not os.path.exists(new_file_path):
            return _new_file_info

        self.logger.debug(f"Destination file already exists: {new_file_path}")
        media2 = self._init_media_file(media_file_path=new_file_path)
        if media2 and media2.valid and media.hash == media2.hash:
            self.logger.debug(f"[DUPLICATE] Destination file matches source file: {new_file_path}")
            _new_file_info['duplicate'] = True
            return _new_file_info
        # increment 1 second and try again
        media.date_taken = media.date_taken + timedelta(seconds=1)
        return self._get_new_fileinfo(media)

    def _simulate_copy(self, media: TruImage | TruVideo, dest_info: dict) -> dict:
        """
        Return the source -> destination mapping `media.copy()` would produce,
        without touching the filesystem. Used for dry-run mode.
        """
        dest_dir = dest_info.get("dir")
        filename = dest_info.get("filename")
        ext = dest_info.get("ext") or media.preferred_ext
        files: dict[str, str] = {media.media_path: f"{dest_dir}/{filename}{ext}"}
        if media.json_file_path:
            suffix = ext if media.media_type == "image" else ""
            files[media.json_file_path] = f"{dest_dir}/{filename}{suffix}.json"
        animation = getattr(media, "animation", None)
        if animation:
            files[animation] = f"{dest_dir}/{filename}{FILE_EXTS.get('video_preferred')}"
        return files

    def run(self):
        if self.dry_run:
            self.logger.info("DRY RUN: no files will be copied, deleted, or DB records inserted")
        cleanup_files = []
        medias = self._get_medias(self.source_dir)
        media_count = len(medias)
        for index, media in enumerate(medias.values(), 1):
            media_file = media.media_path
            if not media.valid:
                self.logger.error(f"Invalid media: {media_file}")
                self.invalid_files.append(media_file)
                self.results['invalid'] += 1
                continue
            self.logger.info(
                f"Processing file {index} / {media_count}:\n\t{media_file}"
            )
            if rec := self._check_db_for_media_path_hash(media):
                self.logger.debug(f"[DUPLICATE] Hash for {media_file} already in db: {rec}")
                self.results['duplicate'] += 1
                cleanup_files += media.files.values()
                continue

            if media.date_taken is not None:
                # Apply offset if configured
                media.date_taken = self._apply_offset(media.date_taken)
                new_file_info = self._get_new_fileinfo(media)
                if not new_file_info.get('duplicate'):
                    try:
                        if self.dry_run:
                            copied = self._simulate_copy(media, new_file_info)
                            for source, dest in copied.items():
                                self.logger.info(f"[DRY RUN] Would copy:\n\t{source}\n\t-> {dest}")
                        else:
                            copied = media.copy(new_file_info)
                        cleanup_files += copied.keys()
                        self.results['moved'] += len(copied)
                        if not self.dry_run:
                            # add dest media path and hash to db
                            self._insert_media_hash(copied[media.media_path])
                    except shutil.Error as exc:
                        self.failed_files.append(media_file)
                        self.results['failed'] += 1
                        self.logger.error(f"Failed to move file: {media_file}\n{exc}")
                else:
                    new_file_path = self._file_path(new_file_info)
                    self.logger.debug(f"[DUPLICATE] File already exists: {media_file} -> {new_file_path}")
                    self.results['duplicate'] += 1
                    if not self.dry_run:
                        self._insert_media_hash(new_file_path)
                    self.logger.info(f"File already moved: {media_file} -> {new_file_path}")
                    cleanup_files += media.files.values()
            else:
                self.logger.error(f"Unable to determine date taken for file: {media_file}")
                self.failed_files.append(media_file)
                self.results['failed'] += 1

        if cleanup_files and self.cleanup:
            for cleanup_file in list(set(cleanup_files)):
                if cleanup_file:
                    self.results['deleted'] += 1
                    if self.dry_run:
                        self.logger.info(f"[DRY RUN] Would delete file: {cleanup_file}")
                    else:
                        self.logger.info(f"Deleting file: {cleanup_file}")
                        os.remove(cleanup_file)
        return self.results
