import logging

MEDIA_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.heic'],
    'video': ['.mp4', '.mpg', '.mov', '.m4v', '.mts', '.mkv'],
}
OFFSET_CHARS = 'YMDhms'

EXIF_DATE_FIELDS = ['DateTimeOriginal', 'CreateDate']
VIDEO_DATE_FIELDS = [
    'QuickTime:CreateDate',
    'QuickTime:TrackCreateDate',
    'QuickTime:MediaCreateDate',
    'Matroska:CreationTime'
]
DATE_FORMATS = {
    "default": "%Y-%m-%d %H:%M:%S",
    "exif": "%Y:%m:%d %H:%M:%S",
    "m4": "%Y/%m/%d %H:%M:%S,%f",
    "filename": "%Y-%m-%d_%H'%M'%S",
    "video": "%Y-%m-%d %H:%M:%S",
    "mkv": "%Y-%m-%dT%H:%M:%SZ",
    "recorded": "%Y-%m-%d %H:%M:%S%z",
    "encoded": "%Y-%m-%d %H:%M:%S %Z",
}
FILE_EXTS = {
    "image_convert": ['.heic'],
    "image_change": ['.jpeg'],
    "image_preferred": ".jpg",
    "video_convert": ['.mpg', '.mov', '.m4v', '.mts', '.mkv'],
    "video_preferred": ".mp4",
}


def get_logger(verbose: bool = False):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[ %(asctime)s ][ %(levelname)s ] %(message)s')

    file_handle = logging.FileHandler(f"{__name__}.log")
    if verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    file_handle.setLevel(logging.DEBUG)
    file_handle.setFormatter(formatter)

    stream_handle = logging.StreamHandler()
    stream_handle.setLevel(log_level)
    stream_handle.setFormatter(formatter)

    logger.addHandler(file_handle)
    logger.addHandler(stream_handle)

    return logger