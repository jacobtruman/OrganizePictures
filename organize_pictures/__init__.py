import json
import os
from datetime import datetime, timedelta
import hashlib
import shutil
from logging import Logger
from glob import glob
import time

import pytz
import sqlite3
from exiftool import ExifToolHelper
from pymediainfo import MediaInfo
import ffmpeg
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener
import xml.etree.ElementTree as ET
import xmltodict
import tempfile
from dict2xml import dict2xml

import atexit

register_heif_opener()

MEDIA_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.heic'],
    'video': ['.mp4', '.mpg', '.mov', '.m4v', '.mts', '.mkv'],
}
OFFSET_CHARS = 'YMDhms'


class OrganizePictures:
    FILENAME_DATE_FORMAT = "%Y-%m-%d_%H'%M'%S"
    ENCODED_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    M4_DATE_FORMAT = '%Y/%m/%d %H:%M:%S,%f'
    VIDEO_DATE_FORMATS = {
        "default": "%Y-%m-%d %H:%M:%S %Z",
        # ".mkv": "%Y-%m-%dT%H:%M:%SZ %Z",
    }
    IMG_CONVERT_EXTS = ['.heic']
    IMG_CHANGE_EXTS = ['.jpeg']
    VID_CONVERT_EXTS = ['.mpg', '.mov', '.m4v', '.mts', '.mkv']
    PREFERRED_IMAGE_EXT = '.jpg'
    PREFERRED_VIDEO_EXT = '.mp4'
    EXIF_DATE_FIELDS = ['DateTimeOriginal', 'CreateDate']

    # pylint: disable=too-many-arguments
    def __init__(
            self,
            logger: Logger,
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
        self.logger = logger
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

    def _check_db_for_image_path_hash(self, image_path):
        return self._check_db_for_image_hash(self._get_image_hash(image_path))

    def _insert_image_hash(self, image_path):
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
                    ).strftime(self.ENCODED_DATE_FORMAT)
                    for field in self.EXIF_DATE_FIELDS:
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

    def _get_date_taken(self, _file: str) -> datetime:
        date_time_obj = None
        ext = self._get_file_ext(_file).lower()
        if ext in MEDIA_TYPES.get('video'):
            media_info = MediaInfo.parse(_file)
            for track in media_info.tracks:
                if track.track_type in ['Video', 'General']:
                    if track.encoded_date is not None:
                        date_time_obj = datetime.strptime(
                            track.encoded_date, self.VIDEO_DATE_FORMATS.get(
                                ext,
                                self.VIDEO_DATE_FORMATS.get("default")
                            )
                        )
                        print(track.encoded_date, date_time_obj)
                        _fromtz = pytz.timezone(track.encoded_date.split(" ")[-1])
                        _totz = pytz.timezone('US/Mountain')
                        date_time_obj = datetime.astimezone(date_time_obj.replace(tzinfo=_fromtz), _totz)
                        break
                    if track.recorded_date is not None:
                        date_time_obj = datetime.strptime(track.recorded_date, "%Y-%m-%d %H:%M:%S%z")
                        break
        elif ext in MEDIA_TYPES.get('image'):
            self._write_json_data_to_image(_file)
            try:
                with ExifToolHelper() as eth:
                    metadata = (eth.get_metadata(_file) or [])[0]
                    for exif_date_field in self.EXIF_DATE_FIELDS:
                        _date_field = f"EXIF:{exif_date_field}"
                        if _date_field in metadata:
                            self.logger.info(f"Using date field: {_date_field}")
                            date_time_obj = datetime.strptime(
                                metadata.get(_date_field), self.ENCODED_DATE_FORMAT
                            )
                            break
                    if date_time_obj is None and "PNG:XMLcommagicmemoriesm4" in metadata:
                        tree = ET.fromstring(metadata.get("PNG:XMLcommagicmemoriesm4"))
                        if tree.attrib.get("creation") is not None:
                            self.logger.info("Using m4 creation date")
                            date_time_obj = datetime.strptime(tree.attrib.get("creation"), self.M4_DATE_FORMAT)
            except Exception as exc:
                self.logger.error(f'Unable to get exif data for file: {_file}:\n{exc}')

        # if other dates are not found, use the file modified date
        if date_time_obj is None:
            self.logger.info("Using file modified date as date taken")
            date_time_obj = datetime.strptime(time.ctime(os.path.getmtime(_file)), '%c')

        if self.offset != self.init_offset():
            # update date object with offset
            multiplier = 1
            if self.minus:
                multiplier = -1
            date_time_obj = datetime(
                year=(date_time_obj.year + (self.offset.get("Y") * multiplier)),
                month=(date_time_obj.month + (self.offset.get("M") * multiplier)),
                day=(date_time_obj.day + (self.offset.get("D") * multiplier)),
                hour=(date_time_obj.hour + (self.offset.get("h") * multiplier)),
                minute=(date_time_obj.minute + (self.offset.get("m") * multiplier)),
                second=(date_time_obj.second + (self.offset.get("s") * multiplier)),
            )

        return date_time_obj

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

    def _convert_image(self, source_file: str, dest_file: str):
        self.logger.debug(f"Converting file:\n\tSource: {source_file}\n\tDestination: {dest_file}")
        method = "pillow"
        try:
            image = Image.open(source_file)
            image.convert('RGB').save(dest_file)
            self._write_json_data_to_image(dest_file, self._get_json_file(source_file))
        except Exception as exc:
            self.logger.error(f"Failed second conversion attempt via {method}: {source_file}\n{exc}")
            return False
        self.results['moved'] += 1
        self.logger.debug(
            f"Successfully converted file via {method}:\n\tSource: {source_file}\n\tDestination: {dest_file}"
        )
        return True

    def _media_file_matches(self, source_file: str, dest_file: str):
        matches = False
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
                    self.logger.debug(f"Checking if video file has already been converted")
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
            new_date = _date.strftime(self.ENCODED_DATE_FORMAT)
            image = Image.open(_file)

            with ExifToolHelper() as eth:
                metadata = (eth.get_metadata(_file) or [])[0]
                if self.EXIF_DATE_FIELDS[0] not in metadata or metadata.get(self.EXIF_DATE_FIELDS[0]) != new_date:
                    eth.set_tags(
                        [_file],
                        tags={field: _date for field in self.EXIF_DATE_FIELDS},
                        params=["-P", "-overwrite_original"]
                    )
                else:
                    self.logger.debug(f"Exif date already matches for {_file}")
        except Exception as exc:
            self.logger.error(f"Failed to update file date for {_file}: {exc}")

    def _get_new_fileinfo(self, _file: str, _date: datetime):
        _ext = self._get_file_ext(_file)
        _ext_lower = _ext.lower()
        _year = _date.strftime("%Y")
        _month = _date.strftime("%b")
        _dir = self.dest_dir
        if self.sub_dirs:
            _dir += f"/{_year}/{_month}"

        _filename = f"{_date.strftime(self.FILENAME_DATE_FORMAT)}{_ext_lower}"
        _new_file_info = {
            'ext': _ext_lower,
            'dir': _dir,
            'filename': _filename,
            'path': f"{_dir}/{_filename}",
            'date_encoded': _date
        }
        json_file = self._get_json_file(_file)
        if os.path.isfile(json_file):
            _new_file_info['json_file'] = json_file
            _new_file_info['new_json_file'] = f"{_dir}/{self._get_json_file(_filename)}"

        image_animation = self._find_image_animation(_file, _ext)
        if self.media_type == 'image' and image_animation is not None:
            _new_file_info['animation_source'] = image_animation
            _new_file_info['animation_dest'] = f"{_dir}/{_filename.replace(_ext_lower, self.PREFERRED_VIDEO_EXT)}"

        if _ext_lower in self.IMG_CONVERT_EXTS:
            _new_file_info['convert_path'] = f"{_dir}/{_filename.replace(_ext_lower, self.PREFERRED_IMAGE_EXT)}"
        if _ext_lower in self.VID_CONVERT_EXTS:
            _new_file_info['path'] = f"{_dir}/{_filename.replace(_ext_lower, self.PREFERRED_VIDEO_EXT)}"
        if _ext_lower in self.IMG_CHANGE_EXTS:
            _new_file_info['path'] = f"{_dir}/{_filename.replace(_ext_lower, self.PREFERRED_IMAGE_EXT)}"

        if not os.path.isdir(_new_file_info['dir']):
            self.logger.debug(f"Destination path does not exist, creating: {_new_file_info['dir']}")
            os.makedirs(_new_file_info['dir'])
        if not os.path.exists(_new_file_info['path']):
            return _new_file_info

        self.logger.debug(f"Destination file already exists: {_new_file_info['path']}")
        if self._media_file_matches(_file, _new_file_info['path']):
            _new_file_info['duplicate'] = True
            return _new_file_info
        else:
            # increment 1 second and try again
            new_dt = _date + timedelta(seconds=1)
            return self._get_new_fileinfo(_file, new_dt)

    def run(self):
        files = self._get_files(self.source_dir)
        for index, media_file in enumerate(files, start=1):
            self.current_image = media_file
            self.logger.info(
                f"Processing file {index} / {len(files)}:\n\t{media_file}"
            )
            cleanup_files = []
            if self._check_db_for_image_path_hash(media_file):
                self.logger.debug(f"{media_file} Already in db")
                cleanup_files.append(media_file)
                continue
            date_taken = self._get_date_taken(media_file)
            if date_taken is not None:
                new_file_info = self._get_new_fileinfo(media_file, date_taken)
                if not new_file_info.get('duplicate'):
                    if new_file_info['ext'] in MEDIA_TYPES.get('video'):
                        if self._convert_video(media_file, new_file_info['path']):
                            cleanup_files.append(media_file)
                    else:
                        try:
                            self.logger.info(
                                f"Moving file:\n\tSource: {media_file}\n\tDestination: {new_file_info['path']}"
                            )
                            if new_file_info.get('convert_path') is not None:
                                if not self._convert_image(media_file, new_file_info['convert_path']):
                                    self.logger.error(f"Failed to convert image: {media_file}")
                                    continue
                            shutil.copyfile(media_file, new_file_info['path'])
                            # update file date of new file
                            self._update_file_date(new_file_info['path'], new_file_info['date_encoded'])
                            self.results['moved'] += 1
                            cleanup_files.append(media_file)
                            if "animation_source" in new_file_info:
                                if self._media_file_matches(
                                        new_file_info['animation_source'],
                                        new_file_info['animation_dest']
                                ) or self._convert_video(
                                        new_file_info['animation_source'],
                                        new_file_info['animation_dest']
                                ):
                                    cleanup_files.append(new_file_info['animation_source'])
                            # add to db
                            self._insert_image_hash(media_file)
                        except shutil.Error as exc:
                            self.results['failed'] += 1
                            self.logger.error(f"Failed to move file: {media_file}\n{exc}")

                    if new_file_info.get('json_file') is not None:
                        self.logger.info(
                            f"Moving file:\n\tSource: {new_file_info.get('json_file')}\n\t"
                            f"Destination: {new_file_info.get('new_json_file')}")
                        shutil.copyfile(new_file_info['json_file'], new_file_info['new_json_file'])
                        self.results['moved'] += 1
                        cleanup_files.append(new_file_info['json_file'])
                else:
                    # file is already moved
                    self.logger.info(f"File already moved: {media_file} -> {new_file_info.get('path')}")
                    cleanup_files.append(media_file)
                    if new_file_info.get('json_file'):
                        cleanup_files.append(new_file_info.get('json_file'))
                    if new_file_info.get('animation_source'):
                        cleanup_files.append(new_file_info.get('animation_source'))

            if cleanup_files and self.cleanup:
                for cleanup_file in cleanup_files:
                    self.results['deleted'] += 1
                    self.logger.info(f"Deleting file: {cleanup_file}")
                    os.remove(cleanup_file)

        return self.results
