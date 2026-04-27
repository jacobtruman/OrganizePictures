import logging
import mimetypes
import shutil
from abc import abstractmethod, ABC
from datetime import datetime
import json
import os
import pathlib
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

import ffmpeg
import magic
from exiftool import ExifToolHelper
from pillow_heif import register_heif_opener
from dict2xml import dict2xml
import xmltodict

from organize_pictures.utils import get_logger, EXIF_DATE_FIELDS, DATE_FORMATS, VIDEO_DATE_FIELDS, MEDIA_TYPES

register_heif_opener()


# pylint: disable=too-many-instance-attributes
class TruMedia(ABC):

    def __init__(
            self,
            media_path: str,
            json_file_path: str | None = None,
            logger: logging.Logger | None = None,
            verbose: bool = False,
            dry_run: bool = False
    ):
        self.verbose: bool = verbose
        self.dry_run: bool = dry_run
        self.dev_mode: bool = False
        self.regenerated = False
        self.overwrite_comment = False
        self._logger: logging.Logger | None = None
        self.logger: logging.Logger | None = logger
        self._media_path: str | None = None
        self.media_path: str = media_path
        self.media_path_source: str | None = None
        self._json_file_path: str | None = None
        self.json_file_path: str | None = json_file_path
        self._ext: str | None = None
        self._json_data: dict | None = None
        self._exif_data: dict | None = None
        self._date_taken = None
        self._hash = None
        self._media_type = None
        self._valid: bool = True
        if not self.dry_run and self.ext.lower() != self.preferred_ext:
            self.convert()

    @abstractmethod
    def media_type(self):
        self.logger.info(f"This method should be overridden in a subclass")

    @abstractmethod
    def date_fields(self) -> list:
        self.logger.info(f"This method should be overridden in a subclass")

    @abstractmethod
    def preferred_ext(self):
        self.logger.info(f"This method should be overridden in a subclass")

    @abstractmethod
    def convert(self, dest_ext: str | None = None):
        self.logger.info(f"This method should be overridden in a subclass")

    @property
    def valid(self):
        """
        Common getter for valid property - returns the internal _valid state
        Subclasses should implement their own setters with media-specific validation logic
        """
        return self._valid

    @property
    def media_path(self):
        return self._media_path

    @media_path.setter
    def media_path(self, value):
        if not os.path.isfile(value):
            self.logger.error(f"Media not found: {value}")
            raise FileNotFoundError(f"Media not found: {value}")
        self._media_path = value

    @property
    def json_file_path(self):
        if self._json_file_path is None:
            self._json_file_path = self._find_json_sidecar(self.media_path)
        return self._json_file_path

    @staticmethod
    def _find_json_sidecar(media_path: str) -> str | None:
        """
        Locate the Google-Takeout JSON sidecar for ``media_path``.

        Handles three sidecar conventions:
          - ``<media>.json``                          (IMG_1234.jpg.json)
          - ``<media without ext>.json``              (IMG_1234.json)
          - ``<media>.supplemental-metadata.json``    (newer Takeout exports)

        Takeout caps sidecar filenames at 51 chars total, so when the
        ``.supplemental-metadata.json`` form would overflow, Takeout truncates
        the literal suffix from the right (``.supplemental-metadat.json``,
        ``.supplemental-metada.json`` ... ``.s.json``). We match any non-empty
        prefix of ``supplemental-metadata`` for that reason. We also try the
        ext-stripped form with the same suffix.
        """
        stem, _ = os.path.splitext(media_path)
        suffix = "supplemental-metadata"
        bases = (media_path, stem)
        candidates: list[str] = []
        for base in bases:
            candidates.append(f"{base}.json")
        for base in bases:
            for length in range(len(suffix), 0, -1):
                candidates.append(f"{base}.{suffix[:length]}.json")
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None

    @json_file_path.setter
    def json_file_path(self, value):
        if value and not os.path.isfile(value):
            self.logger.error(f"JSON file not found: {value}")
            raise FileNotFoundError(f"JSON file not found: {value}")
        self._json_file_path = value

    @property
    def json_data(self):
        if self._json_data is None and self.json_file_path:
            with open(self.json_file_path, "r", encoding="utf-8") as file_handle:
                self._json_data = json.load(file_handle)
        return self._json_data

    @property
    def logger(self) -> logging.Logger:
        if self._logger is None:
            self._logger = get_logger()
        return self._logger

    @logger.setter
    def logger(self, value: logging.Logger | None):
        self._logger = get_logger() if value is None else value

    @property
    def hash(self):
        if self._hash is None:
            self._get_media_hash()
        return self._hash

    @property
    def ext(self):
        if self._ext is None:
            ext = pathlib.Path(self.media_path).suffix
            self._ext = ext
        return self._ext

    @ext.setter
    def ext(self, value):
        self._ext = value

    @property
    def exif_data(self):
        if self._exif_data is None:
            with ExifToolHelper() as eth:
                self._exif_data = (eth.get_metadata(self.media_path) or [])[0]
        return self._exif_data

    @property
    def date_taken(self):
        # pylint: disable=too-many-nested-blocks
        if self._date_taken is None:
            # First priority: Try to get date from JSON file
            if self.json_data and "photoTakenTime" in self.json_data:
                try:
                    timestamp = int(self.json_data.get("photoTakenTime").get("timestamp"))
                    self._date_taken = datetime.fromtimestamp(timestamp)
                    self.logger.info(f"Using date from JSON photoTakenTime: {self._date_taken}")
                except (AttributeError, TypeError, ValueError, OSError) as exc:
                    self.logger.error(f"Unable to get date from JSON photoTakenTime:\n{exc}")

            # Second priority: Try to get date from file metadata
            if self._date_taken is None:
                try:
                    for exif_date_field in self.date_fields:
                        _date_field = self._date_field(exif_date_field)
                        if _date_field in self.exif_data:
                            self.logger.info(f"Using date field: {_date_field}")
                            for date_format in DATE_FORMATS.values():
                                try:
                                    self._date_taken = datetime.strptime(self.exif_data.get(_date_field), date_format)
                                    break
                                except (TypeError, ValueError) as exc:
                                    self.logger.debug(
                                        f"Date field did not match format {date_format}: {_date_field}\n{exc}"
                                    )
                    if self._date_taken is None and "PNG:XMLcommagicmemoriesm4" in self.exif_data:
                        try:
                            tree = ET.fromstring(self.exif_data.get("PNG:XMLcommagicmemoriesm4"))
                            if tree.attrib.get("creation") is not None:
                                self.logger.info("Using m4 creation date")
                                self._date_taken = datetime.strptime(tree.attrib.get("creation"), DATE_FORMATS.get("m4"))
                        except (ET.ParseError, TypeError, ValueError, AttributeError) as exc:
                            self.logger.error(f"Unable to get m4 creation date:\n{exc}")
                except (KeyError, AttributeError, TypeError) as exc:
                    self.logger.error(f'Unable to get exif data for file: {self.media_path}:\n{exc}')

            # Third priority: Try to parse date from filename
            if self._date_taken is None:
                try:
                    filename = os.path.basename(self.media_path)
                    # Remove extension
                    filename_no_ext = os.path.splitext(filename)[0]
                    # Try each date format to parse the filename
                    for format_name, date_format in DATE_FORMATS.items():
                        try:
                            self._date_taken = datetime.strptime(filename_no_ext, date_format)
                            self.logger.info(f"Using date from filename with format '{format_name}': {self._date_taken}")
                            # Write the parsed date back to the file metadata
                            _date = self._date_taken.strftime(DATE_FORMATS.get("default"))
                            tags = {}
                            for field in self.date_fields:
                                # Use the field name as-is for videos (they already have prefixes)
                                # For images, use the field name without prefix (TruImage._date_field will add EXIF:)
                                if self.media_type == "video":
                                    # Videos: use the full field name (e.g., "QuickTime:CreateDate")
                                    tags[field] = _date
                                else:
                                    # Images: use just the field name (e.g., "DateTimeOriginal")
                                    # TruImage._date_field will add "EXIF:" prefix when needed
                                    field_name = field.split(':')[-1] if ':' in field else field
                                    tags[field_name] = _date
                            self._update_tags(self.media_path, tags)
                            break
                        except ValueError:
                            # This format didn't match, try the next one
                            continue
                except (OSError, ValueError, TypeError) as exc:
                    self.logger.error(f"Unable to parse date from filename: {exc}")

            if self._date_taken is None:
                self.logger.error(f"Unable to determine date taken for {self.media_path}")

        return self._date_taken

    @date_taken.setter
    def date_taken(self, value: datetime):
        self._date_taken = value
        self.logger.info(f"Setting date taken to {value}")
        _date = value.strftime(DATE_FORMATS.get("default"))
        # Use the appropriate date fields for the media type
        tags = {}
        for field in self.date_fields:
            # Use the field name as-is for videos (they already have prefixes)
            # For images, use the field name without prefix (TruImage._date_field will add EXIF:)
            if self.media_type == "video":
                # Videos: use the full field name (e.g., "QuickTime:CreateDate")
                tags[field] = _date
            else:
                # Images: use just the field name (e.g., "DateTimeOriginal")
                # TruImage._date_field will add "EXIF:" prefix when needed
                field_name = field.split(':')[-1] if ':' in field else field
                tags[field_name] = _date
        self._update_tags(self.media_path, tags)

    def _date_field(self, date_field: str):
        return date_field

    def _get_media_hash(self):
        self.logger.info(f"This method should be overridden in a subclass")

    def _reconcile_mime_type(self):
        """
        Reconcile mime type with file extension (common implementation)
        """
        mime_guess = mimetypes.guess_type(self.media_path)[0]
        mime_actual = magic.from_file(self.media_path, mime=True)

        if mime_actual == "inode/x-empty":
            self._valid = False
        elif mime_guess != mime_actual:
            file_updates = {}
            _mt = mimetypes.MimeTypes()
            new_ext = _mt.types_map_inv[1].get(mime_actual)[0]
            new_path = self.media_path.replace(self.ext, new_ext)
            self.ext = new_ext
            file_updates["media_path"] = new_path
            self.logger.error(f"Mimetype does not match filetype: {mime_guess} != {mime_actual}")

            if self.json_file_path and os.path.isfile(self.json_file_path):
                new_json_file = f"{new_path}.json"
                file_updates["json_file_path"] = new_json_file

            for key, value in file_updates.items():
                source = getattr(self, key)
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would update {key} '{source}' to '{value}'")
                    continue
                if self.dev_mode:
                    self.logger.info(f"Would update {key} '{source}' to '{value}' (dev_mode: copying)")
                    shutil.copy(source, value)
                else:
                    self.logger.info(f"Updating {key} '{source}' to '{value}'")
                    shutil.move(source, value)
                    setattr(self, key, value)

    def _write_json_data_to_media(self, media_path=None):
        """
        Write JSON data to media metadata (common implementation for images and videos)
        """
        if media_path is None:
            media_path = self.media_path
        if self.json_data:
            tags = {}

            # Handle photoTakenTime
            if "photoTakenTime" in self.json_data:
                _date = datetime.fromtimestamp(
                    int(self.json_data.get("photoTakenTime").get("timestamp"))
                ).strftime(DATE_FORMATS.get("default"))
                for field in self.date_fields:
                    # Use the field name as-is for videos (they already have prefixes)
                    # For images, use the field name without prefix (TruImage._date_field will add EXIF:)
                    if self.media_type == "video":
                        # Videos: use the full field name (e.g., "QuickTime:CreateDate")
                        tags[field] = _date
                    else:
                        # Images: use just the field name (e.g., "DateTimeOriginal")
                        # TruImage._date_field will add "EXIF:" prefix when needed
                        field_name = field.split(':')[-1] if ':' in field else field
                        tags[field_name] = _date

            # Handle people data
            if "people" in self.json_data:
                people_dict = {
                    "People": {"Person": [person.get("name") for person in self.json_data.get("people")]}
                }

                # For images, handle existing UserComment data more carefully
                if hasattr(self, 'exif_data') and hasattr(self, 'overwrite_comment'):
                    user_comment = None
                    if "EXIF:UserComment" in self.exif_data:
                        user_comment = self.exif_data.get("EXIF:UserComment")
                    if not self.overwrite_comment and user_comment:
                        try:
                            data_dict = xmltodict.parse(user_comment)
                        except ExpatError:
                            if "METADATA-START" in user_comment:
                                data_dict = {"UserComment": {}}
                            else:
                                data_dict = {"UserComment": {"note": user_comment}}

                        # make sure UserComment is at the root level
                        if "UserComment" not in data_dict:
                            data_dict = {"UserComment": data_dict}
                        # if people_comment is not in user_comment, add people_dict
                        if dict2xml(people_dict, newlines=False) not in user_comment:
                            data_dict["UserComment"].update(people_dict)
                    else:
                        data_dict = {"UserComment": people_dict}
                else:
                    # For videos or simpler handling
                    data_dict = {"UserComment": people_dict}

                # convert user comment to xml and add to tags
                if "UserComment" in data_dict:
                    tags["UserComment"] = dict2xml(data_dict.get("UserComment"), newlines=False)

            # Handle GPS data
            if "geoDataExif" in self.json_data:
                lat = self.json_data.get("geoDataExif").get("latitude")
                lon = self.json_data.get("geoDataExif").get("longitude")
                alt = self.json_data.get("geoDataExif").get("altitude")
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
                    if alt != 0:
                        tags["GPSAltitude"] = alt
                        # GPSAltitudeRef (0 for above sea level, 1 for below sea level)
                        tags["GPSAltitudeRef"] = 0 if alt > 0 else 1

            if tags:
                self.logger.info(f"Writing JSON data to media metadata: {media_path}")
                self._update_tags(media_path, tags)

    def _update_tags(self, media_path: str, tags: dict):
        del_tags = []
        for _field, _value in tags.items():
            if isinstance(_value, str):
                _value = _value.encode('ascii', 'ignore').decode('ascii')
                tags[_field] = _value
            # Compare against the appropriate prefixed field (EXIF:, QuickTime:, etc.).
            # Also fall back to scanning all known prefixes so video tags don't
            # always re-write on every run.
            full_field = self._date_field(_field) if ':' not in _field else _field
            existing_value = self.exif_data.get(full_field)
            if existing_value is None:
                # Search any prefix (e.g. for tags _date_field doesn't know about).
                for exif_key, exif_val in self.exif_data.items():
                    if exif_key.split(':')[-1] == _field:
                        existing_value = exif_val
                        break
            if existing_value == _value:
                del_tags.append(_field)
        for _tag in del_tags:
            del tags[_tag]
        if tags:
            if self.dry_run:
                self.logger.debug(f"[DRY RUN] Would update tags for {media_path}\n\t{tags}")
                return
            self.logger.debug(f"Updating tags for {media_path}\n\t{tags}")
            with ExifToolHelper() as _eth:
                if self.verbose:
                    for tag, val in tags.items():
                        self.logger.debug(f"Tag [{tag}]: {val}")
                        if tag == "UserComment":
                            val = val.replace(
                                val[val.find("METADATA-START"):val.find("METADATA-END") + len("METADATA-END")], ""
                            )
                        _eth.set_tags(
                            [media_path],
                            tags={tag: val},
                            params=["-m", "-u", "-U", "-P", "-overwrite_original"]
                        )
                else:
                    _eth.set_tags(
                        [media_path],
                        tags=tags,
                        params=["-m", "-u", "-U", "-P", "-overwrite_original"]
                    )
        # reset exif data
        self._exif_data = None

    def _convert_video(self, _file: str, _new_file: str):
        if os.path.isfile(_new_file):
            self.logger.info(f"Skipping conversion of \"{_file}\" to \"{_new_file}\" as it already exists")
            return False
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
        if err:
            self.logger.error(f"Failed to convert \"{_file}\" to \"{_new_file}\"")
            return False
        self.logger.info(f"Successfully converted \"{_file}\" to \"{_new_file}\"")
        return True

    def _add_json_file_to_copy(self, files_to_copy: dict, dest_dir: str, filename: str, ext_suffix=""):
        """
        Helper method to add JSON file to copy operations
        :param files_to_copy: dict to add file mappings to
        :param dest_dir: destination directory
        :param filename: base filename without extension
        :param ext_suffix: optional extension suffix (e.g., ".jpg" for images)
        """
        if self.json_file_path and os.path.isfile(self.json_file_path):
            dest_json_file = f"{dest_dir}/{filename}{ext_suffix}.json"
            if not os.path.isfile(dest_json_file):
                files_to_copy[self.json_file_path] = dest_json_file
            else:
                self.logger.warning(f"Destination JSON file already exists: {dest_json_file}")

    def copy(self, dest_info: dict):
        """
        Copy image to destination path
        :param dest_info: dict of destination path information
            path: destination path
            filename: destination filename without extension
        :return: dict of files copied
        """
        dest_dir = dest_info.get("dir")
        if not os.path.isdir(dest_dir):
            self.logger.warning(f"Destination directory not found: {dest_dir}")
            os.makedirs(dest_dir)