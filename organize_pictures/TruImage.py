import logging
import hashlib
import os
import pathlib
import shutil
import tempfile

from exiftool.exceptions import ExifToolExecuteError
from PIL import Image
from pillow_heif import register_heif_opener

from organize_pictures.utils import MEDIA_TYPES, EXIF_DATE_FIELDS, FILE_EXTS
from organize_pictures.TruMedia import TruMedia

register_heif_opener()


# pylint: disable=too-many-instance-attributes
class TruImage(TruMedia):

    def __init__(
            self,
            media_path: str,
            json_file_path: str = None,
            logger: logging.Logger = None,
            verbose: bool = False
    ):
        super().__init__(media_path=media_path, json_file_path=json_file_path, logger=logger, verbose=verbose)
        self.dev_mode = False
        self._animation = None
        self.valid = None

    @TruMedia.valid.setter
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
        """Override parent method to handle image-specific regeneration logic"""
        import magic

        mime_actual = magic.from_file(self.media_path, mime=True)

        if not mime_actual.startswith("image/"):
            if self._regenerate():
                mime_actual = magic.from_file(self.media_path, mime=True)

        if not mime_actual.startswith("image/"):
            self.valid = False
        else:
            # Use parent class for common mime type reconciliation
            super()._reconcile_mime_type()

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

    def open(self):
        try:
            image = Image.open(self.media_path)
            return image
        except Exception as exc:
            self.logger.error(f"Failed to open image: {self.media_path}\n{exc}")

    def show(self):
        try:
            image = self.open()
            image.show()
            image.close()
        except Exception as exc:
            self.logger.error(f"Failed to show image: {self.media_path}\n{exc}")

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

            # Use parent class helper to handle JSON file (with extension suffix for images)
            self._add_json_file_to_copy(files_to_copy, dest_dir, filename, ext_lower)

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
