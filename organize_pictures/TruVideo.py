from datetime import datetime
import hashlib
import os
import shutil
import tempfile

from exiftool import ExifToolHelper
import ffmpeg
import magic
import mimetypes
from pillow_heif import register_heif_opener

from organize_pictures.utils import get_logger, MEDIA_TYPES, EXIF_DATE_FIELDS, DATE_FORMATS, VIDEO_DATE_FIELDS, FILE_EXTS

register_heif_opener()


class TruVideo:

    def __init__(self, video_path, logger=None, verbose=False):
        self.verbose = verbose
        self.dev_mode = False
        self._logger = None
        self.logger = logger
        self._video_path = None
        self.video_path = video_path
        self._ext = None
        self._exif_data = None
        self._date_taken = None
        self._hash = None
        self._valid = None
        self.valid = None

    @property
    def video_path(self):
        return self._video_path

    @video_path.setter
    def video_path(self, value):
        if not os.path.isfile(value):
            self.logger.error(f"Image not found: {value}")
            raise FileNotFoundError(f"Image not found: {value}")
        self._video_path = value

    @property
    def logger(self):
        if self._logger is None:
            self._logger = get_logger()
        return self._logger

    @logger.setter
    def logger(self, value):
        if value is None:
            value = get_logger()
        self._logger = value

    @property
    def hash(self):
        if self._hash is None:
            self._get_video_hash()
        return self._hash

    @property
    def ext(self):
        if self._ext is None:
            _, ext = os.path.splitext(os.path.basename(self.video_path))
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
            "video": self.video_path,
        }

    @property
    def exif_data(self):
        if self._exif_data is None:
            with ExifToolHelper() as eth:
                self._exif_data = (eth.get_metadata(self.video_path) or [])[0]
        return self._exif_data

    @property
    def date_taken(self):
        if self._date_taken is None:
            # if self.ext in MEDIA_TYPES.get('video'):
            #     media_info = MediaInfo.parse(self.video_path)
            #     for track in media_info.tracks:
            #         if track.track_type in ['Video', 'General']:
            #             if track.encoded_date is not None:
            #                 self._date_taken = datetime.strptime(
            #                     track.encoded_date, DATE_FORMATS.get(self.ext, DATE_FORMATS.get("encoded"))
            #                 )
            #                 _fromtz = pytz.timezone(track.encoded_date.split(" ")[-1])
            #                 _totz = pytz.timezone('US/Mountain')
            #                 self._date_taken = datetime.astimezone(self._date_taken.replace(tzinfo=_fromtz), _totz)
            #                 break
            #             if track.recorded_date is not None:
            #                 self._date_taken = datetime.strptime(track.recorded_date, DATE_FORMATS.get("recorded"))
            #                 break

            try:
                for _date_field in VIDEO_DATE_FIELDS:
                    if _date_field in self.exif_data:
                        self.logger.info(f"Using date field: {_date_field}")
                        for date_format in DATE_FORMATS.values():
                            try:
                                self._date_taken = datetime.strptime(self.exif_data.get(_date_field), date_format)
                                self.logger.info(f"Date field {_date_field} format: {date_format}")
                                break
                            except Exception as exc:
                                self.logger.error(
                                    f"Unable to convert date field using format {date_format}: {_date_field}\n{exc}"
                                )
                        break
            except Exception as exc:
                self.logger.error(f'Unable to get exif data for file: {self.video_path}:\n{exc}')

            if self._date_taken is None:
                self.logger.error(f"Unable to determine date taken for {self.video_path}")

        return self._date_taken

    @date_taken.setter
    def date_taken(self, value: datetime):
        self._date_taken = value
        self.logger.info(f"Setting date taken to {value}")
        _date = value.strftime(DATE_FORMATS.get("default"))
        self._update_tags(self.video_path, {field: _date for field in EXIF_DATE_FIELDS})

    @property
    def valid(self):
        return self._valid

    @valid.setter
    def valid(self, _):
        if self.ext.lower() not in MEDIA_TYPES.get('video'):
            self.logger.error(f"Invalid video file: {self.video_path}")
            self._valid = False
        else:
            self._valid = self._reconcile_mime_type()

    def _reconcile_mime_type(self):
        mime_guess = mimetypes.guess_type(self.video_path)[0]
        mime_actual = magic.from_file(self.video_path, mime=True)
        if mime_actual == "inode/x-empty":
            return False
        elif mime_guess != mime_actual:
            file_updates = {}
            _mt = mimetypes.MimeTypes()
            new_ext = _mt.types_map_inv[1].get(mime_actual)[0]
            new_path = self.video_path.replace(self.ext, new_ext)
            self.ext = new_ext
            file_updates["image_path"] = new_path
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
        return True

    def _get_video_hash(self):
        print(self.video_path)
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                self.logger.debug(f"Getting hash for {self.video_path}")
                temp_file = f"{temp_dir}/{os.path.basename(self.video_path)}"
                stream = ffmpeg.input(self.video_path)
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
                self.logger.error(f"Error opening image: {self.video_path}")
                self._hash = None

    def _update_tags(self, video_path: str = None, tags: dict = None):
        if tags is not None:
            if video_path is None:
                video_path = self.video_path
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
                self.logger.debug(f"Updating tags for {video_path}\n{tags}")
                with ExifToolHelper() as _eth:
                    _eth.set_tags(
                        [video_path],
                        tags=tags,
                        params=["-P", "-overwrite_original"]
                    )

    def _write_data_to_video(self, video_path=None):
        if video_path is None:
            video_path = self.video_path
        if self.exif_data:
            tags = {}
            for date_field in VIDEO_DATE_FIELDS:
                if date_field in self.exif_data:
                    self.exif_data.get(date_field)
                _date = datetime.fromtimestamp(
                    int(self.json_data.get("photoTakenTime").get("timestamp"))
                ).strftime(DATE_FORMATS.get("default"))
                for field in EXIF_DATE_FIELDS:
                    tags[field] = _date
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

                self._update_tags(video_path, tags)

    def convert(self, dest_ext: str):
        dest_file = self.video_path.replace(self.ext, dest_ext)
        if os.path.isfile(dest_file):
            self.logger.info(f"Skipping conversion of \"{self.video_path}\" to \"{dest_file}\" as it already exists")
            return True
        else:
            self.logger.info(f"Converting \"{self.video_path}\" to \"{dest_file}\"")
            stream = ffmpeg.input(self.video_path)
            stream = ffmpeg.output(
                stream,
                dest_file,
                acodec="aac",
                vcodec="h264",
                map_metadata=0,
                metadata=f"comment=Converted {self.video_path} to {dest_file}",
                loglevel="verbose" if self.verbose else "quiet"
            )
            _, err = ffmpeg.run(stream)
            if err is None:
                self.logger.info(f"Successfully converted \"{self.video_path}\" to \"{dest_file}\"")
                return True
            else:
                self.logger.error(f"Failed to convert \"{self.video_path}\" to \"{dest_file}\"")
        return False

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
            files_to_copy[self.video_path] = dest_file

            for source, dest in files_to_copy.items():
                self.logger.info(f"Copying file:\n\tSource: {source}\n\tDestination: {dest}")
                shutil.copy(source, dest)
                self.logger.debug("Successfully copied file")
        else:
            self.logger.warning(f"Destination file already exists: {dest_file}")

        return files_to_copy

# tv = TruVideo("/Users/jatruman/workspace/personal/OrganizePictures/tests/testing/PXL_20240628_181441700.TS.mp4", verbose=True)
tv = TruVideo("/Users/jatruman/workspace/personal/OrganizePictures/tests/testing/2021-05-01 09.36.31.mp4", verbose=True)
print(tv.valid)
# print(tv.date_taken)
# tags = {
#     "GPSLatitude": tv.exif_data["Composite:GPSLatitude"],
#     "GPSLongitude": tv.exif_data["Composite:GPSLongitude"],
#     "Composite:GPSLongitude": tv.exif_data["Composite:GPSLongitude"]
# }
# print(tv.exif_data)
# for field in EXIF_DATE_FIELDS:
#     tags[field] = tv.date_taken
#
# tv._update_tags(tv.video_path, tags)
