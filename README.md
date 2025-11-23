# OrganizePictures

A Python tool for organizing photos and videos into folders by date, with intelligent EXIF/metadata handling, duplicate detection, and format conversion capabilities.

## Features

- **Automatic Organization**: Organizes images and videos into date-based folder structures (YYYY/Month)
- **Smart Date Detection**: Extracts dates from EXIF data, video metadata, JSON sidecar files, or filenames
- **Duplicate Detection**: Uses SHA-256 hashing and SQLite database to prevent duplicate files
- **Format Conversion**:
  - Converts HEIC images to JPG
  - Converts various video formats (MPG, MOV, M4V, MTS, MKV) to MP4
  - Converts GIF animations to MP4
- **Metadata Preservation**: Maintains and updates EXIF/metadata during conversions
- **Google Photos Support**: Reads metadata from Google Photos JSON export files
- **Time Offset Adjustment**: Apply time offsets to correct camera timezone issues
- **Flexible Filtering**: Process specific file types or extensions
- **Dry Run Mode**: Preview operations without making changes

## Supported Formats

### Images
- JPG/JPEG
- PNG
- HEIC (converted to JPG)

### Videos
- MP4
- MPG (converted to MP4)
- MOV (converted to MP4)
- M4V (converted to MP4)
- MTS (converted to MP4)
- MKV (converted to MP4)

## Installation

### Prerequisites
- Python 3.11 or higher
- ExifTool (must be installed separately)
- FFmpeg (for video conversion)

### Install from PyPI

#### Using pip
```bash
pip install OrganizePictures
```

#### Using uv tool (Recommended)
[uv](https://github.com/astral-sh/uv) can install Python tools in isolated environments, making them available globally without affecting your system Python or other projects.

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install OrganizePictures as a tool
uv tool install OrganizePictures

# The commands are now available globally
organizepictures --help
truexif --help
trugiftomp4 --help
```

**Benefits of using `uv tool install`:**
- Isolated environment: No dependency conflicts with other projects
- Global availability: Commands work from any directory
- Easy updates: `uv tool upgrade OrganizePictures`
- Easy removal: `uv tool uninstall OrganizePictures`

**Managing the tool:**
```bash
# Upgrade to the latest version
uv tool upgrade OrganizePictures

# List installed tools
uv tool list

# Uninstall the tool
uv tool uninstall OrganizePictures
```

### Install from Source

#### Using uv tool (Install as global tool from source)
```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/jacobtruman/OrganizePictures.git
cd OrganizePictures

# Install as a tool from the local directory
uv tool install .

# The commands are now available globally
organizepictures --help
```

#### Using uv sync (For development)
[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver.

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup the project
git clone https://github.com/jacobtruman/OrganizePictures.git
cd OrganizePictures
uv sync

# Run commands using uv run
uv run organizepictures --help
```

This will create a virtual environment in `.venv` and install all dependencies with their exact versions from `uv.lock`.

#### Using pip
```bash
git clone https://github.com/jacobtruman/OrganizePictures.git
cd OrganizePictures
pip install -e .
```

### Installing ExifTool

**macOS:**
```bash
brew install exiftool
```

**Linux:**
```bash
sudo apt-get install libimage-exiftool-perl
```

**Windows:**
Download from [ExifTool website](https://exiftool.org/)

### Installing FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
Download from [FFmpeg website](https://ffmpeg.org/download.html)

## Usage

### Command Line Tools

The package provides three command-line tools:

#### 1. organizepictures

Main tool for organizing photos and videos by date.

```bash
organizepictures [OPTIONS]
```

**Options:**
- `-s, --source_dir PATH`: Source directory containing media files (default: `./pictures`)
- `-d, --destination_dir PATH`: Destination directory for organized files (default: `./pictures/renamed`)
- `-e, --extensions EXT1,EXT2`: Comma-separated list of file extensions to process
- `-t, --media_type TYPE`: Filter by media type (`image` or `video`)
- `-c, --cleanup`: Delete source files after successful organization
- `-b, --sub_dirs`: Create year/month subdirectories (YYYY/Month format)
- `-o, --offset OFFSET`: Time offset in format `0Y0M0D0h0m0s` (e.g., `5h30m` for 5 hours 30 minutes)
- `-m, --minus`: Subtract the offset instead of adding it
- `-v, --verbose`: Enable verbose logging

**Examples:**

Organize all media files with year/month subdirectories:
```bash
organizepictures -s ~/Downloads/photos -d ~/Pictures/Organized -b
```

Process only images with cleanup:
```bash
organizepictures -s ~/Downloads -d ~/Pictures -t image -c -b
```

Apply 5-hour time offset (fix timezone):
```bash
organizepictures -s ~/photos -d ~/organized -o 5h -b
```

Process only specific extensions:
```bash
organizepictures -s ~/photos -d ~/organized -e jpg,png,mp4 -b
```

#### 2. truexif

Display EXIF data from image files.

```bash
truexif IMAGE_PATH [OPTIONS]
```

**Options:**
- `-t, --tags TAG1,TAG2`: Display only specific tags
- `-d, --decode`: Decode EXIF data to UTF-8

**Examples:**

Show all EXIF data:
```bash
truexif photo.jpg
```

Show specific tags:
```bash
truexif photo.jpg -t datetimeoriginal,model
```

Show decoded EXIF data:
```bash
truexif photo.jpg -d
```

#### 3. trugiftomp4

Convert GIF files to MP4 format with metadata preservation.

```bash
trugiftomp4 GIF_PATH [OPTIONS]
```

**Options:**
- `-d, --date DATE`: Set creation date for the video
- `-p, --pattern PATTERN`: Date pattern (e.g., `%Y-%m-%d %H:%M:%S`)
- `-c, --cleanup`: Remove source GIF after successful conversion
- `-v, --verbose`: Enable verbose output

**Examples:**

Convert GIF to MP4:
```bash
trugiftomp4 animation.gif
```

Convert with specific date:
```bash
trugiftomp4 animation.gif -d "2024-01-15 14:30:00" -p "%Y-%m-%d %H:%M:%S"
```

Convert and cleanup:
```bash
trugiftomp4 animation.gif -c
```

### Python API

You can also use OrganizePictures as a Python library:

```python
from organize_pictures import OrganizePictures

# Create organizer instance
organizer = OrganizePictures(
    source_directory="/path/to/source",
    destination_directory="/path/to/destination",
    media_type="image",  # or "video", or None for both
    cleanup=False,
    sub_dirs=True,
    verbose=True
)

# Run organization
results = organizer.run()

# Check results
print(f"Moved: {results['moved']}")
print(f"Duplicates: {results['duplicate']}")
print(f"Failed: {results['failed']}")
```

### Working with Individual Files

```python
from organize_pictures.TruImage import TruImage
from organize_pictures.TruVideo import TruVideo

# Process an image
image = TruImage("/path/to/photo.jpg")
if image.valid:
    print(f"Date taken: {image.date_taken}")
    print(f"Hash: {image.hash}")

    # Copy to new location
    image.copy({
        "dir": "/destination/path",
        "filename": "new_name",
        "ext": ".jpg"
    })

# Process a video
video = TruVideo("/path/to/video.mov")
if video.valid:
    print(f"Date taken: {video.date_taken}")

    # Convert to MP4
    video.convert(".mp4")
```

## How It Works

1. **File Discovery**: Scans source directory for media files
2. **Validation**: Checks file types and validates media files
3. **Date Extraction**: Attempts to find creation date from:
   - EXIF data (for images)
   - Video metadata (QuickTime, Matroska, etc.)
   - Google Photos JSON sidecar files
   - Filename patterns
4. **Duplicate Detection**: Calculates SHA-256 hash and checks SQLite database
5. **Format Conversion**: Converts files to preferred formats if needed
6. **Organization**: Copies/moves files to destination with date-based naming
7. **Cleanup**: Optionally removes source files after successful processing

## File Naming Convention

Organized files are named using the format:
```
YYYY-MM-DD_HH'MM'SS.ext
```

Example: `2024-01-15_14'30'45.jpg`

If subdirectories are enabled (`-b` flag), files are organized as:
```
YYYY/Month/YYYY-MM-DD_HH'MM'SS.ext
```

Example: `2024/Jan/2024-01-15_14'30'45.jpg`

## Database

OrganizePictures maintains a SQLite database (`pictures.db`) to track processed files and prevent duplicates. The database stores:
- File paths
- SHA-256 hashes
- Processing timestamps

## Google Photos Integration

When exporting from Google Photos, you'll get JSON files alongside your media files. OrganizePictures automatically:
- Detects JSON sidecar files
- Extracts metadata (date, location, description)
- Writes metadata to EXIF/video metadata
- Preserves JSON files alongside organized media

## Time Offset Feature

Useful for correcting timezone issues or camera clock errors:

```bash
# Add 5 hours and 30 minutes
organizepictures -s ~/photos -d ~/organized -o 5h30m -b

# Subtract 2 hours
organizepictures -s ~/photos -d ~/organized -o 2h -m -b

# Complex offset: 1 day, 3 hours, 15 minutes
organizepictures -s ~/photos -d ~/organized -o 1D3h15m -b
```

Offset format: `[Y]Y[M]M[D]D[h]h[m]m[s]s`
- Y = Years
- M = Months
- D = Days
- h = hours
- m = minutes
- s = seconds

## Development

### Running Tests

```bash
pytest test_media_files.py
```

### Project Structure

```
OrganizePictures/
├── organize_pictures/
│   ├── __init__.py          # Main OrganizePictures class
│   ├── TruMedia.py          # Abstract base class for media files
│   ├── TruImage.py          # Image handling class
│   ├── TruVideo.py          # Video handling class
│   ├── utils.py             # Utility functions and constants
│   └── scripts/
│       ├── organizepictures.py  # CLI for organizing media
│       ├── truexif.py           # CLI for EXIF viewing
│       └── trugiftomp4.py       # CLI for GIF conversion
├── tests/                   # Test files and fixtures
├── test_media_files.py      # Pytest test suite
├── gui.py                   # GUI for finding duplicate images
└── pyproject.toml           # Project configuration
```

## Additional Tools

### Duplicate Image Finder (GUI)

The project includes a GUI tool for finding and removing duplicate images using visual comparison:

```bash
python gui.py /path/to/images
```

This tool:
- Compares images visually using perceptual hashing
- Shows side-by-side comparison with difference visualization
- Allows interactive selection of duplicates to delete

## Troubleshooting

### ExifTool not found
Ensure ExifTool is installed and in your PATH. Test with:
```bash
exiftool -ver
```

### FFmpeg not found
Ensure FFmpeg is installed and in your PATH. Test with:
```bash
ffmpeg -version
```

### Permission errors
Ensure you have read permissions for source files and write permissions for destination directory.

### Date not detected
If dates aren't being detected:
1. Check if files have EXIF/metadata: `truexif yourfile.jpg`
2. Ensure filenames follow a recognizable date pattern
3. For Google Photos exports, ensure JSON files are present

## Development

### Setting up Development Environment

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable dependency management.

```bash
# Clone the repository
git clone https://github.com/jacobtruman/OrganizePictures.git
cd OrganizePictures

# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Git hooks (auto-bumps version on commit)
./setup-hooks.sh

# Sync dependencies (creates .venv and installs packages)
uv sync

# Or sync with development dependencies (includes pytest, pytest-cov)
uv sync --all-extras

# Activate the virtual environment (optional - uv run works without activation)
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

### Common Development Commands

```bash
# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Update dependencies
uv sync --upgrade

# Run tests
uv run pytest

# Run a script with uv
uv run python organize_pictures/scripts/organizepictures.py

# Run the installed CLI tools
uv run organizepictures --help
uv run truexif --help
uv run trugiftomp4 --help
```

### Why uv?

- **Fast**: 10-100x faster than pip
- **Reliable**: Deterministic dependency resolution with `uv.lock`
- **Compatible**: Works with existing `pyproject.toml` and `requirements.txt`
- **Modern**: Built in Rust with best practices

### Git Hooks

This project includes Git hooks for automated version management:

#### Automatic Version Bumping

The `pre-commit` hook automatically increments the patch version in `pyproject.toml` with each commit.

**Setup:**
```bash
./setup-hooks.sh
```

**Example:**
```bash
# Before commit: version = '1.0.11'
git commit -m "Add new feature"
# After commit: version = '1.0.12'
```

**Skip version bump for a specific commit:**
```bash
git commit --no-verify -m "Documentation update"
```

**Manual version changes:**
If you manually update the major or minor version (e.g., `1.0.11` → `2.0.0`), the hook will continue bumping the patch version from there (next commit: `2.0.1`).

See `hooks/README.md` for more details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source. See the repository for license details.

## Author

Jacob Truman (jacob.truman@gmail.com)

## Links

- **Homepage**: https://github.com/jacobtruman/OrganizePictures
- **Repository**: https://github.com/jacobtruman/OrganizePictures
- **Issues**: https://github.com/jacobtruman/OrganizePictures/issues