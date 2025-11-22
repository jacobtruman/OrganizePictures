"""Unit tests for organize_pictures.utils module"""
import logging
import os
import pytest
from organize_pictures.utils import (
    get_logger,
    MEDIA_TYPES,
    OFFSET_CHARS,
    EXIF_DATE_FIELDS,
    VIDEO_DATE_FIELDS,
    DATE_FORMATS,
    FILE_EXTS,
)


class TestConstants:
    """Test module constants"""

    def test_media_types_structure(self):
        """Test MEDIA_TYPES dictionary structure"""
        assert isinstance(MEDIA_TYPES, dict)
        assert 'image' in MEDIA_TYPES
        assert 'video' in MEDIA_TYPES
        assert isinstance(MEDIA_TYPES['image'], list)
        assert isinstance(MEDIA_TYPES['video'], list)

    def test_media_types_image_extensions(self):
        """Test image extensions in MEDIA_TYPES"""
        expected_image_exts = ['.jpg', '.jpeg', '.png', '.heic']
        assert MEDIA_TYPES['image'] == expected_image_exts

    def test_media_types_video_extensions(self):
        """Test video extensions in MEDIA_TYPES"""
        expected_video_exts = ['.mp4', '.mpg', '.mov', '.m4v', '.mts', '.mkv']
        assert MEDIA_TYPES['video'] == expected_video_exts

    def test_offset_chars(self):
        """Test OFFSET_CHARS constant"""
        assert OFFSET_CHARS == 'YMDhms'
        assert len(OFFSET_CHARS) == 6

    def test_exif_date_fields(self):
        """Test EXIF_DATE_FIELDS constant"""
        assert isinstance(EXIF_DATE_FIELDS, list)
        assert 'DateTimeOriginal' in EXIF_DATE_FIELDS
        assert 'CreateDate' in EXIF_DATE_FIELDS
        assert len(EXIF_DATE_FIELDS) == 2

    def test_video_date_fields(self):
        """Test VIDEO_DATE_FIELDS constant"""
        assert isinstance(VIDEO_DATE_FIELDS, list)
        assert 'QuickTime:CreateDate' in VIDEO_DATE_FIELDS
        assert 'QuickTime:TrackCreateDate' in VIDEO_DATE_FIELDS
        assert 'QuickTime:MediaCreateDate' in VIDEO_DATE_FIELDS
        assert 'Matroska:CreationTime' in VIDEO_DATE_FIELDS
        assert len(VIDEO_DATE_FIELDS) == 4

    def test_date_formats(self):
        """Test DATE_FORMATS dictionary"""
        assert isinstance(DATE_FORMATS, dict)
        assert 'default' in DATE_FORMATS
        assert 'exif' in DATE_FORMATS
        assert 'filename' in DATE_FORMATS
        assert 'video' in DATE_FORMATS
        assert DATE_FORMATS['default'] == "%Y-%m-%d %H:%M:%S"
        assert DATE_FORMATS['exif'] == "%Y:%m:%d %H:%M:%S"

    def test_file_exts(self):
        """Test FILE_EXTS dictionary"""
        assert isinstance(FILE_EXTS, dict)
        assert 'image_convert' in FILE_EXTS
        assert 'image_preferred' in FILE_EXTS
        assert 'video_convert' in FILE_EXTS
        assert 'video_preferred' in FILE_EXTS
        assert FILE_EXTS['image_preferred'] == '.jpg'
        assert FILE_EXTS['video_preferred'] == '.mp4'


class TestGetLogger:
    """Test get_logger function"""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a Logger instance"""
        logger = get_logger()
        assert isinstance(logger, logging.Logger)

    def test_get_logger_verbose_false(self):
        """Test get_logger with verbose=False"""
        logger = get_logger(verbose=False)
        assert logger.level == logging.DEBUG
        # Check that handlers are configured
        assert len(logger.handlers) >= 2

    def test_get_logger_verbose_true(self):
        """Test get_logger with verbose=True"""
        logger = get_logger(verbose=True)
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) >= 2

    def test_get_logger_has_file_handler(self):
        """Test that logger has a file handler"""
        logger = get_logger()
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0

    def test_get_logger_has_stream_handler(self):
        """Test that logger has a stream handler"""
        logger = get_logger()
        stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) > 0

    def test_get_logger_clears_existing_handlers(self):
        """Test that get_logger clears existing handlers"""
        logger1 = get_logger()
        handler_count1 = len(logger1.handlers)
        logger2 = get_logger()
        handler_count2 = len(logger2.handlers)
        # Should have same number of handlers (old ones cleared)
        assert handler_count1 == handler_count2

    def test_get_logger_formatter(self):
        """Test that logger handlers have correct formatter"""
        logger = get_logger()
        for handler in logger.handlers:
            assert handler.formatter is not None
            format_string = handler.formatter._fmt
            assert '%(asctime)s' in format_string
            assert '%(levelname)s' in format_string
            assert '%(message)s' in format_string

    def test_get_logger_creates_log_file(self):
        """Test that get_logger creates a log file"""
        logger = get_logger()
        # Trigger logging to create file
        logger.info("Test message")
        # Check if log file exists
        log_file = "organize_pictures.utils.log"
        assert os.path.exists(log_file)

    def teardown_method(self):
        """Clean up log file after tests"""
        log_file = "organize_pictures.utils.log"
        if os.path.exists(log_file):
            # Clear handlers to release file
            logger = logging.getLogger('organize_pictures.utils')
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)

