from datetime import datetime
import hashlib
import mimetypes
import os
import pathlib
import shutil
import tempfile

from dict2xml import dict2xml
from exiftool.exceptions import ExifToolExecuteError
import magic
from PIL import Image
from pillow_heif import register_heif_opener
import xmltodict

from organize_pictures.utils import MEDIA_TYPES, EXIF_DATE_FIELDS, DATE_FORMATS, FILE_EXTS
from organize_pictures.TruMedia import TruMedia

register_heif_opener()


# pylint: disable=too-many-instance-attributes
class TruImage(TruMedia):

    def __init__(self, media_path, json_file_path=None, logger=None, verbose=False):
        super().__init__(media_path=media_path, json_file_path=json_file_path, logger=logger, verbose=verbose)
        self.dev_mode = False
        self._json_data = None
        self._animation = None

    @property
    def valid(self):
        return self._valid

    @valid.setter
    def valid(self, _):
        self._valid = self.ext.lower() in MEDIA_TYPES.get('image')
        if self.valid:
            self._reconcile_mime_type()
        if self.valid:
            self._write_json_data_to_media()

    @property
    def media_type(self):
        if self._media_type is None:
            self._media_type = "image"
        return self._media_type

    @property
    def date_fields(self) -> list:
        return EXIF_DATE_FIELDS

    @property
    def files(self):
        """
        Get associated files
        :return:
        """
        return {
            "image": self.media_path,
            "json": self.json_file_path,
            "animation": self.animation
        }

    @property
    def animation(self):
        if self._animation is None:
            self._animation = self._find_image_animation()
        return self._animation

    def _date_field(self, date_field: str):
        return f"EXIF:{date_field}"

    def _regenerate(self):
        """
        Regenerate image
        :return:
        """
        try:
            self.logger.warning(f"Regenerating image: {self.media_path}")
            # get exif data
            exif_data = self.exif_data
            # regenerate image
            Image.open(self.media_path).save(self.media_path)
            self.regenerated = True
            # update exif data
            self.logger.debug("Image regenerated; trying to rewrite exif data")
            tags = {tag.replace("EXIF:", ""): value for tag, value in exif_data.items() if tag.startswith("EXIF:")}
            self._update_tags(media_path=self.media_path, tags=tags)
            self.logger.info(f"Successfully regenerated image: {self.media_path}")
            return True
        except Exception as exc:
            self.logger.error(f"Failed to regenerate image: {self.media_path}\n{exc}")
            return False

    def _reconcile_mime_type(self):
        mime_guess = mimetypes.guess_type(self.media_path)[0]
        mime_actual = magic.from_file(self.media_path, mime=True)

        if not mime_actual.startswith("image/"):
            if self._regenerate():
                mime_actual = magic.from_file(self.media_path, mime=True)

        if not mime_actual.startswith("image/"):
            self.valid = False
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
                if self.dev_mode:
                    self.logger.info(f"Would update {key} '{source}' to '{value}'")
                    shutil.copy(source, value)
                else:
                    self.logger.info(f"Updating {key} '{source}' to '{value}'")
                    shutil.move(source, value)
                    setattr(self, key, value)

    def _find_image_animation(self):
        image_animation = None
        for ext in MEDIA_TYPES.get('video'):
            _file = self.media_path.replace(self.ext, ext)
            _file_upper = _file.replace(ext, ext.upper())
            if os.path.isfile(_file):
                image_animation = _file
            elif os.path.isfile(_file_upper):
                # rename file ext to lowercase
                shutil.move(_file_upper, _file)
                image_animation = _file

        if image_animation:
            # convert video to preferred format
            ext = pathlib.Path(image_animation).suffix
            if ext is not FILE_EXTS.get('video_preferred'):
                _new_file = image_animation.replace(ext, FILE_EXTS.get('video_preferred'))
                if self._convert_video(image_animation, _new_file):
                    image_animation = _new_file

        return image_animation

    def _get_media_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                self.logger.debug(f"Getting hash for {self.media_path}")
                temp_file = f"{temp_dir}/{os.path.basename(self.media_path)}"
                image = Image.open(self.media_path)
                image.save(temp_file)
                image.close()
                image = Image.open(temp_file)
                media_hash = hashlib.md5(image.tobytes()).hexdigest()
                image.close()
                self._hash = media_hash
            except Exception:  # pylint: disable=broad-except
                self.logger.error(f"Error opening image: {self.media_path}")
                self._hash = None

    # pylint: disable=too-many-branches
    def _write_json_data_to_media(self, media_path=None):
        if media_path is None:
            media_path = self.media_path
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

                # convert user comment to xml and add to tags
                if "UserComment" in data_dict:
                    tags["UserComment"] = dict2xml(data_dict.get("UserComment"), newlines=False)
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
            if tags:
                self._update_tags(media_path, tags)

    def _update_tags(self, media_path: str, tags: dict):
        try:
            super()._update_tags(media_path, tags)
        except ExifToolExecuteError as exc:
            self.logger.error(f"Failed to update tags for {media_path}:\n{exc}")
            if not self.regenerated:
                if self._regenerate():
                    self._update_tags(media_path, tags)
            else:
                self.valid = False

    def convert(self, dest_ext: str):
        dest_file = self.media_path.replace(self.ext, dest_ext)
        if os.path.isfile(dest_file):
            self.logger.error(f"Not converting {self.media_path} to {dest_ext} as it already exists")
            return False
        self.logger.debug(f"Converting file:\n\tSource: {self.media_path}\n\tDestination: {dest_file}")
        method = "pillow"
        try:
            image = Image.open(self.media_path)
            image.convert('RGB').save(dest_file)
            image.close()
            # update image path
            self.media_path = dest_file
            self.ext = dest_ext
            self._write_json_data_to_media()
        except Exception as exc:
            self.logger.error(f"Failed second conversion attempt via {method}: {self.media_path}\n{exc}")
            return False
        self.logger.debug(
            f"Successfully converted file via {method}:\n\tSource: {self.media_path}\n\tDestination: {dest_file}"
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
        super().copy(dest_info)
        files_to_copy = {}
        dest_dir = dest_info.get("dir")
        filename = dest_info.get("filename")
        ext_lower = self.ext.lower()

        if ext_lower in FILE_EXTS.get('image_convert'):
            # add the pre-converted file to be copied
            files_to_copy[self.media_path] = f"{dest_dir}/{filename}{ext_lower}"
            self.convert(FILE_EXTS.get('image_preferred'))
            ext_lower = self.ext.lower()
        elif ext_lower in FILE_EXTS.get('image_change'):
            ext_lower = FILE_EXTS.get('image_preferred')

        dest_file = f"{dest_dir}/{filename}{ext_lower}"
        if not os.path.isfile(dest_file):
            files_to_copy[self.media_path] = dest_file
            if self.json_file_path:
                dest_file = f"{dest_dir}/{filename}{ext_lower}.json"
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
