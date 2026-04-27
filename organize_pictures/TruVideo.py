import os
import pathlib
import shutil

import ffmpeg

from organize_pictures.utils import (
    MEDIA_TYPES, FILE_EXTS, VIDEO_DATE_FIELDS
)
from organize_pictures.TruMedia import TruMedia


class TruVideo(TruMedia):

    def __init__(self, media_path, json_file_path=None, logger=None, verbose=False, dry_run=False):
        super().__init__(
            media_path=media_path,
            json_file_path=json_file_path,
            logger=logger,
            verbose=verbose,
            dry_run=dry_run,
        )

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
            "video_source": self.media_path_source,
            "json": self.json_file_path,
        }

    @TruMedia.valid.setter
    def valid(self, value):
        if value is None:
            if self.ext.lower() not in MEDIA_TYPES.get('video'):
                self.logger.error(f"Invalid media file: {self.media_path}")
                self._valid = False
            elif self._is_animation():
                self.logger.error(f"Skipping animation: {self.media_path}")
                self._valid = False
            else:
                self._reconcile_mime_type()
            if self._valid:
                self._write_json_data_to_media()
            return
        self._valid = bool(value)

    @property
    def preferred_ext(self):
        return FILE_EXTS.get('video_preferred')

    def _is_animation(self):
        # if an image of the same base name exists, this video file is an animation
        for ext in MEDIA_TYPES.get("image"):
            if (os.path.isfile(self.media_path.replace(self.ext, ext)) or
                    os.path.isfile(self.media_path.replace(self.ext, ext.upper()))):
                return True
        return False

    def _get_media_hash(self):
        # Hash the raw encoded video/audio packets (no re-encode, no container/metadata bytes).
        # `-c copy -f md5` streams packets through ffmpeg's md5 muxer, so two files whose
        # underlying streams are identical but containers differ will hash the same.
        try:
            self.logger.debug(f"Getting hash for {self.media_path}")
            stream = ffmpeg.input(self.media_path)
            stream = ffmpeg.output(
                stream,
                "pipe:",
                format="md5",
                codec="copy",
                loglevel="verbose" if self.verbose else "quiet",
            )
            out, _ = ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
            digest_line = out.decode("ascii", errors="replace").strip()
            if not digest_line.startswith("MD5="):
                self.logger.error(
                    f"Unexpected ffmpeg md5 output for {self.media_path}: {digest_line!r}"
                )
                self._hash = None
                return
            self._hash = digest_line.split("=", 1)[1].strip()
        except (OSError, ffmpeg.Error) as exc:
            stderr = getattr(exc, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            self.logger.error(f"Error hashing video: {self.media_path}\n{exc}\n{stderr}")
            self._hash = None

    def convert(self, dest_ext: str | None = None):
        if dest_ext is None:
            dest_ext = self.preferred_ext
        dest_file = self.media_path.replace(self.ext, dest_ext)
        if os.path.isfile(dest_file):
            self.logger.error(f"Not converting {self.media_path} to {dest_ext} as it already exists")
            return False
        if self._convert_video(self.media_path, dest_file):
            self.media_path_source = self.media_path
            if self.json_file_path:
                new_json_file = f"{dest_file}.json"
                if not os.path.isfile(new_json_file):
                    shutil.move(self.json_file_path, new_json_file)
                    self.json_file_path = new_json_file
                else:
                    self.logger.warning(f"Destination JSON file already exists: {new_json_file}")
            self.media_path = dest_file
            self.ext = dest_ext
            self._write_json_data_to_media()
            return True
        return False

    def copy(self, dest_info: dict):
        """
        Copy video to destination path
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
            self.convert()

        # If video was converted, copy the original source file with .ORIG extension
        if self.media_path_source:
            source_ext = pathlib.Path(self.media_path_source).suffix
            files_to_copy[self.media_path_source] = f"{dest_dir}/{filename}{source_ext}.ORIG"

        dest_file = f"{dest_dir}/{filename}{self.ext}"
        if os.path.isfile(dest_file):
            self.logger.warning(f"Destination file already exists: {dest_file}")
            return files_to_copy

        files_to_copy[self.media_path] = dest_file
        self._add_json_file_to_copy(files_to_copy, dest_dir, filename)

        for source, dest in files_to_copy.items():
            if os.path.isfile(dest):
                self.logger.warning(f"Destination file already exists, skipping copy: {dest}")
                continue
            self.logger.info(f"Copying file:\n\tSource: {source}\n\tDestination: {dest}")
            shutil.copy(source, dest)
            self.logger.debug("Successfully copied file")

        return files_to_copy

    def __repr__(self):
        """
        Return a detailed string representation for debugging
        """
        return (f"TruVideo(media_path='{self.media_path}', "
                f"media_path_source={repr(self.media_path_source)}, "
                f"json_file_path={repr(self.json_file_path)}, "
                f"valid={self.valid}, "
                f"ext='{self.ext}', "
                f"date_taken={repr(self.date_taken)}, "
                f"hash='{self.hash if self.hash else 'None'}')")

    def __str__(self):
        """
        Return a user-friendly string representation
        """
        filename = os.path.basename(self.media_path)
        status = "✅ Valid" if self.valid else "❌ Invalid"

        # Get file size
        try:
            file_size = os.path.getsize(self.media_path)
            if file_size > 1024 * 1024 * 1024:  # GB
                size_str = f"{file_size / (1024 * 1024 * 1024):.1f}GB"
            elif file_size > 1024 * 1024:  # MB
                size_str = f"{file_size / (1024 * 1024):.1f}MB"
            elif file_size > 1024:  # KB
                size_str = f"{file_size / 1024:.1f}KB"
            else:
                size_str = f"{file_size}B"
        except Exception:
            size_str = "Unknown"

        # Get duration if available
        duration_str = ""
        try:
            exif_data = self.exif_data
            if "QuickTime:Duration" in exif_data:
                duration = exif_data["QuickTime:Duration"]
                try:
                    duration_sec = float(duration.split()[0])
                    minutes = int(duration_sec // 60)
                    seconds = int(duration_sec % 60)
                    duration_str = f" | ⏱️ {minutes}:{seconds:02d}"
                except:
                    pass
        except:
            pass

        # Date information
        date_str = ""
        if self.date_taken:
            date_str = f" | 📅 {self.date_taken.strftime('%Y-%m-%d')}"

        # JSON indicator
        json_str = " | 📋 JSON" if self.json_data else ""

        # Animation indicator
        animation_str = " | 🎬 Animation" if self._is_animation() else ""

        return f"📹 {filename} ({size_str}) {status}{duration_str}{date_str}{json_str}{animation_str}"
