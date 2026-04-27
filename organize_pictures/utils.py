import logging
import os

MEDIA_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.heic'],
    'video': ['.mp4', '.mpg', '.mov', '.m4v', '.mts', '.mkv'],
}
OFFSET_CHARS = 'YMDhms'

EXIF_DATE_FIELDS = ['DateTimeOriginal', 'CreateDate'] #, 'XMP:MetadataDate']
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
    "xmp": "%Y:%m:%d %H:%M:%SZ",
}
FILE_EXTS = {
    "image_convert": ['.heic'],
    "image_change": ['.jpeg'],
    "image_preferred": ".jpg",
    "video_convert": ['.mpg', '.mov', '.m4v', '.mts', '.mkv'],
    "video_preferred": ".mp4",
}


_LOG_FORMAT = '[ %(asctime)s ][ %(levelname)s ] %(message)s'
_LOGGER_INITIALIZED = False


def get_logger(verbose: bool = False) -> logging.Logger:
    """
    Return a configured logger.

    Idempotent: handlers are attached exactly once across the lifetime of the
    process. Subsequent calls just return the same logger and (if requested)
    update the stream handler's verbosity. This matters because the logger is
    fetched from a hot path (every TruMedia constructor); previous versions
    closed and re-attached handlers on each call, which races nasty when a
    log line is mid-emit and resulted in formatting recursion errors.

    Override the log file location with the ORGANIZE_PICTURES_LOG environment
    variable.
    """
    global _LOGGER_INITIALIZED  # noqa: PLW0603
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if _LOGGER_INITIALIZED:
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        return logger

    formatter = logging.Formatter(_LOG_FORMAT)

    log_path = os.environ.get("ORGANIZE_PICTURES_LOG", f"{__name__}.log")
    file_handle = logging.FileHandler(log_path)
    file_handle.setLevel(logging.DEBUG)
    file_handle.setFormatter(formatter)

    stream_handle = logging.StreamHandler()
    stream_handle.setLevel(logging.DEBUG if verbose else logging.INFO)
    stream_handle.setFormatter(formatter)

    logger.addHandler(file_handle)
    logger.addHandler(stream_handle)
    _LOGGER_INITIALIZED = True

    return logger


def reset_logger() -> None:
    """
    Tear down the cached logger handlers. Test-only helper -- production code
    should never need this.
    """
    global _LOGGER_INITIALIZED  # noqa: PLW0603
    logger = logging.getLogger(__name__)
    for handler in list(logger.handlers):
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        logger.removeHandler(handler)
    _LOGGER_INITIALIZED = False
