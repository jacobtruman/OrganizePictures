import json
import os
from datetime import datetime, timedelta
import hashlib
import shutil
from logging import Logger
from glob import glob
import time

import pytz
import piexif
from pymediainfo import MediaInfo
import ffmpeg
from PIL import Image, UnidentifiedImageError

MEDIA_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.heic'],
    'video': ['.mp4', '.mpg', '.mov', '.m4v', '.mts'],
}


class OrganizePictures:
    FILENAME_DATE_FORMAT = "%Y-%m-%d_%H'%M'%S"
    ENCODED_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    IMG_CONVERT_EXTS = ['.heic']
    IMG_CHANGE_EXTS = ['.jpeg']
    VID_CONVERT_EXTS = ['.mpg', '.mov', '.m4v', '.mts']
    PREFERRED_IMAGE_EXT = '.jpg'
    PREFERRED_VIDEO_EXT = '.mp4'

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
            verbose: bool = False,
    ):
        self.logger = logger
        self.source_dir = source_directory
        self.dest_dir = destination_directory
        self.media_type = media_type
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.verbose = verbose

        self.extensions = extensions
        if self.extensions is None:
            if media_type is not None:
                self.extensions = MEDIA_TYPES.get(media_type)
            else:
                self.extensions = []
                for exts in MEDIA_TYPES.values():
                    self.extensions += exts

    @staticmethod
    def _get_file_ext(file):
        _, ext = os.path.splitext(os.path.basename(file))
        return ext

    def _get_json_file(self, _file):
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
    def _md5(fname):
        hash_md5 = hashlib.md5()
        with open(fname, "rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

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
        return files

    def _get_date_taken(self, _file: str) -> datetime:
        date_time_obj = None
        ext = self._get_file_ext(_file).lower()
        if ext in MEDIA_TYPES.get('video'):
            media_info = MediaInfo.parse(_file)
            for track in media_info.tracks:
                if track.track_type in ['Video', 'General']:
                    if track.encoded_date is not None:
                        date_time_obj = datetime.strptime(track.encoded_date, "%Z %Y-%m-%d %H:%M:%S")
                        _fromtz = pytz.timezone(track.encoded_date[0:track.encoded_date.find(" ")])
                        _totz = pytz.timezone('US/Mountain')
                        date_time_obj = datetime.astimezone(date_time_obj.replace(tzinfo=_fromtz), _totz)
                        break
                    if track.recorded_date is not None:
                        date_time_obj = datetime.strptime(track.recorded_date, "%Y-%m-%d %H:%M:%S%z")
                        break
        elif ext in MEDIA_TYPES.get('image'):
            json_file = self._get_json_file(_file)
            if os.path.isfile(json_file):
                date_time_obj = datetime.fromtimestamp(
                    int(self._load_json_file(json_file).get('photoTakenTime', {}).get('timestamp')))
            else:
                try:
                    exif_dict = piexif.load(_file)
                    for tag, value in exif_dict['Exif'].items():
                        if "DateTimeDigitized" in piexif.TAGS['Exif'][tag]["name"]:
                            date_time_obj = datetime.strptime(value.decode(), '%Y:%m:%d %H:%M:%S')
                            break
                except piexif._exceptions.InvalidImageDataError:
                    self.logger.error(f'Unable to get exif data for file: {_file}')
        # if other dates are not found, use the file modified date
        if date_time_obj is None:
            date_time_obj = datetime.strptime(time.ctime(os.path.getmtime(_file)), '%c')

        return date_time_obj

    def _convert_video(self, _file: str, _new_file: str):
        converted = False
        self.logger.info(f"Converting '{_file}' to '{_new_file}'")
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
            self.logger.info(f"Successfully converted '{_file}' to '{_new_file}'")
            converted = True
        else:
            self.logger.error(f"Failed to convert '{_file}' to '{_new_file}'")
        return converted

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

    def _get_new_fileinfo(self, _file: str, _date: datetime):
        _ext = self._get_file_ext(_file)
        _ext_lower = _ext.lower()
        _year = _date.strftime("%Y")
        _month = _date.strftime("%b")
        _dir = f"{self.dest_dir}/{_year}/{_month}"
        _filename = f"{_date.strftime(self.FILENAME_DATE_FORMAT)}{_ext_lower}"
        _new_file_info = {
            'ext': _ext_lower,
            'dir': _dir,
            'filename': _filename,
            'path': f"{_dir}/{_filename}",
            'date_encoded': _date.strftime(self.ENCODED_DATE_FORMAT)
        }
        json_file = self._get_json_file(_file)
        if os.path.isfile(json_file):
            json_filename = self._get_json_file(_filename)
            _new_file_info['json_filename'] = json_filename
            _new_file_info['json_path'] = f"{_dir}/{json_filename}"

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
            self.logger.warning(f"Destination path does not exist, creating: {_new_file_info['dir']}")
            os.makedirs(_new_file_info['dir'])
        if not os.path.exists(_new_file_info['path']):
            return _new_file_info

        self.logger.warning(f"Destination file already exists: {_new_file_info['path']}")
        if self._md5(_new_file_info['path']) != self._md5(_file):
            self.logger.warning(f"""Source file does not match existing destination file:
    Source: {_file}
    Destination: {_new_file_info['path']}""")
            if _ext_lower in MEDIA_TYPES.get('video'):
                _media_info = MediaInfo.parse(_new_file_info['path'])
                for _track in _media_info.tracks:
                    if hasattr(_track, 'comment') and _track.comment is not None:
                        if "Converted" in _track.comment:
                            self.logger.info(f"File already converted: {_file}")
                            self.logger.debug(f"\t{_track.comment}")
                            return None

            # increment 1 second and try again
            new_dt = _date + timedelta(seconds=1)
            return self._get_new_fileinfo(_file, new_dt)

        self.logger.info(f"""Source file matches existing destination file:
    Source: {_file}
    Destination: {_new_file_info['path']}""")
        return None

    def run(self):
        files = self._get_files(self.source_dir)
        for media_file in files:
            cleanup_files = []
            json_file = self._get_json_file(media_file)
            date_taken = self._get_date_taken(media_file)
            if date_taken is not None:
                new_file_info = self._get_new_fileinfo(media_file, date_taken)
                if new_file_info is not None:
                    if new_file_info['ext'] in MEDIA_TYPES.get('video'):
                        if self._convert_video(media_file, new_file_info['path']):
                            cleanup_files.append(media_file)
                    else:
                        try:
                            self.logger.info(
                                f"Moving file:\n\tSource: {media_file}\n\tDestination: {new_file_info['path']}"
                            )
                            if new_file_info.get('convert_path') is not None:
                                self.logger.debug(
                                    f"Converting file:\n"
                                    f"\tSource: {media_file}\n\tDestination: {new_file_info['convert_path']}"
                                )
                                image = Image.open(media_file)
                                image.convert('RGB').save(new_file_info['convert_path'])
                            shutil.copyfile(media_file, new_file_info['path'])
                            cleanup_files.append(media_file)
                            if new_file_info.get('json_filename') is not None:
                                self.logger.info(
                                    f"Moving file:\n\tSource: {json_file}\n\tDestination: {new_file_info['json_path']}")
                                shutil.copyfile(json_file, new_file_info['json_path'])
                                cleanup_files.append(json_file)
                            if "animation_source" in new_file_info:
                                if self._convert_video(
                                        new_file_info['animation_source'],
                                        new_file_info['animation_dest']
                                ):
                                    cleanup_files.append(new_file_info['animation_source'])
                        except UnidentifiedImageError as exc:
                            self.logger.error(f"Failed to convert file: {media_file}\n{exc}")
                        except shutil.Error as exc:
                            self.logger.error(f"Failed to move file: {media_file}\n{exc}")
                else:
                    # file is already moved
                    cleanup_files.append(media_file)

            if cleanup_files and self.cleanup:
                for cleanup_file in cleanup_files:
                    self.logger.info(f"Deleting file: {cleanup_file}")
                    os.remove(cleanup_file)

        return True
