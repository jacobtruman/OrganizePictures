import atexit
import json
import os
from datetime import datetime, timedelta
import hashlib
import shutil
import tempfile
from glob import glob

import sqlite3
from exiftool import ExifToolHelper
from pymediainfo import MediaInfo
import ffmpeg
from PIL import Image
from pillow_heif import register_heif_opener
import xmltodict
from dict2xml import dict2xml

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

        self.results = {"moved": 0, "duplicate": 0, "failed": 0, "deleted": 0}

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

    def _get_image_hash(self, image_path):
        if image_path == self.current_image and self.current_hash is not None:
            return self.current_hash
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                self.logger.debug(f"Getting hash for {image_path}")
                temp_file = f"{temp_dir}/{os.path.basename(image_path)}"
                image = Image.open(image_path)
                image.save(temp_file)
                image.close()
                image = Image.open(temp_file)
                image_hash = hashlib.md5(image.tobytes()).hexdigest()
                image.close()
                return image_hash
            except Exception:  # pylint: disable=broad-except
                self.logger.error(f"Error opening image: {image_path}")
                return None

    def _check_db_for_image_path(self, image_path):
        sql = f'SELECT * FROM image_hashes WHERE image_path = "{image_path}"'
        return self.dbc.execute(sql).fetchall()

    def _check_db_for_image_hash(self, image_hash):
        sql = f'SELECT * FROM image_hashes WHERE hash = "{image_hash}"'
        return self.dbc.execute(sql).fetchall()

    def _check_db_for_image_path_hash(self, image):
        return self._check_db_for_image_hash(image.hash)

    def _insert_image_hash(self, image_path: str):
        if not os.path.isfile(image_path):
            self.logger.error(f"Image path does not exist: {image_path}")
            return False
        image_hash = self._get_image_hash(image_path)
        if image_hash is not None:
            sql = f'INSERT INTO image_hashes VALUES ("{image_path}","{image_hash}")'
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

    # pylint: disable=too-many-branches
    def _write_json_data_to_image(self, _file, _json_file=None):
        if _json_file is None:
            _json_file = self._get_json_file(_file)
        if os.path.isfile(_json_file):
            with ExifToolHelper() as eth:
                metadata = (eth.get_metadata(_file) or [])[0]
            data = self._load_json_file(_json_file)
            if data is not None:
                tags = {}
                if "photoTakenTime" in data:
                    _date = datetime.fromtimestamp(
                        int(data.get("photoTakenTime").get("timestamp"))
                    ).strftime(DATE_FORMATS.get("default"))
                    for field in EXIF_DATE_FIELDS:
                        tags[field] = _date
                if "people" in data:
                    user_comment = None
                    people_dict = {"People": {"Person": [person.get("name") for person in data.get("people")]}}
                    if "EXIF:UserComment" in metadata:
                        user_comment = metadata.get("EXIF:UserComment")
                    if user_comment:
                        try:
                            data_dict = xmltodict.parse(user_comment)
                        except Exception:
                            # if we can't parse the user comment, add existing comment as a note
                            data_dict = {"UserComment": {"note": user_comment}}
                        # make sure UserComment is at the root level
                        if "UserComment" not in data_dict:
                            data_dict["UserComment"] = data_dict
                        # if people_comment is not in user_comment, add people_dict
                        if dict2xml(people_dict, newlines=False) not in user_comment:
                            data_dict["UserComment"].update(people_dict)
                    else:
                        data_dict = {"UserComment": people_dict}

                    # convert user comment to xml and add to tags
                    if "UserComment" in data_dict:
                        tags["UserComment"] = dict2xml(data_dict, newlines=False)
                if "geoDataExif" in data:
                    lat = data.get("geoDataExif").get("latitude")
                    lon = data.get("geoDataExif").get("longitude")
                    alt = data.get("geoDataExif").get("altitude")
                    if lat != 0 and lon != 0:
                        # GPSLatitudeRef (S for negative, N for positive)
                        if lat > 0:
                            tags["GPSLatitude"] = lat
                            tags["GPSLatitudeRef"] = "N"
                        else:
                            tags["GPSLatitude"] = -lat
                            tags["GPSLatitudeRef"] = "S"
                        # GPSLongitudeRef (W for negative, E for positive)
                        if lon > 0:
                            tags["GPSLongitude"] = lon
                            tags["GPSLongitudeRef"] = "E"
                        else:
                            tags["GPSLongitude"] = -lon
                            tags["GPSLongitudeRef"] = "W"
                        tags["GPSAltitude"] = alt
                        # GPSAltitudeRef (0 for above sea level, 1 for below sea level)
                        tags["GPSAltitudeRef"] = 0 if alt > 0 else 1

                    self._update_tags(_file, tags, metadata)

    def _get_files(self, path: str):
        files = []
        paths = glob(f"{path}/*")
        for file in paths:
            if os.path.isfile(file):
                ext = self._get_file_ext(file)
                ext_lower = ext.lower()
                if ext_lower in self.extensions:
                    add = True
                    if self.media_type is not None and ext_lower not in MEDIA_TYPES.get(self.media_type):
                        add = False
                    if add:
                        files.append(file)
            elif os.path.isdir(file):
                files += self._get_files(file)
        return sorted(files)

    def _convert_video(self, _file: str, _new_file: str):
        converted = False
        if os.path.isfile(_new_file):
            self.logger.info(f"Skipping conversion of \"{_file}\" to \"{_new_file}\" as it already exists")
            converted = True
        self.logger.info(f"Converting \"{_file}\" to \"{_new_file}\"")
        stream = ffmpeg.input(_file)
        stream = ffmpeg.output(
            stream,
            _new_file,
            acodec="aac",
            vcodec="h264",
            map_metadata=0,
            metadata=f"comment=Converted {_file} to {_new_file}",
            loglevel="verbose" if self.verbose else "quiet"
        )
        _, err = ffmpeg.run(stream)
        if err is None:
            self.results['moved'] += 1
            self.logger.info(f"Successfully converted \"{_file}\" to \"{_new_file}\"")
            converted = True
        else:
            self.logger.error(f"Failed to convert \"{_file}\" to \"{_new_file}\"")
        return converted

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
        image2 = TruImage(new_file_path, self.logger)
        if image2.valid and image.hash == image2.hash:
            _new_file_info['duplicate'] = True
            return _new_file_info
        # increment 1 second and try again
        image.date_taken = image.date_taken + timedelta(seconds=1)
        return self._get_new_fileinfo(image)

    def run(self):
        cleanup_files = []
        files = self._get_files(self.source_dir)
        for index, media_file in enumerate(files, start=1):
            image = TruImage(media_file, self.logger)
            if image.valid:
                self.logger.info(
                    f"Processing file {index} / {len(files)}:\n\t{media_file}"
                )
                if self._check_db_for_image_path_hash(image):
                    self.logger.debug(f"Hash for {media_file} already in db")
                    self.results['duplicate'] += 1
                    cleanup_files += image.files.values()
                    continue

                if image.date_taken is not None:
                    new_file_info = self._get_new_fileinfo(image)
                    if not new_file_info.get('duplicate'):
                        try:
                            if image.ext.lower() in FILE_EXTS.get('image_convert'):
                                image.convert(FILE_EXTS.get('image_preferred'))
                            copied = image.copy(new_file_info)
                            cleanup_files += copied.keys()
                            self.results['moved'] += len(copied)
                            # add to db
                            self._insert_image_hash(copied.image_path)
                        except shutil.Error as exc:
                            self.results['failed'] += 1
                            self.logger.error(f"Failed to move file: {media_file}\n{exc}")
                    else:
                        self.results['duplicate'] += 1
                        self._insert_image_hash(self._file_path(new_file_info))
                        # file is already moved
                        self.logger.info(f"File already moved: {media_file} -> {new_file_info.get('path')}")
                        cleanup_files += image.files.values()
            else:
                print("Not a valid image file - maybe video?")
                # TODO: video object processing
                # if new_file_info['ext'] in MEDIA_TYPES.get('video'):
                #     if self._convert_video(media_file, new_file_info['path']):
                #         cleanup_files.append(media_file)

        if cleanup_files and self.cleanup:
            for cleanup_file in cleanup_files:
                if cleanup_file:
                    self.results['deleted'] += 1
                    self.logger.info(f"Deleting file: {cleanup_file}")
                    os.remove(cleanup_file)

        return self.results
