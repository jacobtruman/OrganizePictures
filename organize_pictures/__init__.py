import atexit
import os
from datetime import timedelta
import hashlib
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
    EXIF_DATE_FIELDS,
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
        create = False
        if not os.path.isfile(db_file):
            create = True

        self.db_conn = sqlite3.connect(db_file)
        self.dbc = self.db_conn.cursor()

        if create:
            # Create table
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

    @staticmethod
    def _file_path(file_info):
        """
        File path for the given file info
        :param file_info: Dict of file info containing dir and filename
        :return:
        """
        return f"{file_info.get('dir')}/{file_info.get('filename')}{file_info.get('ext')}"

    def _check_db_for_media_path(self, media_path):
        sql = f'SELECT * FROM image_hashes WHERE image_path = "{media_path}"'
        return dict(self.dbc.execute(sql).fetchall())

    def _check_db_for_media_hash(self, media_hash):
        sql = f'SELECT * FROM image_hashes WHERE hash = "{media_hash}"'
        return dict(self.dbc.execute(sql).fetchall())

    def _check_db_for_media_path_hash(self, media):
        return self._check_db_for_media_hash(media.hash)

    def _insert_media_hash(self, media_path: str):
        if not os.path.isfile(media_path):
            self.logger.error(f"Media path does not exist: {media_path}")
            return False
        media = self._init_media_file(media_file_path=media_path)
        if media.hash:
            sql = f'INSERT INTO image_hashes VALUES ("{media_path}","{media.hash}")'
            self.dbc.execute(sql)
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
        Get all files in the given path matching the given pattern and extensions
        :param base_dir: Base directory to search
        :param extensions: Extensions to search for
        :param recursive:
        :return:
        """
        if extensions is None:
            extensions = self.extensions
        return [
            os.path.abspath(_file) for _file in sorted(glob(f"{base_dir}/**/*", recursive=recursive))
            if pathlib.Path(_file).suffix.lower() in extensions
        ]

    def _init_media_file(self, media_file_path: str):
        for media_type in MEDIA_TYPES:
            if pathlib.Path(media_file_path).suffix.lower() in MEDIA_TYPES.get(media_type):
                match media_type:
                    case 'image':
                        return TruImage(media_path=media_file_path, logger=self.logger)
                    case 'video':
                        return TruVideo(media_path=media_file_path, logger=self.logger)
        return None

    def _get_medias(self, base_dir: str):
        """
        Get objects for media in the given path. Check json files first for metadata to get matching media files,
        since they don't always match.
        :param base_dir: Path to search for media files
        :return:
        """
        medias = {}
        # then process media files
        self.logger.debug(f"Pre-processing media files in {base_dir}")
        media_files = self._get_file_paths(base_dir=base_dir)
        media_files_count = len(media_files)
        for index, media_file_path in enumerate(media_files, 1):
            file_base_name = pathlib.Path(media_file_path).stem

            if "(" in file_base_name or ")" in file_base_name or len(os.path.basename(media_file_path)) >= 146:
                # manual intervention required
                self.logger.error(
                    f"Manual intervention required for file (filename inconsistencies): {media_file_path}"
                )
                self.results['manual'] += 1
                continue
            self.logger.debug(f"Pre-processing media file {index} / {media_files_count}: {media_file_path}")
            # skip files found in json files
            if file_base_name not in medias and file_base_name not in self.excluded:
                medias[file_base_name] = self._init_media_file(media_file_path=media_file_path)
            else:
                self.logger.error(f"Manual intervention required for file (duplicate filename base): {media_file_path}")
                del medias[file_base_name]
                self.excluded.append(file_base_name)
                self.results['manual'] += 1
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
            os.makedirs(_dir)
        if not os.path.exists(new_file_path):
            return _new_file_info

        self.logger.debug(f"Destination file already exists: {new_file_path}")
        media2 = self._init_media_file(media_file_path=new_file_path)
        if media2.valid and media.hash == media2.hash:
            self.logger.debug(f"[DUPLICATE] Destination file matches source file: {new_file_path}")
            _new_file_info['duplicate'] = True
            return _new_file_info
        # increment 1 second and try again
        media.date_taken = media.date_taken + timedelta(seconds=1)
        return self._get_new_fileinfo(media)

    def run(self):
        cleanup_files = []
        medias = self._get_medias(self.source_dir)
        media_count = len(medias)
        for index, media in enumerate(medias.values(), 1):
            media_file = media.media_path
            if not media.valid:
                self.logger.error(f"Invalid media: {media_file}")
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
                new_file_info = self._get_new_fileinfo(media)
                if not new_file_info.get('duplicate'):
                    try:
                        copied = media.copy(new_file_info)
                        cleanup_files += copied.keys()
                        self.results['moved'] += len(copied)
                        # add dest media path and hash to db
                        self._insert_media_hash(copied[media.media_path])
                    except shutil.Error as exc:
                        self.results['failed'] += 1
                        self.logger.error(f"Failed to move file: {media_file}\n{exc}")
                else:
                    self.logger.debug(f"[DUPLICATE] File already exists: {media_file} -> {new_file_info.get('path')}")
                    self.results['duplicate'] += 1
                    self._insert_media_hash(self._file_path(new_file_info))
                    # file is already moved
                    self.logger.info(f"File already moved: {media_file} -> {new_file_info.get('path')}")
                    cleanup_files += media.files.values()

        if cleanup_files and self.cleanup:
            for cleanup_file in list(set(cleanup_files)):
                if cleanup_file:
                    self.results['deleted'] += 1
                    self.logger.info(f"Deleting file: {cleanup_file}")
                    os.remove(cleanup_file)
        return self.results
