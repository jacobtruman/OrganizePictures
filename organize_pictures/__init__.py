import atexit
import json
import os
from datetime import datetime, timedelta
import hashlib
import pathlib
import shutil
from glob import glob

import sqlite3
from exiftool import ExifToolHelper
from pymediainfo import MediaInfo
from PIL import Image
from pillow_heif import register_heif_opener

from organize_pictures.TruImage import TruImage
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
        self.minus = minus
        self.verbose = verbose

        self.results = {"moved": 0, "duplicate": 0, "failed": 0, "invalid": 0, "deleted": 0}

        self.extensions = extensions
        if self.extensions is None:
            if media_type is not None:
                self.extensions = MEDIA_TYPES.get(media_type)
            else:
                self.extensions = []
                for exts in MEDIA_TYPES.values():
                    self.extensions += exts

        self.current_hash = None
        self.current_image = None
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
        self.logger.debug("EXIT: Committing final records")
        self.db_conn.commit()
        self.db_conn.close()

    @staticmethod
    def _get_file_ext(file):
        _, ext = os.path.splitext(os.path.basename(file))
        return ext

    @staticmethod
    def init_offset():
        return dict.fromkeys(list(OFFSET_CHARS), 0)

    def _get_json_file(self, _file):
        """Get the json file name for the given file"""
        if "(" in _file and ")" in _file:
            ext = self._get_file_ext(_file)
            start = _file.find("(")
            end = _file.find(")")
            base_file = _file[:start]
            file_num = _file[start + 1:end]
            _file = f"{base_file}{ext}({file_num})"
        return f"{_file}.json"

    @staticmethod
    def _load_json_file(json_file: str):
        parsed_json = None
        if os.path.isfile(json_file):
            with open(json_file, encoding="utf-8") as user_file:
                parsed_json = json.load(user_file)
        return parsed_json

    @staticmethod
    def _find_image_animation(_file: str, _ext: str):
        for ext in MEDIA_TYPES.get('video'):
            image_animation = _file.replace(_ext, ext)
            if os.path.isfile(image_animation):
                return image_animation
            image_animation = _file.replace(_ext, ext.upper())
            if os.path.isfile(image_animation):
                return image_animation
        return None

    @staticmethod
    def _md5(fname):
        hash_md5 = hashlib.md5()
        with open(fname, "rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    @staticmethod
    def _file_path(file_info):
        """
        File path for the given file info
        :param file_info: Dict of file info containing dir and filename
        :return:
        """
        return f"{file_info.get('dir')}/{file_info.get('filename')}{FILE_EXTS.get('image_preferred')}"

    def _check_db_for_image_path(self, image_path):
        sql = f'SELECT * FROM image_hashes WHERE image_path = "{image_path}"'
        return dict(self.dbc.execute(sql).fetchall())

    def _check_db_for_image_hash(self, image_hash):
        sql = f'SELECT * FROM image_hashes WHERE hash = "{image_hash}"'
        return dict(self.dbc.execute(sql).fetchall())

    def _check_db_for_image_path_hash(self, image):
        return self._check_db_for_image_hash(image.hash)

    def _insert_image_hash(self, image_path: str):
        if not os.path.isfile(image_path):
            self.logger.error(f"Image path does not exist: {image_path}")
            return False
        image = TruImage(image_path=image_path, logger=self.logger)
        if image.hash:
            sql = f'INSERT INTO image_hashes VALUES ("{image_path}","{image.hash}")'
            self.dbc.execute(sql)
            self.current_hash = None
            return True
        return False

    def _update_tags(self, _file, _tags, _metadata):
        del_tags = []
        for _field, _value in _tags.items():
            if isinstance(_value, str):
                _value = _value.encode('ascii', 'ignore').decode('ascii')
                _tags[_field] = _value
            exif_field = f"EXIF:{_field}"
            if exif_field in _metadata and _metadata.get(exif_field) == _value:
                del_tags.append(_field)
        for _tag in del_tags:
            del _tags[_tag]
        if _tags:
            self.logger.debug(f"Updating tags for {_file}\n{_tags}")
            with ExifToolHelper() as _eth:
                _eth.set_tags(
                    [_file],
                    tags=_tags,
                    params=["-P", "-overwrite_original"]
                )

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

    def _get_images(self, path: str):
        """
        Get image objects for images in the given path. Check json files first for metadata to get matching image files,
        since they don't always match.
        :param path: Path to search for media files
        :return:
        """
        images = {}
        # then process image files
        self.logger.debug(f"Pre-processing image files in {path}")
        media_files = self._get_file_paths(base_dir=path)
        media_files_count = len(media_files)
        for index, media_file_path in enumerate(media_files, 1):
            file_base_name = pathlib.Path(media_file_path).stem
            if "(" in file_base_name or ")" in file_base_name or len(os.path.basename(media_file_path)) >= 46:
                # manual intervention required
                self.logger.error(
                    f"Manual intervention required for file (filename inconsistencies): {media_file_path}"
                )
                continue
            self.logger.debug(f"Pre-processing media file {index} / {media_files_count}: {media_file_path}")
            # skip files found in json files
            if file_base_name not in images:
                images[file_base_name] = TruImage(image_path=media_file_path, logger=self.logger)
            else:
                self.logger.error(f"Manual intervention required for file (duplicate filename base): {media_file_path}")
                del images[file_base_name]
        return dict(sorted(images.items()))

    def _media_file_matches(self, source_file: str, dest_file: str):
        matches = False
        # pylint: disable=too-many-nested-blocks
        # assume source file exists, ensure dest file exists
        if os.path.isfile(dest_file):
            if self._md5(source_file) == self._md5(dest_file):
                self.results['duplicate'] += 1
                matches = True
                self.logger.debug(f"""Source file matches existing destination file:
                            Source: {source_file}
                            Destination: {dest_file}""")
            else:
                self.logger.debug(f"""Source file does not match existing destination file:
                            Source: {source_file}
                            Destination: {dest_file}""")
                source_file_ext = self._get_file_ext(source_file).lower()
                if source_file_ext in MEDIA_TYPES.get('video'):
                    self.logger.debug("Checking if video file has already been converted")
                    _media_info = MediaInfo.parse(dest_file)
                    for _track in _media_info.tracks:
                        if hasattr(_track, 'comment') and _track.comment is not None:
                            if "Converted" in _track.comment:
                                self.results['duplicate'] += 1
                                self.logger.info(f"Video file already converted: {source_file}")
                                self.logger.debug(f"\t{_track.comment}")
                                matches = True
                                break
        return matches

    def _update_file_date(self, _file, _date: datetime):
        try:
            new_date = _date.strftime(DATE_FORMATS.get("default"))
            image = Image.open(_file)

            with ExifToolHelper() as eth:
                metadata = (eth.get_metadata(_file) or [])[0]
                if EXIF_DATE_FIELDS[0] not in metadata or metadata.get(EXIF_DATE_FIELDS[0]) != new_date:
                    eth.set_tags(
                        [_file],
                        tags={field: _date for field in EXIF_DATE_FIELDS},
                        params=["-P", "-overwrite_original"]
                    )
                else:
                    self.logger.debug(f"Exif date already matches for {_file}")
        except Exception as exc:
            self.logger.error(f"Failed to update file date for {_file}: {exc}")

    def _get_new_fileinfo(self, image: TruImage):
        _ext_lower = image.ext.lower()
        _year = image.date_taken.strftime("%Y")
        _month = image.date_taken.strftime("%b")
        _dir = self.dest_dir
        if self.sub_dirs:
            _dir += f"/{_year}/{_month}"

        _filename = f"{image.date_taken.strftime(DATE_FORMATS.get('filename'))}"
        _new_file_info = {
            'dir': _dir,
            'filename': _filename,
        }
        new_file_path = self._file_path(_new_file_info)

        if not os.path.isdir(_dir):
            self.logger.debug(f"Destination path does not exist, creating: {_dir}")
            os.makedirs(_dir)
        if not os.path.exists(new_file_path):
            return _new_file_info

        self.logger.debug(f"Destination file already exists: {new_file_path}")
        image2 = TruImage(image_path=new_file_path, logger=self.logger)
        if image2.valid and image.hash == image2.hash:
            self.logger.debug(f"[DUPLICATE] Destination file matches source file: {new_file_path}")
            _new_file_info['duplicate'] = True
            return _new_file_info
        # increment 1 second and try again
        image.date_taken = image.date_taken + timedelta(seconds=1)
        return self._get_new_fileinfo(image)

    def run(self):
        cleanup_files = []
        images = self._get_images(self.source_dir)
        image_count = len(images)
        for index, image in enumerate(images.values(), 1):
            media_file = image.image_path
            if not image.valid:
                self.logger.error(f"Invalid image: {media_file}")
                self.results['invalid'] += 1
                continue
            self.logger.info(
                f"Processing file {index} / {image_count}:\n\t{media_file}"
            )
            if rec := self._check_db_for_image_path_hash(image):
                self.logger.debug(f"[DUPLICATE] Hash for {media_file} already in db: {rec}")
                self.results['duplicate'] += 1
                cleanup_files += image.files.values()
                continue

            if image.date_taken is not None:
                new_file_info = self._get_new_fileinfo(image)
                if not new_file_info.get('duplicate'):
                    try:
                        copied = image.copy(new_file_info)
                        cleanup_files += copied.keys()
                        self.results['moved'] += len(copied)
                        # add dest image path and hash to db
                        self._insert_image_hash(copied[image.image_path])
                    except shutil.Error as exc:
                        self.results['failed'] += 1
                        self.logger.error(f"Failed to move file: {media_file}\n{exc}")
                else:
                    self.logger.debug(f"[DUPLICATE] File already exists: {media_file} -> {new_file_info.get('path')}")
                    self.results['duplicate'] += 1
                    self._insert_image_hash(self._file_path(new_file_info))
                    # file is already moved
                    self.logger.info(f"File already moved: {media_file} -> {new_file_info.get('path')}")
                    cleanup_files += image.files.values()

            # TODO: video object processing
            # if new_file_info['ext'] in MEDIA_TYPES.get('video'):
            #     if self._convert_video(media_file, new_file_info['path']):
            #         cleanup_files.append(media_file)

        if cleanup_files and self.cleanup:
            for cleanup_file in list(set(cleanup_files)):
                if cleanup_file:
                    self.results['deleted'] += 1
                    self.logger.info(f"Deleting file: {cleanup_file}")
                    os.remove(cleanup_file)

        return self.results
