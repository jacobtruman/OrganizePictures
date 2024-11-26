import hashlib
import os
import shutil
import tempfile

import ffmpeg
import magic
import mimetypes

from organize_pictures.utils import (
    MEDIA_TYPES, FILE_EXTS, VIDEO_DATE_FIELDS
)
from organize_pictures.TruMedia import TruMedia


class TruVideo(TruMedia):

    def __init__(self, media_path, logger=None, verbose=False):
        super().__init__(media_path=media_path, logger=logger, verbose=verbose)

    @property
    def media_type(self):
        if self._media_type is None:
            self._media_type = "video"
        return self._media_type

    @property
    def date_fields(self) -> list:
        return VIDEO_DATE_FIELDS

    @property
    def files(self):
        """
        Get associated files
        :return:
        """
        return {
            "video": self.media_path,
        }

    @property
    def valid(self):
        return self._valid

    @valid.setter
    def valid(self, _):
        if self.ext.lower() not in MEDIA_TYPES.get('video'):
            self.logger.error(f"Invalid media file: {self.media_path}")
            self._valid = False
        elif self._is_animation():
            self.logger.error(f"Skipping animation: {self.media_path}")
            self._valid = False
        else:
            self._reconcile_mime_type()

    def _is_animation(self):
        # if an image of the same base name exists, this video file is an animation
        for ext in MEDIA_TYPES.get("image"):
            if (os.path.isfile(self.media_path.replace(self.ext, ext)) or
                    os.path.isfile(self.media_path.replace(self.ext, ext.upper()))):
                return True

    def _reconcile_mime_type(self):
        mime_guess = mimetypes.guess_type(self.media_path)[0]
        mime_actual = magic.from_file(self.media_path, mime=True)
        if mime_actual == "inode/x-empty":
            self.valid = False
        elif mime_guess != mime_actual:
            file_updates = {}
            _mt = mimetypes.MimeTypes()
            new_ext = _mt.types_map_inv[1].get(mime_actual)[0]
            new_path = self.media_path.replace(self.ext, new_ext)
            self.ext = new_ext
            file_updates["media_path"] = new_path
            self.logger.error(f"Mimetype does not match filetype: {mime_guess} != {mime_actual}")

            for key, value in file_updates.items():
                source = getattr(self, key)
                if self.dev_mode:
                    self.logger.info(f"Would update {key} '{source}' to '{value}'")
                    shutil.copy(source, value)
                else:
                    self.logger.info(f"Updating {key} '{source}' to '{value}'")
                    shutil.move(source, value)
                    setattr(self, key, value)

    def _get_media_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                self.logger.debug(f"Getting hash for {self.media_path}")
                temp_file = f"{temp_dir}/{os.path.basename(self.media_path)}"
                stream = ffmpeg.input(self.media_path)
                stream = ffmpeg.output(
                    stream,
                    temp_file,
                    acodec="aac",
                    vcodec="h264",
                    map_metadata=0,
                    loglevel="verbose" if self.verbose else "quiet"
                )
                _, err = ffmpeg.run(stream)
                if err:
                    self.logger.error(err)
                    exit()

                with open(temp_file, "rb") as f:
                    s = f.read()
                    self._hash = hashlib.md5(s).hexdigest()
            except Exception:  # pylint: disable=broad-except
                self.logger.error(f"Error opening image: {self.media_path}")
                self._hash = None

    def convert(self, dest_ext: str):
        dest_file = self.media_path.replace(self.ext, dest_ext)
        if self._convert_video(self.media_path, dest_file):
            self.media_path = dest_file
            self.ext = dest_ext
            return True
        return False

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

        if ext_lower in FILE_EXTS.get('video_convert'):
            # add the pre-converted file to be copied
            files_to_copy[self.media_path] = f"{dest_dir}/{filename}{ext_lower}.ORIG"
            self.convert(FILE_EXTS.get('video_preferred'))

        dest_file = f"{dest_dir}/{filename}{self.ext}"
        if not os.path.isfile(dest_file):
            files_to_copy[self.media_path] = dest_file

            for source, dest in files_to_copy.items():
                self.logger.info(f"Copying file:\n\tSource: {source}\n\tDestination: {dest}")
                shutil.copy(source, dest)
                self.logger.debug("Successfully copied file")
        else:
            self.logger.warning(f"Destination file already exists: {dest_file}")

        return files_to_copy
