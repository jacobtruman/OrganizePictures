"""Unit tests for organize_pictures.__init__ module (OrganizePictures class)"""
import os
import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from PIL import Image
from organize_pictures import OrganizePictures
from organize_pictures.TruImage import TruImage
from organize_pictures.TruVideo import TruVideo
from organize_pictures.utils import MEDIA_TYPES, OFFSET_CHARS


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary source and destination directories"""
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()
    return {
        "source": str(source_dir),
        "dest": str(dest_dir),
        "tmp": str(tmp_path)
    }


@pytest.fixture
def sample_images(temp_dirs):
    """Create sample images in source directory"""
    source_dir = temp_dirs["source"]
    images = []
    
    for i in range(3):
        img_path = os.path.join(source_dir, f"test_image_{i}.jpg")
        img = Image.new('RGB', (100, 100), color='red')
        img.save(img_path)
        images.append(img_path)
    
    return images


class TestOrganizePicturesInit:
    """Test OrganizePictures initialization"""

    def test_init_basic(self, temp_dirs):
        """Test basic initialization"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        assert org.source_dir == temp_dirs["source"]
        assert org.dest_dir == temp_dirs["dest"]
        assert org.dry_run is False
        assert org.cleanup is False
        assert org.sub_dirs is True

    def test_init_with_media_type(self, temp_dirs):
        """Test initialization with specific media type"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            media_type="image"
        )
        assert org.media_type == "image"
        assert org.extensions == MEDIA_TYPES.get("image")

    def test_init_with_extensions(self, temp_dirs):
        """Test initialization with custom extensions"""
        custom_exts = ['.jpg', '.png']
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            extensions=custom_exts
        )
        assert org.extensions == custom_exts

    def test_init_with_dry_run(self, temp_dirs):
        """Test initialization with dry_run flag"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            dry_run=True
        )
        assert org.dry_run is True

    def test_init_with_cleanup(self, temp_dirs):
        """Test initialization with cleanup flag"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            cleanup=True
        )
        assert org.cleanup is True

    def test_init_with_offset(self, temp_dirs):
        """Test initialization with custom offset"""
        custom_offset = {'Y': 1, 'M': 2, 'D': 3, 'h': 4, 'm': 5, 's': 6}
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            offset=custom_offset
        )
        assert org.offset == custom_offset

    def test_init_creates_database(self, temp_dirs):
        """Test initialization creates database"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        assert org.db_conn is not None
        assert org.dbc is not None

    def test_init_results_dict(self, temp_dirs):
        """Test initialization creates results dictionary"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        assert "moved" in org.results
        assert "duplicate" in org.results
        assert "failed" in org.results
        assert "manual" in org.results
        assert "invalid" in org.results
        assert "deleted" in org.results


class TestOrganizePicturesStaticMethods:
    """Test OrganizePictures static methods"""

    def test_init_offset(self):
        """Test init_offset static method"""
        offset = OrganizePictures.init_offset()
        assert isinstance(offset, dict)
        assert len(offset) == len(OFFSET_CHARS)
        for char in OFFSET_CHARS:
            assert char in offset
            assert offset[char] == 0

    def test_file_path(self):
        """Test _file_path static method"""
        file_info = {
            "dir": "/test/dir",
            "filename": "testfile",
            "ext": ".jpg"
        }
        result = OrganizePictures._file_path(file_info)
        assert result == "/test/dir/testfile.jpg"


class TestOrganizePicturesFileOperations:
    """Test OrganizePictures file operations"""

    def test_get_file_paths(self, temp_dirs, sample_images):
        """Test _get_file_paths method"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            extensions=['.jpg']
        )
        files = org._get_file_paths(base_dir=temp_dirs["source"])
        assert len(files) == 3
        assert all(f.endswith('.jpg') for f in files)

    def test_get_file_paths_with_extensions(self, temp_dirs):
        """Test _get_file_paths with specific extensions"""
        source_dir = temp_dirs["source"]
        
        # Create files with different extensions
        jpg_path = os.path.join(source_dir, "test.jpg")
        png_path = os.path.join(source_dir, "test.png")
        txt_path = os.path.join(source_dir, "test.txt")
        
        Image.new('RGB', (100, 100)).save(jpg_path)
        Image.new('RGB', (100, 100)).save(png_path)
        with open(txt_path, 'w') as f:
            f.write("test")
        
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            extensions=['.jpg', '.png']
        )
        files = org._get_file_paths(base_dir=source_dir)
        assert len(files) == 2
        assert any(f.endswith('.jpg') for f in files)
        assert any(f.endswith('.png') for f in files)
        assert not any(f.endswith('.txt') for f in files)

    def test_init_media_file_image(self, temp_dirs):
        """Test _init_media_file with image"""
        img_path = os.path.join(temp_dirs["source"], "test.jpg")
        img = Image.new('RGB', (100, 100))
        img.save(img_path)
        
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                media = org._init_media_file(img_path)
                assert isinstance(media, TruImage)

    def test_init_media_file_video(self, temp_dirs):
        """Test _init_media_file with video"""
        video_path = os.path.join(temp_dirs["source"], "test.mp4")
        with open(video_path, 'wb') as f:
            f.write(b"fake video data")
        
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                media = org._init_media_file(video_path)
                assert isinstance(media, TruVideo)


class TestOrganizePicturesDatabaseOperations:
    """Test OrganizePictures database operations"""

    def test_insert_media_hash(self, temp_dirs):
        """Test _insert_media_hash method"""
        img_path = os.path.join(temp_dirs["source"], "test.jpg")
        img = Image.new('RGB', (100, 100))
        img.save(img_path)
        
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        
        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                result = org._insert_media_hash(img_path)
                assert result is True

    def test_check_db_for_media_hash(self, temp_dirs):
        """Test _check_db_for_media_hash method"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )
        
        # Insert a test hash
        test_hash = "test_hash_123"
        test_path = "/test/path.jpg"
        org.dbc.execute(
            f'INSERT INTO image_hashes VALUES ("{test_path}", "{test_hash}")'
        )
        
        result = org._check_db_for_media_hash(test_hash)
        assert isinstance(result, dict)
        assert test_path in result


class TestOrganizePicturesGetNewFileInfo:
    """Test OrganizePictures _get_new_fileinfo method"""

    @patch('exiftool.ExifToolHelper')
    def test_get_new_fileinfo(self, mock_exif, temp_dirs):
        """Test _get_new_fileinfo generates correct file info"""
        img_path = os.path.join(temp_dirs["source"], "test.jpg")
        img = Image.new('RGB', (100, 100))
        img.save(img_path)

        # Mock EXIF data
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'EXIF:DateTimeOriginal': '2024-01-15 10:30:45'
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            sub_dirs=True
        )

        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                media = TruImage(media_path=img_path, logger=org.logger)
                media._date_taken = datetime(2024, 1, 15, 10, 30, 45)

                file_info = org._get_new_fileinfo(media)

                assert "dir" in file_info
                assert "filename" in file_info
                assert "ext" in file_info
                assert "2024" in file_info["dir"]
                assert "Jan" in file_info["dir"]


class TestOrganizePicturesRun:
    """Test OrganizePictures run method"""

    @patch('exiftool.ExifToolHelper')
    def test_run_basic(self, mock_exif, temp_dirs):
        """Test basic run operation"""
        # Create test image
        img_path = os.path.join(temp_dirs["source"], "test.jpg")
        img = Image.new('RGB', (100, 100))
        img.save(img_path)

        # Mock EXIF data
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{
            'EXIF:DateTimeOriginal': '2024-01-15 10:30:45'
        }]
        mock_exif.return_value.__enter__.return_value = mock_eth

        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            media_type="image"
        )

        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                with patch.object(TruImage, 'date_taken', datetime(2024, 1, 15, 10, 30, 45)):
                    results = org.run()

                    assert isinstance(results, dict)
                    assert "moved" in results
                    assert "duplicate" in results
                    assert "failed" in results

    def test_run_returns_results(self, temp_dirs):
        """Test run returns results dictionary"""
        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"]
        )

        results = org.run()
        assert isinstance(results, dict)
        assert all(key in results for key in ["moved", "duplicate", "failed", "manual", "invalid", "deleted"])

    @patch('exiftool.ExifToolHelper')
    def test_run_increments_failed_when_date_taken_is_none(self, mock_exif, temp_dirs):
        """Test that files without date_taken are counted as failed"""
        # Create test image
        img_path = os.path.join(temp_dirs["source"], "test.jpg")
        img = Image.new('RGB', (100, 100))
        img.save(img_path)

        # Mock EXIF data to return no date information
        mock_eth = MagicMock()
        mock_eth.get_metadata.return_value = [{}]  # No date fields
        mock_exif.return_value.__enter__.return_value = mock_eth

        org = OrganizePictures(
            source_directory=temp_dirs["source"],
            destination_directory=temp_dirs["dest"],
            media_type="image"
        )

        with patch('organize_pictures.TruImage.TruImage._reconcile_mime_type'):
            with patch('organize_pictures.TruImage.TruImage._write_json_data_to_media'):
                with patch.object(TruImage, 'date_taken', new_callable=PropertyMock) as mock_date:
                    mock_date.return_value = None  # Simulate no date found
                    results = org.run()

                    # Should increment failed counter
                    assert results['failed'] == 1
                    assert results['moved'] == 0

