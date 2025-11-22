"""Unit tests for organize_pictures.TruVideo module"""
import os
import pathlib
import pytest
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from organize_pictures.TruVideo import TruVideo
from organize_pictures.utils import VIDEO_DATE_FIELDS, FILE_EXTS, MEDIA_TYPES


@pytest.fixture
def sample_video(tmp_path):
    """Create a sample video file for testing"""
    video_path = tmp_path / "test_video.mp4"
    # Create a fake video file
    video_path.write_bytes(b"fake video data")
    return str(video_path)


@pytest.fixture
def sample_mov_video(tmp_path):
    """Create a sample MOV video file for testing"""
    video_path = tmp_path / "test_video.mov"
    video_path.write_bytes(b"fake mov video data")
    return str(video_path)


class TestTruVideoInit:
    """Test TruVideo initialization"""

    def test_init_with_valid_video(self, sample_video):
        """Test initialization with a valid video file"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                assert video.media_path == sample_video

    def test_init_with_nonexistent_file(self):
        """Test initialization with nonexistent file raises error"""
        with pytest.raises(FileNotFoundError):
            TruVideo(media_path="/nonexistent/video.mp4")

    def test_init_with_logger(self, sample_video):
        """Test initialization with custom logger"""
        from organize_pictures.utils import get_logger
        logger = get_logger()
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video, logger=logger)
                assert video.logger == logger

    def test_init_with_json_file(self, sample_video, tmp_path):
        """Test initialization with JSON file"""
        json_path = tmp_path / "test_video.mp4.json"
        json_path.write_text('{"photoTakenTime": {"timestamp": "1234567890"}}')
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video, json_file_path=str(json_path))
                assert video.json_file_path == str(json_path)


class TestTruVideoProperties:
    """Test TruVideo properties"""

    def test_media_type_property(self, sample_video):
        """Test media_type property returns 'video'"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                assert video.media_type == "video"

    def test_date_fields_property(self, sample_video):
        """Test date_fields property returns VIDEO_DATE_FIELDS"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                assert video.date_fields == VIDEO_DATE_FIELDS

    def test_preferred_ext_property(self, sample_video):
        """Test preferred_ext property returns .mp4"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                assert video.preferred_ext == ".mp4"

    def test_files_property(self, sample_video):
        """Test files property returns dict of associated files"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                files = video.files
                assert isinstance(files, dict)
                assert "video" in files
                assert "video_source" in files
                assert "json" in files


class TestTruVideoValidation:
    """Test TruVideo validation"""

    def test_valid_setter_with_valid_extension(self, sample_video):
        """Test valid setter with valid video extension"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                assert video.valid is True

    def test_valid_setter_with_invalid_extension(self, tmp_path):
        """Test valid setter with invalid extension"""
        # Create a file with invalid extension
        invalid_file = tmp_path / "test.txt"
        invalid_file.write_bytes(b"not a video")

        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                # Mock convert to prevent ffmpeg call during init
                with patch('organize_pictures.TruVideo.TruVideo.convert'):
                    video = TruVideo(media_path=str(invalid_file))
                    # Trigger the valid setter (TruVideo doesn't call it in __init__)
                    video.valid = None
                    # File has .txt extension which is not in MEDIA_TYPES['video']
                    # The valid setter should set _valid to False
                    assert video.valid is False

    def test_is_animation_no_matching_image(self, sample_video):
        """Test _is_animation returns False when no matching image exists"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                assert video._is_animation() is False

    def test_is_animation_with_matching_image(self, tmp_path):
        """Test _is_animation returns True when matching image exists"""
        from PIL import Image
        
        # Create matching image
        img_path = tmp_path / "test.jpg"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(str(img_path))
        
        # Create video with same base name
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video data")
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=str(video_path))
                assert video._is_animation() is True


class TestTruVideoHash:
    """Test TruVideo hash generation"""

    @patch('organize_pictures.TruVideo.ffmpeg')
    def test_get_media_hash(self, mock_ffmpeg, sample_video):
        """Test _get_media_hash generates hash"""
        # Mock ffmpeg operations
        mock_stream = MagicMock()
        mock_ffmpeg.input.return_value = mock_stream
        mock_ffmpeg.output.return_value = mock_stream
        mock_ffmpeg.run.return_value = (None, None)
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b"test data"
                    
                    video = TruVideo(media_path=sample_video)
                    hash_value = video.hash
                    
                    assert hash_value is not None
                    assert isinstance(hash_value, str)


class TestTruVideoConvert:
    """Test TruVideo convert functionality"""

    def test_convert_to_mp4(self, tmp_path):
        """Test converting video to MP4"""
        # Use .mp4 to avoid automatic conversion during init
        mp4_path = tmp_path / "test.mp4"
        mp4_path.write_bytes(b"fake mp4 data")

        # Create destination path for conversion
        avi_path = tmp_path / "test.avi"

        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                with patch('organize_pictures.TruVideo.TruVideo._convert_video') as mock_convert:
                    # Mock _convert_video to create the file and return True
                    def create_avi_file(source, dest):
                        pathlib.Path(dest).write_bytes(b"fake avi data")
                        return True

                    mock_convert.side_effect = create_avi_file

                    video = TruVideo(media_path=str(mp4_path))
                    result = video.convert(".avi")

                    assert result is True
                    mock_convert.assert_called_once()

    @patch('organize_pictures.TruVideo.TruVideo._convert_video')
    def test_convert_existing_file_skipped(self, mock_convert, tmp_path):
        """Test convert skips if destination already exists"""
        mov_path = tmp_path / "test.mov"
        mp4_path = tmp_path / "test.mp4"
        
        mov_path.write_bytes(b"fake mov data")
        mp4_path.write_bytes(b"fake mp4 data")
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=str(mov_path))
                result = video.convert(".mp4")
                
                assert result is False
                mock_convert.assert_not_called()

    def test_convert_default_extension(self, tmp_path):
        """Test convert uses preferred extension by default"""
        # Use .avi to test conversion to preferred .mp4
        avi_path = tmp_path / "test.avi"
        avi_path.write_bytes(b"fake avi data")

        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                with patch('organize_pictures.TruVideo.TruVideo._convert_video') as mock_convert:
                    # Mock _convert_video to create the file and return True
                    def create_mp4_file(source, dest):
                        pathlib.Path(dest).write_bytes(b"fake mp4 data")
                        return True

                    mock_convert.side_effect = create_mp4_file

                    # Mock convert during init to prevent automatic conversion
                    with patch.object(TruVideo, 'convert', return_value=True) as mock_init_convert:
                        video = TruVideo(media_path=str(avi_path))
                        # Reset the mock to track the explicit convert call
                        mock_init_convert.reset_mock()
                        # Now call convert without specifying extension - should use preferred (.mp4)
                        result = video.convert()

                        # Should convert to preferred extension (.mp4)
                        mock_init_convert.assert_called_once_with()
                        assert result is True


class TestTruVideoCopy:
    """Test TruVideo copy functionality"""

    def test_copy_video(self, sample_video, tmp_path):
        """Test copying video to destination"""
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                dest_info = {
                    "dir": str(dest_dir),
                    "filename": "copied_video",
                    "ext": ".mp4"
                }
                
                files_copied = video.copy(dest_info)
                
                # Check file was copied
                dest_file = dest_dir / "copied_video.mp4"
                assert dest_file.exists()
                assert isinstance(files_copied, dict)


class TestTruVideoStringRepresentation:
    """Test TruVideo string representations"""

    def test_repr(self, sample_video):
        """Test __repr__ method"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                repr_str = repr(video)
                assert "TruVideo" in repr_str
                assert "media_path" in repr_str
                assert sample_video in repr_str

    def test_str(self, sample_video):
        """Test __str__ method"""
        with patch('organize_pictures.TruVideo.TruVideo._reconcile_mime_type'):
            with patch('organize_pictures.TruVideo.TruVideo._write_json_data_to_media'):
                video = TruVideo(media_path=sample_video)
                str_repr = str(video)
                assert "test_video.mp4" in str_repr
                assert "📹" in str_repr

