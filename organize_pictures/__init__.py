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
import pyheif

MEDIA_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.heic'],
    'video': ['.mp4', '.mpg', '.mov', '.m4v', '.mts', '.mkv'],
}


class OrganizePictures:
    FILENAME_DATE_FORMAT = "%Y-%m-%d_%H'%M'%S"
    ENCODED_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    PIEXIF_DATE_FORMAT = '%Y:%m:%d %H:%M:%S'
    VIDEO_DATE_FORMATS = {
        "default": "%Z %Y-%m-%d %H:%M:%S",
        ".mkv": "%Z %Y-%m-%dT%H:%M:%SZ",
    }
    IMG_CONVERT_EXTS = ['.heic']
    IMG_CHANGE_EXTS = ['.jpeg']
    VID_CONVERT_EXTS = ['.mpg', '.mov', '.m4v', '.mts', '.mkv']
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
            sub_dirs: bool = True,
            verbose: bool = False,
    ):
        self.logger = logger
        self.source_dir = source_directory
        self.dest_dir = destination_directory
        self.media_type = media_type
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.sub_dirs = sub_dirs
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

    @staticmethod
    def _get_file_ext(file):
        _, ext = os.path.splitext(os.path.basename(file))
        return ext

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
                            date_time_obj = datetime.strptime(value.decode(), self.PIEXIF_DATE_FORMAT)
                            break
                except piexif._exceptions.InvalidImageDataError:
                    self.logger.error(f'Unable to get exif data for file: {_file}')
        # if other dates are not found, use the file modified date
        if date_time_obj is None:
            date_time_obj = datetime.strptime(time.ctime(os.path.getmtime(_file)), '%c')

        return date_time_obj

    def _convert_video(self, _file: str, _new_file: str):
        converted = False
        if os.path.isfile(_new_file):
            self.logger.info(f"Skipping conversion of '{_file}' to '{_new_file}' as it already exists")
            converted = True
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
            self.results['moved'] += 1
            self.logger.info(f"Successfully converted '{_file}' to '{_new_file}'")
            converted = True
        else:
            self.logger.error(f"Failed to convert '{_file}' to '{_new_file}'")
        return converted

    def _convert_image(self, source_file: str, dest_file: str):
        self.logger.debug(f"Converting file:\n\tSource: {source_file}\n\tDestination: {dest_file}")
        image_ext = self._get_file_ext(source_file).lower()
        method = "pillow"
        try:
            image = Image.open(source_file)
            image.convert('RGB').save(dest_file)
        except UnidentifiedImageError as pilexc:
            if image_ext != ".heic":
                return False
            method = "pyheif"
            self.logger.error(f"Failed first conversion attempt via {method}: {source_file}\n{pilexc}")
            heif_file = pyheif.read(source_file)
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            image.save(dest_file)
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

    def _update_file_date(self, _file, _date: datetime):
        try:
            new_date = _date.strftime(self.PIEXIF_DATE_FORMAT)
            image = Image.open(_file)

            exif_dict = piexif.load(_file)
            if exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] != new_date:
                self.logger.debug(f"Updating date digitized for {_file}")
                exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = new_date
                exif_bytes = piexif.dump(exif_dict)
                image.save(_file, exif=exif_bytes)
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
            # Need to work out issues with this before enabling
            # self._update_file_date(_file, new_dt)
            return self._get_new_fileinfo(_file, new_dt)

    def run(self):
        files = self._get_files(self.source_dir)
        for media_file in files:
            cleanup_files = []
            json_file = self._get_json_file(media_file)
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
                            # Need to work out issues with this before enabling
                            # self._update_file_date(media_file, new_file_info['date_encoded'])
                            shutil.copyfile(media_file, new_file_info['path'])
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
                        except shutil.Error as exc:
                            self.results['failed'] += 1
                            self.logger.error(f"Failed to move file: {media_file}\n{exc}")

                    if new_file_info.get('json_filename') is not None:
                        self.logger.info(
                            f"Moving file:\n\tSource: {json_file}\n\tDestination: {new_file_info['json_path']}")
                        shutil.copyfile(json_file, new_file_info['json_path'])
                        self.results['moved'] += 1
                        cleanup_files.append(json_file)
                else:
                    # file is already moved
                    self.logger.info(f"File already moved: {media_file}")
                    cleanup_files.append(media_file)
                    if new_file_info.get('json_filename'):
                        cleanup_files.append(new_file_info.get('json_filename'))
                    if new_file_info.get('animation_source'):
                        cleanup_files.append(new_file_info.get('animation_source'))

            if cleanup_files and self.cleanup:
                for cleanup_file in cleanup_files:
                    self.results['deleted'] += 1
                    self.logger.info(f"Deleting file: {cleanup_file}")
                    os.remove(cleanup_file)

        return self.results
