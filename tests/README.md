# OrganizePictures Test Suite

This directory contains the comprehensive test suite for the OrganizePictures project using pytest.

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and pytest configuration
├── test_utils.py                  # Tests for utils.py module
├── test_trumedia.py              # Tests for TruMedia.py (abstract base class)
├── test_truimage.py              # Tests for TruImage.py
├── test_truvideo.py              # Tests for TruVideo.py
├── test_organize_pictures.py     # Tests for __init__.py (OrganizePictures class)
├── resources/                     # Test resource files (images, videos, JSON)
└── README.md                      # This file
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run tests for a specific module
```bash
pytest tests/test_utils.py
pytest tests/test_truimage.py
pytest tests/test_truvideo.py
pytest tests/test_trumedia.py
pytest tests/test_organize_pictures.py
```

### Run tests with verbose output
```bash
pytest -v
```

### Run tests with coverage report
```bash
pytest --cov=organize_pictures --cov-report=html
```

### Run only unit tests (fast)
```bash
pytest -m unit
```

### Run only integration tests
```bash
pytest -m integration
```

### Run tests excluding slow tests
```bash
pytest -m "not slow"
```

### Run a specific test class
```bash
pytest tests/test_utils.py::TestGetLogger
```

### Run a specific test function
```bash
pytest tests/test_utils.py::TestGetLogger::test_get_logger_returns_logger
```

## Test Categories

### Unit Tests (`test_utils.py`)
- **TestConstants**: Tests for module constants (MEDIA_TYPES, DATE_FORMATS, etc.)
- **TestGetLogger**: Tests for the get_logger function

### Unit Tests (`test_trumedia.py`)
- **TestTruMediaInit**: Tests for TruMedia initialization
- **TestTruMediaProperties**: Tests for TruMedia properties (media_path, ext, hash, etc.)
- **TestTruMediaJsonHandling**: Tests for JSON file handling
- **TestTruMediaDateHandling**: Tests for date extraction and manipulation
- **TestTruMediaCopy**: Tests for copy functionality

### Unit Tests (`test_truimage.py`)
- **TestTruImageInit**: Tests for TruImage initialization
- **TestTruImageProperties**: Tests for TruImage-specific properties
- **TestTruImageValidation**: Tests for image validation logic
- **TestTruImageHash**: Tests for image hash generation
- **TestTruImageOpen**: Tests for opening and displaying images
- **TestTruImageConvert**: Tests for image conversion (HEIC to JPG, etc.)
- **TestTruImageCopy**: Tests for image copying with animations
- **TestTruImageStringRepresentation**: Tests for __str__ and __repr__ methods

### Unit Tests (`test_truvideo.py`)
- **TestTruVideoInit**: Tests for TruVideo initialization
- **TestTruVideoProperties**: Tests for TruVideo-specific properties
- **TestTruVideoValidation**: Tests for video validation and animation detection
- **TestTruVideoHash**: Tests for video hash generation
- **TestTruVideoConvert**: Tests for video conversion (MOV to MP4, etc.)
- **TestTruVideoCopy**: Tests for video copying
- **TestTruVideoStringRepresentation**: Tests for __str__ and __repr__ methods

### Unit Tests (`test_organize_pictures.py`)
- **TestOrganizePicturesInit**: Tests for OrganizePictures initialization
- **TestOrganizePicturesStaticMethods**: Tests for static methods
- **TestOrganizePicturesFileOperations**: Tests for file discovery and media initialization
- **TestOrganizePicturesDatabaseOperations**: Tests for SQLite database operations
- **TestOrganizePicturesGetNewFileInfo**: Tests for destination file path generation
- **TestOrganizePicturesRun**: Tests for the main run() method

## Fixtures

### Shared Fixtures (in `conftest.py`)
- `test_resources_dir`: Path to test resources directory
- `temp_workspace`: Temporary workspace with source/dest directories
- `create_test_image`: Factory to create test images
- `create_test_video`: Factory to create test video files
- `create_test_json`: Factory to create test JSON files
- `sample_json_data`: Sample JSON data structure
- `mock_exif_data`: Mock EXIF data for images
- `mock_video_exif_data`: Mock EXIF data for videos
- `cleanup_log_files`: Auto-cleanup of log files after tests
- `cleanup_test_db`: Auto-cleanup of test database files

### Module-Specific Fixtures
- `sample_image`: Creates a sample JPG image
- `sample_heic_image`: Creates a sample HEIC image
- `sample_video`: Creates a sample MP4 video
- `sample_mov_video`: Creates a sample MOV video
- `temp_dirs`: Creates temporary source/dest directories
- `sample_images`: Creates multiple sample images

## Writing New Tests

When adding new tests, follow these guidelines:

1. **Use descriptive test names**: `test_<what_is_being_tested>`
2. **Organize tests into classes**: Group related tests together
3. **Use fixtures**: Leverage existing fixtures or create new ones in conftest.py
4. **Mock external dependencies**: Use `unittest.mock` for external calls (EXIF tools, ffmpeg, etc.)
5. **Test edge cases**: Include tests for error conditions and boundary cases
6. **Add docstrings**: Document what each test is verifying

Example:
```python
class TestNewFeature:
    """Test new feature functionality"""
    
    def test_feature_with_valid_input(self, fixture_name):
        """Test that feature works with valid input"""
        # Arrange
        input_data = "test"
        
        # Act
        result = function_under_test(input_data)
        
        # Assert
        assert result == expected_value
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines. Ensure all tests pass before merging code.

## Coverage Goals

Aim for:
- **Overall coverage**: >80%
- **Critical paths**: >95%
- **Utility functions**: >90%

## Troubleshooting

### Tests fail with "FileNotFoundError"
- Ensure test resources exist in `tests/resources/`
- Check that fixtures are creating temporary files correctly

### Tests fail with "ModuleNotFoundError"
- Ensure the package is installed: `pip install -e .`
- Check that `conftest.py` is adding the correct path

### Database lock errors
- The `cleanup_test_db` fixture should handle cleanup
- If issues persist, manually delete `pictures.db` files

### Log file conflicts
- The `cleanup_log_files` fixture should handle cleanup
- If issues persist, manually delete `.log` files

## Contributing

When contributing tests:
1. Run the full test suite before submitting
2. Add tests for any new functionality
3. Update this README if adding new test categories
4. Ensure tests are isolated and don't depend on external state

