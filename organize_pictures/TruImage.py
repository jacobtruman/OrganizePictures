from datetime import datetime
import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET

from dict2xml import dict2xml
from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError
import ffmpeg
import magic
from PIL import Image
from pillow_heif import register_heif_opener
import xmltodict

from organize_pictures.utils import get_logger, MEDIA_TYPES, EXIF_DATE_FIELDS, DATE_FORMATS, FILE_EXTS

register_heif_opener()


# pylint: disable=too-many-instance-attributes
class TruImage:

    def __init__(self, image_path, logger=None, verbose=False):
        self.verbose = verbose
        self.dev_mode = False
        self._logger = None
        self.logger = logger
        self._image_path = None
        self.image_path = image_path
        self._ext = None
        self._json_file_path = None
        self._json_data = None
        self._exif_data = None
        self._date_taken = None
        self._hash = None
        self._animation = None
        self.regenerated = False
        self.valid = self.ext.lower() in MEDIA_TYPES.get('image')
        if self.valid:
            self._reconcile_mime_type()
        if self.valid:
            self._write_json_data_to_image()

    @property
    def image_path(self):
        return self._image_path

    @image_path.setter
    def image_path(self, value):
        if not os.path.isfile(value):
            self.logger.error(f"Image not found: {value}")
            raise FileNotFoundError(f"Image not found: {value}")
        self._image_path = value

    @property
    def logger(self):
        if self._logger is None:
            self._logger = get_logger()
        return self._logger

    @logger.setter
    def logger(self, value):
        if value is None:
            self._logger = get_logger()
        self._logger = value

    @property
    def hash(self):
        if self._hash is None:
            self._get_image_hash()
        return self._hash

    @property
    def ext(self):
        if self._ext is None:
            _, ext = os.path.splitext(os.path.basename(self.image_path))
            self._ext = ext
        return self._ext

    @ext.setter
    def ext(self, value):
        self._ext = value

    @property
    def files(self):
        """
        Get associated files
        :return:
        """
        return {
            "image": self.image_path,
            "json": self.json_file_path,
            "animation": self.animation
        }

    @property
    def exif_data(self):
        if self._exif_data is None:
            with ExifToolHelper() as eth:
                self._exif_data = (eth.get_metadata(self.image_path) or [])[0]
        return self._exif_data

    @property
    def json_file_path(self):
        if self._json_file_path is None:
            if "(" in self.image_path and ")" in self.image_path:
                start = self.image_path.find("(")
                end = self.image_path.find(")")
                base_file = self.image_path[:start]
                file_num = self.image_path[start + 1:end]
                _file = f"{base_file}{self.ext}({file_num})"
            json_file = f"{self.image_path}.json"
            self._json_file_path = json_file if os.path.isfile(json_file) else None
        return self._json_file_path

    @json_file_path.setter
    def json_file_path(self, value):
        if not os.path.isfile(value):
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
    def animation(self):
        if self._animation is None:
            self._animation = self._find_image_animation()
        return self._animation

    @property
    def date_taken(self):
        # pylint: disable=too-many-nested-blocks
        if self._date_taken is None:
            try:
                for exif_date_field in EXIF_DATE_FIELDS:
                    _date_field = f"EXIF:{exif_date_field}"
                    if _date_field in self.exif_data:
                        self.logger.info(f"Using date field: {_date_field}")
                        for date_format in DATE_FORMATS.values():
                            try:
                                self._date_taken = datetime.strptime(self.exif_data.get(_date_field), date_format)
                                break
                            except Exception as exc:
                                self.logger.error(
                                    f"Unable to convert date field using format {date_format}: {_date_field}\n{exc}"
                                )
                        break
                if self._date_taken is None and "PNG:XMLcommagicmemoriesm4" in self.exif_data:
                    tree = ET.fromstring(self.exif_data.get("PNG:XMLcommagicmemoriesm4"))
                    if tree.attrib.get("creation") is not None:
                        self.logger.info("Using m4 creation date")
                        self._date_taken = datetime.strptime(tree.attrib.get("creation"), DATE_FORMATS.get("m4"))
            except Exception as exc:
                self.logger.error(f'Unable to get exif data for file: {self.image_path}:\n{exc}')

            if self._date_taken is None:
                self.logger.error(f"Unable to determine date taken for {self.image_path}")

            # if self.offset != self.init_offset():
            #     # update date object with offset
            #     multiplier = 1
            #     if self.minus:
            #         multiplier = -1
            #     date_time_obj = datetime(
            #         year=(date_time_obj.year + (self.offset.get("Y") * multiplier)),
            #         month=(date_time_obj.month + (self.offset.get("M") * multiplier)),
            #         day=(date_time_obj.day + (self.offset.get("D") * multiplier)),
            #         hour=(date_time_obj.hour + (self.offset.get("h") * multiplier)),
            #         minute=(date_time_obj.minute + (self.offset.get("m") * multiplier)),
            #         second=(date_time_obj.second + (self.offset.get("s") * multiplier)),
            #     )

        return self._date_taken

    @date_taken.setter
    def date_taken(self, value: datetime):
        self._date_taken = value
        self.logger.info(f"Setting date taken to {value}")
        _date = value.strftime(DATE_FORMATS.get("default"))
        self._update_tags(self.image_path, {field: _date for field in EXIF_DATE_FIELDS})

    def _regenerate(self):
        """
        Regenerate image
        :return:
        """
        try:
            self.logger.warning(f"Regenerating image: {self.image_path}")
            # get exif data
            exif_data = self.exif_data
            # regenerate image
            Image.open(self.image_path).save(self.image_path)
            # update exif data
            self.logger.debug("Image regenerated; trying to rewrite exif data")
            tags = {tag: value for tag, value in exif_data.items() if tag.startswith("EXIF:")}
            self._update_tags(self.image_path, tags)
            self.logger.info(f"Successfully regenerated image: {self.image_path}")
            self.regenerated = True
            return True
        except Exception as exc:
            self.logger.error(f"Failed to regenerate image: {self.image_path}\n{exc}")
            return False

    def _reconcile_mime_type(self):
        mime_guess = mimetypes.guess_type(self.image_path)[0]
        mime_actual = magic.from_file(self.image_path, mime=True)
        print(f"{self.image_path}\nGuess: {mime_guess}\nActual: {mime_actual}")
        # exit()

        if not mime_actual.startswith("image/"):
            if self._regenerate():
                mime_actual = magic.from_file(self.image_path, mime=True)

        if not mime_actual.startswith("image/"):
            self.valid = False
        elif mime_guess != mime_actual:
            file_updates = {}
            _mt = mimetypes.MimeTypes()
            new_ext = _mt.types_map_inv[1].get(mime_actual)[0]
            new_path = self.image_path.replace(self.ext, new_ext)
            self.ext = new_ext
            file_updates["image_path"] = new_path
            self.logger.error(f"Mimetype does not match filetype: {mime_guess} != {mime_actual}")

            if self.json_file_path and os.path.isfile(self.json_file_path):
                new_json_file = f"{new_path}.json"
                file_updates["json_file_path"] = new_json_file

            for key, value in file_updates.items():
                source = getattr(self, key)
                if self.dev_mode:
                    self.logger.info(f"Would update {key} '{source}' to '{value}'")
                    shutil.copy(source, value)
                else:
                    self.logger.info(f"Updating {key} '{source}' to '{value}'")
                    shutil.move(source, value)
                    setattr(self, key, value)

    def _convert_video(self, _file: str, _new_file: str):
        converted = False
        if os.path.isfile(_new_file):
            self.logger.info(f"Skipping conversion of \"{_file}\" to \"{_new_file}\" as it already exists")
            converted = True
        else:
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
                self.logger.info(f"Successfully converted \"{_file}\" to \"{_new_file}\"")
                converted = True
            else:
                self.logger.error(f"Failed to convert \"{_file}\" to \"{_new_file}\"")
        return converted

    def _find_image_animation(self):
        image_animation = None
        for ext in MEDIA_TYPES.get('video'):
            _file = self.image_path.replace(self.ext, ext)
            _file_upper = _file.replace(self.ext, ext.upper())
            if os.path.isfile(_file):
                image_animation = _file
            elif os.path.isfile(_file_upper):
                # rename file ext to lowercase
                shutil.move(_file_upper, _file)
                image_animation = _file

        if image_animation:
            # convert video to preferred format
            _, ext = os.path.splitext(os.path.basename(image_animation))
            if ext is not FILE_EXTS.get('video_preferred'):
                _new_file = image_animation.replace(ext, FILE_EXTS.get('video_preferred'))
                if self._convert_video(image_animation, _new_file):
                    image_animation = _new_file

        return image_animation

    def _get_image_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                self.logger.debug(f"Getting hash for {self.image_path}")
                temp_file = f"{temp_dir}/{os.path.basename(self.image_path)}"
                image = Image.open(self.image_path)
                image.save(temp_file)
                image.close()
                image = Image.open(temp_file)
                image_hash = hashlib.md5(image.tobytes()).hexdigest()
                image.close()
                self._hash = image_hash
            except Exception:  # pylint: disable=broad-except
                self.logger.error(f"Error opening image: {self.image_path}")
                self._hash = None

    def _update_tags(self, image_path, tags):
        try:
            del_tags = []
            for _field, _value in tags.items():
                if isinstance(_value, str):
                    _value = _value.encode('ascii', 'ignore').decode('ascii')
                    tags[_field] = _value
                exif_field = f"EXIF:{_field}"
                if exif_field in self.exif_data and self.exif_data.get(exif_field) == _value:
                    del_tags.append(_field)
            for _tag in del_tags:
                del tags[_tag]
            if tags:
                self.logger.debug(f"Updating tags for {image_path}\n{tags}")
                with ExifToolHelper() as _eth:
                    _eth.set_tags(
                        [image_path],
                        tags=tags,
                        params=["-P", "-overwrite_original"]
                    )
        except ExifToolExecuteError as exc:
            self.logger.error(f"Failed to update tags for {image_path}:\n{exc}")
            if self._regenerate():
                self._update_tags(image_path, tags)
            else:
                self.valid = False

    # pylint: disable=too-many-branches
    def _write_json_data_to_image(self, image_path=None):
        if image_path is None:
            image_path = self.image_path
        if self.json_data:
            tags = {}
            if "photoTakenTime" in self.json_data:
                _date = datetime.fromtimestamp(
                    int(self.json_data.get("photoTakenTime").get("timestamp"))
                ).strftime(DATE_FORMATS.get("default"))
                for field in EXIF_DATE_FIELDS:
                    tags[field] = _date
            if "people" in self.json_data:
                user_comment = None
                people_dict = {
                    "People": {"Person": [person.get("name") for person in self.json_data.get("people")]}
                }
                if "EXIF:UserComment" in self.exif_data:
                    user_comment = self.exif_data.get("EXIF:UserComment")
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
                    tags["GPSAltitude"] = alt
                    # GPSAltitudeRef (0 for above sea level, 1 for below sea level)
                    tags["GPSAltitudeRef"] = 0 if alt > 0 else 1

                self._update_tags(image_path, tags)

    def convert(self, dest_ext: str):
        dest_file = self.image_path.replace(self.ext, dest_ext)
        self.logger.debug(f"Converting file:\n\tSource: {self.image_path}\n\tDestination: {dest_file}")
        method = "pillow"
        try:
            image = Image.open(self.image_path)
            image.convert('RGB').save(dest_file)
            image.close()
            self._write_json_data_to_image(dest_file)
        except Exception as exc:
            self.logger.error(f"Failed second conversion attempt via {method}: {self.image_path}\n{exc}")
            return False
        self.logger.debug(
            f"Successfully converted file via {method}:\n\tSource: {self.image_path}\n\tDestination: {dest_file}"
        )
        return True

    def copy(self, dest_info: dict):
        """
        Copy image to destination path
        :param dest_info: dict of destination path information
            path: destination path
            filename: destination filename without extension
        :return: dict of files copied
        """
        files_to_copy = {}
        dest_dir = dest_info.get("dir")
        filename = dest_info.get("filename")
        if not os.path.isdir(dest_dir):
            self.logger.warning(f"Destination directory not found: {dest_dir}")
            os.makedirs(dest_dir)

        dest_file = f"{dest_dir}/{filename}{self.ext}"
        if not os.path.isfile(dest_file):
            files_to_copy[self.image_path] = dest_file
            if self.json_file_path:
                dest_file = f"{dest_dir}/{filename}.json"
                if not os.path.isfile(dest_file):
                    files_to_copy[self.json_file_path] = dest_file
                else:
                    self.logger.warning(f"Destination json file already exists: {dest_file}")

            if self.animation:
                dest_file = f"{dest_dir}/{filename}{FILE_EXTS.get('video_preferred')}"
                if not os.path.isfile(dest_file):
                    files_to_copy[self.animation] = dest_file
                else:
                    self.logger.warning(f"Destination animation file already exists: {dest_file}")

            for source, dest in files_to_copy.items():
                self.logger.info(f"Copying file:\n\tSource: {source}\n\tDestination: {dest}")
                shutil.copy(source, dest)
                self.logger.debug("Successfully copied file")
        else:
            self.logger.warning(f"Destination file already exists: {dest_file}")

        return files_to_copy
