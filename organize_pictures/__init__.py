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
from PIL import Image


class OrganizePictures:
    FILENAME_DATE_FORMAT = "%Y-%m-%d_%H'%M'%S"
    ENCODED_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    IMG_EXTS = ['.jpg', '.jpeg', '.png', '.heic']
    VID_EXTS = ['.mp4', '.mpg', '.mov']
    IMG_CONVERT_EXTS = ['.heic', '.jpeg']
    VID_CONVERT_EXTS = ['.mpg', '.mov']
    PREFERRED_IMAGE_EXT = '.jpg'
    PREFERRED_VIDEO_EXT = '.mp4'

    # pylint: disable=too-many-arguments
    def __init__(
            self,
            logger: Logger,
            source_directory: str,
            destination_directory: str,
            dry_run: bool = False,
            cleanup: bool = False,
            verbose: bool = False,
    ):
        self.logger = logger
        self.source_dir = source_directory
        self.dest_dir = destination_directory
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.verbose = verbose

        self.extensions = self.IMG_EXTS + self.VID_EXTS

    @staticmethod
    def _get_file_ext(file):
        _, ext = os.path.splitext(os.path.basename(file))
        return ext

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

    def get_files(self, path: str):
        files = []
        paths = glob(f"{path}/*")
        for file in paths:
            if os.path.isfile(file):
                ext = self._get_file_ext(file)
                if ext.lower() in self.extensions:
                    files.append(file)
            elif os.path.isdir(file):
                files += self.get_files(file)
        return files

    def get_date_taken(self, _file: str) -> datetime:
        # print(file)

        date_time_obj = None
        ext = self._get_file_ext(_file).lower()
        if ext in self.VID_EXTS:
            media_info = MediaInfo.parse(_file)
            for track in media_info.tracks:
                if track.track_type == 'Video':
                    if hasattr(track, 'encoded_date') and track.encoded_date is not None:
                        date_time_obj = datetime.strptime(track.encoded_date, "%Z %Y-%m-%d %H:%M:%S")
                        _fromtz = pytz.timezone(track.encoded_date[0:track.encoded_date.find(" ")])
                        _totz = pytz.timezone('US/Mountain')
                        date_time_obj = datetime.astimezone(date_time_obj.replace(tzinfo=_fromtz), _totz)
                    else:
                        self.logger.error(f'encoded_date not found in track: {_file}')
                    break
        elif ext in self.IMG_EXTS:
            json_file = f"{_file}.json"
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

    def get_new_fileinfo(self, _file: str, _date: datetime):
        _ext = self._get_file_ext(_file).lower()
        _year = _date.strftime("%Y")
        _month = _date.strftime("%b")
        _dir = f"{self.dest_dir}/{_year}/{_month}"
        _filename = f"{_date.strftime(self.FILENAME_DATE_FORMAT)}{_ext}"
        _new_file_info = {
            'ext': _ext,
            'dir': _dir,
            'filename': _filename,
            'path': f"{_dir}/{_filename}",
            'date_encoded': _date.strftime(self.ENCODED_DATE_FORMAT)
        }
        json_file = f"{_file}.json"
        if os.path.isfile(json_file):
            _new_file_info['json_filename'] = f"{_filename}.json"
            _new_file_info['json_path'] = f"{_dir}/{_filename}.json"
        if _ext in self.IMG_CONVERT_EXTS:
            _new_file_info['convert_path'] = f"{_dir}/{_filename.replace(_ext, self.PREFERRED_IMAGE_EXT)}"
        if _ext in self.VID_CONVERT_EXTS:
            _new_file_info['path'] = f"{_dir}/{_filename.replace(_ext, self.PREFERRED_VIDEO_EXT)}"

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
            if _ext in self.VID_EXTS:
                _media_info = MediaInfo.parse(_new_file_info['path'])
                for _track in _media_info.tracks:
                    if hasattr(_track, 'comment') and _track.comment is not None:
                        if "Converted" in _track.comment:
                            self.logger.info(f"File already converted: {_file}")
                            self.logger.debug(f"\t{_track.comment}")
                            return None

            # increment 1 second and try again
            new_dt = _date + timedelta(seconds=1)
            return self.get_new_fileinfo(_file, new_dt)

        self.logger.info(f"""Source file matches existing destination file:
    Source: {_file}
    Destination: {_new_file_info['path']}""")
        return None

    def run(self):
        files = self.get_files(self.source_dir)
        for file in files:
            moved = False
            json_file = f"{file}.json"
            date_taken = self.get_date_taken(file)
            if date_taken is not None:
                new_file_info = self.get_new_fileinfo(file, date_taken)
                if new_file_info is not None:
                    if new_file_info['ext'] in self.VID_EXTS:
                        self.logger.info(f"Converting '{file}' to '{new_file_info['path']}'")
                        stream = ffmpeg.input(file)
                        stream = ffmpeg.output(
                            stream,
                            new_file_info['path'],
                            acodec="aac",
                            vcodec="h264",
                            map_metadata=0,
                            metadata=f"comment=Converted {file} to {new_file_info['path']}",
                            loglevel="verbose" if self.verbose else "quiet"
                        )
                        _, err = ffmpeg.run(stream)
                        if err is None:
                            self.logger.info(f"Successfully converted '{file}' to '{new_file_info['path']}'")
                            moved = True
                        else:
                            self.logger.error(f"Failed to convert '{file}' to '{new_file_info['path']}'")
                    else:
                        try:
                            self.logger.info(f"Moving file:\n\tSource: {file}\n\tDestination: {new_file_info['path']}")
                            shutil.copyfile(file, new_file_info['path'])
                            moved = True
                            if new_file_info.get('json_filename') is not None:
                                self.logger.info(
                                    f"Moving file:\n\tSource: {json_file}\n\tDestination: {new_file_info['json_path']}")
                                shutil.copyfile(json_file, new_file_info['json_path'])
                            if new_file_info.get('convert_path') is not None:
                                self.logger.debug(
                                    f"Converting file:\n\tSource: {file}\n\tDestination: {new_file_info['convert_path']}"
                                )
                                image = Image.open(file)
                                image.convert('RGB').save(new_file_info['convert_path'])
                        except shutil.Error as exc:
                            self.logger.error(f"Failed to move file: {file}\n{exc}")
                else:
                    # file is already moved
                    moved = True
            if moved and self.cleanup:
                self.logger.info(f"Deleting file: {file}")
                os.remove(file)
                if os.path.isfile(json_file):
                    self.logger.info(f"Deleting JSON file: {file}")
                    os.remove(json_file)

        return True
