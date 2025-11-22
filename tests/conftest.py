"""Pytest configuration and shared fixtures for organize_pictures tests"""
import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from PIL import Image


# Add the parent directory to the path so we can import organize_pictures
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def test_resources_dir():
    """Return path to test resources directory"""
    return Path(__file__).parent / "resources"


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with source and dest directories"""
    workspace = {
        "root": tmp_path,
        "source": tmp_path / "source",
        "dest": tmp_path / "dest",
        "temp": tmp_path / "temp"
    }
    
    # Create directories
    for dir_path in workspace.values():
        if dir_path != workspace["root"]:
            dir_path.mkdir(exist_ok=True)
    
    yield workspace
    
    # Cleanup is automatic with tmp_path


@pytest.fixture
def create_test_image():
    """Factory fixture to create test images"""
    def _create_image(path, size=(100, 100), color='red', format='JPEG'):
        """
        Create a test image file
        
        Args:
            path: Path where to save the image
            size: Tuple of (width, height)
            color: Color name or RGB tuple
            format: Image format (JPEG, PNG, etc.)
        """
        img = Image.new('RGB', size, color=color)
        img.save(path, format=format)
        return path
    
    return _create_image


@pytest.fixture
def create_test_video():
    """Factory fixture to create test video files"""
    def _create_video(path, content=b"fake video data"):
        """
        Create a test video file
        
        Args:
            path: Path where to save the video
            content: Byte content for the fake video
        """
        with open(path, 'wb') as f:
            f.write(content)
        return path
    
    return _create_video


@pytest.fixture
def create_test_json():
    """Factory fixture to create test JSON files"""
    def _create_json(path, data):
        """
        Create a test JSON file
        
        Args:
            path: Path where to save the JSON
            data: Dictionary to write as JSON
        """
        import json
        with open(path, 'w') as f:
            json.dump(data, f)
        return path
    
    return _create_json


@pytest.fixture
def sample_json_data():
    """Return sample JSON data structure"""
    return {
        "photoTakenTime": {
            "timestamp": "1234567890",
            "formatted": "2009-02-13 23:31:30 UTC"
        },
        "geoDataExif": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 10.0
        },
        "people": [
            {"name": "John Doe"},
            {"name": "Jane Smith"}
        ]
    }


@pytest.fixture
def mock_exif_data():
    """Return mock EXIF data structure"""
    return {
        'EXIF:DateTimeOriginal': '2024-01-15 10:30:45',
        'EXIF:CreateDate': '2024-01-15 10:30:45',
        'EXIF:Make': 'Canon',
        'EXIF:Model': 'Canon EOS 5D',
        'File:FileType': 'JPEG',
        'File:MIMEType': 'image/jpeg'
    }


@pytest.fixture
def mock_video_exif_data():
    """Return mock video EXIF data structure"""
    return {
        'QuickTime:CreateDate': '2024-01-15 10:30:45',
        'QuickTime:TrackCreateDate': '2024-01-15 10:30:45',
        'QuickTime:MediaCreateDate': '2024-01-15 10:30:45',
        'QuickTime:Duration': '30.5 s',
        'File:FileType': 'MP4',
        'File:MIMEType': 'video/mp4'
    }


@pytest.fixture(autouse=True)
def cleanup_log_files():
    """Automatically cleanup log files after each test"""
    yield
    
    # Clean up log files
    log_files = [
        'organize_pictures.utils.log',
        'organize_pictures.TruMedia.log',
        'organize_pictures.TruImage.log',
        'organize_pictures.TruVideo.log',
        'organize_pictures.log'
    ]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except:
                pass


@pytest.fixture(autouse=True)
def cleanup_test_db():
    """Automatically cleanup test database files after each test"""
    yield
    
    # Clean up database files
    db_files = ['pictures.db', './pictures.db']
    
    for db_file in db_files:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except:
                pass


def pytest_configure(config):
    """Pytest configuration hook"""
    # Add custom markers
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test items during collection"""
    # Add 'unit' marker to all tests by default unless marked otherwise
    for item in items:
        if not any(marker.name in ['integration', 'slow'] for marker in item.iter_markers()):
            item.add_marker(pytest.mark.unit)

