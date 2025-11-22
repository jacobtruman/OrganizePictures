"""Unit tests for organize_pictures.TruMedia module"""
import os
import pytest
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from organize_pictures.TruMedia import TruMedia
from organize_pictures.TruImage import TruImage
from organize_pictures.utils import get_logger


class ConcreteTruMedia(TruMedia):
    """Concrete implementation of TruMedia for testing"""
    
    @property
    def media_type(self):
        return "test"
    
    @property
    def date_fields(self):
        return ['DateTimeOriginal', 'CreateDate']
    
    @property
    def preferred_ext(self):
        return ".jpg"
    
    def convert(self, dest_ext=None):
        pass
    
    def _get_media_hash(self):
        self._hash = "test_hash_123"


class TestTruMediaInit:
    """Test TruMedia initialization"""

    def test_init_with_valid_file(self, tmp_path):
        """Test initialization with a valid file"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.media_path == str(test_file)
        assert media.verbose is False
        assert media.dev_mode is False
        assert media.regenerated is False

    def test_init_with_nonexistent_file(self):
        """Test initialization with nonexistent file raises error"""
        with pytest.raises(FileNotFoundError):
            ConcreteTruMedia(media_path="/nonexistent/file.jpg")

    def test_init_with_logger(self, tmp_path):
        """Test initialization with custom logger"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        logger = get_logger()
        
        media = ConcreteTruMedia(media_path=str(test_file), logger=logger)
        assert media.logger == logger

    def test_init_with_verbose(self, tmp_path):
        """Test initialization with verbose flag"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file), verbose=True)
        assert media.verbose is True


class TestTruMediaProperties:
    """Test TruMedia properties"""

    def test_media_path_property(self, tmp_path):
        """Test media_path property getter"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.media_path == str(test_file)

    def test_ext_property(self, tmp_path):
        """Test ext property"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.ext == ".jpg"

    def test_ext_setter(self, tmp_path):
        """Test ext property setter"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        media.ext = ".png"
        assert media.ext == ".png"

    def test_valid_property_default(self, tmp_path):
        """Test valid property default value"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.valid is True

    def test_hash_property(self, tmp_path):
        """Test hash property"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.hash == "test_hash_123"

    def test_logger_property_default(self, tmp_path):
        """Test logger property creates default logger"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.logger is not None


class TestTruMediaJsonHandling:
    """Test TruMedia JSON file handling"""

    def test_json_file_path_none_when_no_json(self, tmp_path):
        """Test json_file_path is None when no JSON file exists"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.json_file_path is None

    def test_json_file_path_found(self, tmp_path):
        """Test json_file_path finds matching JSON file"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        json_file = tmp_path / "test.jpg.json"
        json_file.write_text('{"test": "data"}')
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.json_file_path == str(json_file)

    def test_json_data_property(self, tmp_path):
        """Test json_data property loads JSON content"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        json_file = tmp_path / "test.jpg.json"
        json_file.write_text('{"photoTakenTime": {"timestamp": "1234567890"}}')
        
        media = ConcreteTruMedia(media_path=str(test_file))
        assert media.json_data is not None
        assert "photoTakenTime" in media.json_data


class TestTruMediaDateHandling:
    """Test TruMedia date handling"""

    @patch('organize_pictures.TruMedia.ExifToolHelper')
    def test_date_taken_from_exif(self, mock_exif, tmp_path):
        """Test date_taken extraction from EXIF data"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'DateTimeOriginal': '2024-01-15 10:30:45'
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        media = ConcreteTruMedia(media_path=str(test_file))
        date = media.date_taken
        assert date is not None
        assert isinstance(date, datetime)

    def test_date_taken_setter(self, tmp_path):
        """Test date_taken setter"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        media = ConcreteTruMedia(media_path=str(test_file))
        new_date = datetime(2024, 1, 15, 10, 30, 45)

        with patch.object(media, '_update_tags'):
            media.date_taken = new_date
            assert media._date_taken == new_date


class TestTruMediaDatePriority:
    """Test TruMedia date metadata priority (JSON first, then file metadata)"""

    @patch('organize_pictures.TruMedia.ExifToolHelper')
    def test_json_metadata_takes_priority_over_exif(self, mock_exif, tmp_path, create_test_json):
        """Test that JSON metadata is prioritized over EXIF data"""
        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        # Create JSON file with different date than EXIF
        json_file = tmp_path / "test.jpg.json"
        json_data = {
            "photoTakenTime": {
                "timestamp": "1234567890"  # 2009-02-13 23:31:30 UTC
            }
        }
        create_test_json(json_file, json_data)

        # Mock EXIF data with different date
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'DateTimeOriginal': '2024-01-15 10:30:45'  # Different date
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        # Create media object
        media = ConcreteTruMedia(media_path=str(test_file))
        date = media.date_taken

        # Should use JSON date (2009-02-13), not EXIF date (2024-01-15)
        assert date is not None
        assert date.year == 2009
        assert date.month == 2
        assert date.day == 13

    @patch('organize_pictures.TruMedia.ExifToolHelper')
    def test_exif_used_when_no_json(self, mock_exif, tmp_path):
        """Test that EXIF data is used when no JSON file exists"""
        # Create test file without JSON
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        # Mock EXIF data
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'DateTimeOriginal': '2024-01-15 10:30:45'
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        # Create media object
        media = ConcreteTruMedia(media_path=str(test_file))
        date = media.date_taken

        # Should use EXIF date
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    @patch('organize_pictures.TruMedia.ExifToolHelper')
    def test_exif_used_when_json_has_no_photo_taken_time(self, mock_exif, tmp_path, create_test_json):
        """Test that EXIF data is used when JSON exists but has no photoTakenTime"""
        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        # Create JSON file without photoTakenTime
        json_file = tmp_path / "test.jpg.json"
        json_data = {
            "title": "test.jpg",
            "description": "A test image"
        }
        create_test_json(json_file, json_data)

        # Mock EXIF data
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'DateTimeOriginal': '2024-01-15 10:30:45'
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        # Create media object
        media = ConcreteTruMedia(media_path=str(test_file))
        date = media.date_taken

        # Should use EXIF date since JSON has no photoTakenTime
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    @patch('organize_pictures.TruMedia.ExifToolHelper')
    def test_json_with_invalid_timestamp_falls_back_to_exif(self, mock_exif, tmp_path, create_test_json):
        """Test that invalid JSON timestamp falls back to EXIF data"""
        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        # Create JSON file with invalid timestamp
        json_file = tmp_path / "test.jpg.json"
        json_data = {
            "photoTakenTime": {
                "timestamp": "invalid_timestamp"
            }
        }
        create_test_json(json_file, json_data)

        # Mock EXIF data
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'DateTimeOriginal': '2024-01-15 10:30:45'
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        # Create media object
        media = ConcreteTruMedia(media_path=str(test_file))
        date = media.date_taken

        # Should fall back to EXIF date
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    def test_real_json_file_priority(self, tmp_path, create_test_image, create_test_json):
        """Integration test with real image and JSON file"""
        # Create a real test image
        test_file = tmp_path / "test.jpg"
        create_test_image(test_file)

        # Create JSON file with specific date
        json_file = tmp_path / "test.jpg.json"
        json_data = {
            "photoTakenTime": {
                "timestamp": "1406911518"  # Aug 1, 2014, 4:45:18 PM UTC
            }
        }
        create_test_json(json_file, json_data)

        # Create TruImage (which extends TruMedia)
        from organize_pictures.TruImage import TruImage
        image = TruImage(media_path=str(test_file))

        # Should use JSON date
        date = image.date_taken
        assert date is not None
        assert date.year == 2014
        assert date.month == 8
        assert date.day == 1


class TestTruMediaCopy:
    """Test TruMedia copy functionality"""

    def test_copy_creates_destination_directory(self, tmp_path):
        """Test copy creates destination directory if it doesn't exist"""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")
        dest_dir = tmp_path / "dest"
        
        media = ConcreteTruMedia(media_path=str(test_file))
        dest_info = {
            "dir": str(dest_dir),
            "filename": "newfile",
            "ext": ".jpg"
        }
        
        media.copy(dest_info)
        assert dest_dir.exists()

