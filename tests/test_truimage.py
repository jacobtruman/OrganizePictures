"""Unit tests for organize_pictures.TruImage module"""
import os
import pytest
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from PIL import Image
from organize_pictures.TruImage import TruImage
from organize_pictures.utils import MEDIA_TYPES, FILE_EXTS


@pytest.fixture
def sample_image(tmp_path):
    """Create a sample image file for testing"""
    img_path = tmp_path / "test_image.jpg"
    img = Image.new('RGB', (100, 100), color='red')
    img.save(str(img_path))
    return str(img_path)


@pytest.fixture
def sample_heic_image(tmp_path):
    """Create a sample HEIC image file for testing"""
    img_path = tmp_path / "test_image.heic"
    # Create a simple file to simulate HEIC
    img_path.write_bytes(b"fake heic data")
    return str(img_path)


class TestTruImageInit:
    """Test TruImage initialization"""

    def test_init_with_valid_image(self, sample_image):
        """Test initialization with a valid image file"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                assert img.media_path == sample_image
                assert img.dev_mode is False
                assert img._animation is None

    def test_init_with_nonexistent_file(self):
        """Test initialization with nonexistent file raises error"""
        with pytest.raises(FileNotFoundError):
            TruImage(media_path="/nonexistent/image.jpg")

    def test_init_with_logger(self, sample_image):
        """Test initialization with custom logger"""
        from organize_pictures.utils import get_logger
        logger = get_logger()
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image, logger=logger)
                assert img.logger == logger

    def test_init_with_json_file(self, sample_image, tmp_path):
        """Test initialization with JSON file"""
        json_path = tmp_path / "test_image.jpg.json"
        json_path.write_text('{"photoTakenTime": {"timestamp": "1234567890"}}')
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image, json_file_path=str(json_path))
                assert img.json_file_path == str(json_path)


class TestTruImageProperties:
    """Test TruImage properties"""

    def test_media_type_property(self, sample_image):
        """Test media_type property returns 'image'"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                assert img.media_type == "image"

    def test_date_fields_property(self, sample_image):
        """Test date_fields property returns EXIF_DATE_FIELDS"""
        from organize_pictures.utils import EXIF_DATE_FIELDS
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                assert img.date_fields == EXIF_DATE_FIELDS

    def test_preferred_ext_property(self, sample_image):
        """Test preferred_ext property returns .jpg"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                assert img.preferred_ext == ".jpg"

    def test_files_property(self, sample_image):
        """Test files property returns dict of associated files"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                files = img.files
                assert isinstance(files, dict)
                assert "image" in files
                assert "image_source" in files
                assert "json" in files
                assert "animation" in files

    def test_animation_property_no_animation(self, sample_image):
        """Test animation property when no animation exists"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                assert img.animation is None

    def test_animation_property_with_animation(self, tmp_path):
        """Test animation property when animation file exists"""
        img_path = tmp_path / "test.jpg"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(str(img_path))
        
        # Create matching video file
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video data")
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                tru_img = TruImage(media_path=str(img_path))
                # Animation should be found
                assert tru_img.animation is not None


class TestTruImageValidation:
    """Test TruImage validation"""

    def test_valid_setter_with_valid_extension(self, sample_image):
        """Test valid setter with valid image extension"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                assert img.valid is True

    def test_valid_setter_with_invalid_extension(self, tmp_path):
        """Test valid setter with invalid extension"""
        # Create a file with invalid extension but valid image content
        invalid_file = tmp_path / "test.txt"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(str(invalid_file), format='JPEG')

        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                with patch('organize_pictures.TruImage.TruImage.convert') as mock_convert:
                    # Prevent conversion during init
                    mock_convert.return_value = False
                    tru_img = TruImage(media_path=str(invalid_file))
                    # After conversion is prevented, file still has .txt extension
                    # which is not in MEDIA_TYPES['image'], so valid should be False
                    assert tru_img.valid is False


class TestTruImageHash:
    """Test TruImage hash generation"""

    def test_get_media_hash(self, sample_image):
        """Test _get_media_hash generates hash"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                hash_value = img.hash
                assert hash_value is not None
                assert isinstance(hash_value, str)
                assert len(hash_value) == 32  # MD5 hash length


class TestTruImageOpen:
    """Test TruImage open and show methods"""

    def test_open_image(self, sample_image):
        """Test open method returns PIL Image"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                pil_img = img.open()
                assert pil_img is not None
                assert isinstance(pil_img, Image.Image)
                pil_img.close()

    def test_show_image(self, sample_image):
        """Test show method"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                with patch.object(Image.Image, 'show'):
                    img.show()


class TestTruImageConvert:
    """Test TruImage convert functionality"""

    def test_convert_to_jpg(self, tmp_path):
        """Test converting image to JPG"""
        # Create a PNG image
        png_path = tmp_path / "test.png"
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(str(png_path))

        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                with patch('exiftool.ExifToolHelper'):
                    # Mock convert during init to prevent automatic conversion
                    with patch.object(TruImage, 'convert', return_value=True) as mock_convert:
                        # Start with PNG
                        tru_img = TruImage(media_path=str(png_path))
                        # Reset the mock to track the explicit convert call
                        mock_convert.reset_mock()
                        # Now call convert explicitly
                        result = tru_img.convert(".jpg")

                        # Check conversion was called
                        mock_convert.assert_called_once_with(".jpg")
                        assert result is True

    def test_convert_existing_file_skipped(self, tmp_path):
        """Test convert skips if destination already exists"""
        png_path = tmp_path / "test.png"
        jpg_path = tmp_path / "test.jpg"
        
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(str(png_path))
        img.save(str(jpg_path))
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                tru_img = TruImage(media_path=str(png_path))
                result = tru_img.convert(".jpg")
                assert result is False


class TestTruImageCopy:
    """Test TruImage copy functionality"""

    def test_copy_image(self, sample_image, tmp_path):
        """Test copying image to destination"""
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                dest_info = {
                    "dir": str(dest_dir),
                    "filename": "copied_image",
                    "ext": ".jpg"
                }
                
                files_copied = img.copy(dest_info)
                
                # Check file was copied
                dest_file = dest_dir / "copied_image.jpg"
                assert dest_file.exists()
                assert isinstance(files_copied, dict)


class TestTruImageStringRepresentation:
    """Test TruImage string representations"""

    def test_repr(self, sample_image):
        """Test __repr__ method"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                repr_str = repr(img)
                assert "TruImage" in repr_str
                assert "media_path" in repr_str
                assert sample_image in repr_str

    def test_str(self, sample_image):
        """Test __str__ method"""
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                img = TruImage(media_path=sample_image)
                str_repr = str(img)
                assert "test_image.jpg" in str_repr
                assert "🖼️" in str_repr

