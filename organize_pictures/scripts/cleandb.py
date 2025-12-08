#!/usr/bin/env python
"""
Database cleanup utility for organizing pictures.

This script provides various operations to maintain consistency between
the image database and the filesystem.
"""

import argparse
import atexit
import builtins
import os
import pathlib
import sqlite3
import sys
from glob import glob
from typing import Dict, List, Optional

from pillow_heif import register_heif_opener

from organize_pictures.TruImage import TruImage
from organize_pictures.utils import MEDIA_TYPES


# Constants
TABLE_NAME = "image_hashes"
DEFAULT_BASE_DIR = "/raid/media/Pictures"
DEFAULT_DB_PATHS = ["/raid2/pictures.db", "./pictures.db"]
MAX_FILES_PER_BATCH = 450


def _print(*args, **kwargs):
    """Print with automatic stdout flush."""
    builtins.print(*args, **kwargs)
    sys.stdout.flush()


print = _print


class DatabaseCleaner:
    """Handles database cleanup operations for image organization."""

    def __init__(self, db_path: str, base_dir: str):
        """
        Initialize the database cleaner.

        Args:
            db_path: Path to the SQLite database file
            base_dir: Base directory for image files
        """
        self.db_path = db_path
        self.base_dir = base_dir
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None

        self._connect()
        atexit.register(self.close)

    def _connect(self):
        """Establish database connection."""
        if not os.path.isfile(self.db_path):
            raise FileNotFoundError(f"Database file '{self.db_path}' not found")

        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def close(self):
        """Commit changes and close database connection."""
        if self.conn:
            print("EXIT: Committing final records")
            self.conn.commit()
            self.conn.close()
            self.conn = None
            self.cursor = None

    def restart_script(self):
        """Restart the script (useful for batch processing)."""
        self.close()
        print("RESTARTING")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def get_records(self) -> Dict[str, str]:
        """
        Get all database records for images in the base directory.

        Returns:
            Dictionary mapping image paths to their hashes
        """
        sql = "SELECT * FROM {} WHERE image_path LIKE ?".format(TABLE_NAME)
        pattern = f"{self.base_dir}%"
        return dict(self.cursor.execute(sql, (pattern,)).fetchall())

    def remove_record(self, image_path: str):
        """
        Remove a record from the database.

        Args:
            image_path: Path to the image file
        """
        sql = f"DELETE FROM {TABLE_NAME} WHERE image_path = ?"
        print(f"Removing record: {image_path}")
        self.cursor.execute(sql, (image_path,))

    def update_record_path(self, old_path: str, new_path: str):
        """
        Update the path of a record in the database.

        Args:
            old_path: Current image path
            new_path: New image path
        """
        sql = f"UPDATE {TABLE_NAME} SET image_path = ? WHERE image_path = ?"
        print(f"Updating record: {old_path} -> {new_path}")
        self.cursor.execute(sql, (new_path, old_path))

    def insert_image_hash(self, image: TruImage) -> bool:
        """
        Insert an image hash into the database.

        Args:
            image: TruImage instance

        Returns:
            True if inserted successfully, False otherwise
        """
        if image.hash is None:
            return False

        sql = f"INSERT INTO {TABLE_NAME} VALUES (?, ?)"
        self.cursor.execute(sql, (image.media_path, image.hash))
        return True

    def update_image_hash(self, image: TruImage) -> bool:
        """
        Update an image hash in the database.

        Args:
            image: TruImage instance

        Returns:
            True if updated successfully, False otherwise
        """
        if image.hash is None:
            return False

        sql = f"UPDATE {TABLE_NAME} SET hash = ? WHERE image_path = ?"
        print(f"Updating record: {image.media_path}: {image.hash}")
        self.cursor.execute(sql, (image.hash, image.media_path))
        return True

    def get_image_paths(self, pattern: str = "**/*", recursive: bool = True) -> List[str]:
        """
        Get all image file paths in the base directory.

        Args:
            pattern: Glob pattern for file matching
            recursive: Whether to search recursively

        Returns:
            List of absolute image file paths
        """
        return [
            os.path.abspath(file)
            for file in sorted(glob(f"{self.base_dir}/{pattern}", recursive=recursive))
            # if pathlib.Path(file).suffix.lower() in MEDIA_TYPES['image']
            if pathlib.Path(file).suffix.lower() == ".jpg"
        ]

    def get_json_paths(self, pattern: str = "**/*", recursive: bool = True) -> List[str]:
        """
        Get all JSON file paths in the base directory.

        Args:
            pattern: Glob pattern for file matching
            recursive: Whether to search recursively

        Returns:
            List of absolute JSON file paths
        """
        return [
            os.path.abspath(file)
            for file in sorted(glob(f"{self.base_dir}/{pattern}", recursive=recursive))
            if pathlib.Path(file).suffix.replace(".", "").lower() == "json"
        ]

    def reconcile_db(self, max_files: int = MAX_FILES_PER_BATCH):
        """
        Add missing image records to the database.

        Args:
            max_files: Maximum number of files to process before restarting
        """
        processed = 0
        records = self.get_records()
        image_paths = self.get_image_paths()

        for image_path in image_paths:
            if image_path not in records:
                processed += 1
                image = TruImage(media_path=image_path)
                print(f"Record not found: {image_path}")

                if self.insert_image_hash(image):
                    print(f"[{processed}]\tInserted record: {image_path}")

                del image

                if processed >= max_files:
                    self.restart_script()

    def reconcile_files(self):
        """Remove database records for images that no longer exist."""
        records = self.get_records()
        image_paths = self.get_image_paths()

        for image_path in records.keys():
            print(image_path)
            if image_path not in image_paths:
                print(f"Image not found: {image_path}")
                self.remove_record(image_path)

    def reconcile_json_files(self):
        """Remove JSON files that don't have corresponding image files."""
        json_paths = self.get_json_paths()

        for json_path in json_paths:
            print(json_path)
            image_file = json_path.replace(".json", "")

            if not os.path.isfile(image_file):
                print(f"Removing JSON file without image: {json_path}")
                os.remove(json_path)

    def init_files(self):
        """Initialize all image files and update their hashes if regenerated."""
        image_paths = self.get_image_paths()

        for image_path in image_paths:
            print(f"Initializing: {image_path}", end="\x1b[1K\r")

            try:
                image = TruImage(media_path=image_path)

                if image.valid:
                    print(f"Successfully initialized: {image.media_path}")
                    if image.regenerated:
                        print(f"Regenerated: {image.media_path}")
                        self.update_image_hash(image)
                else:
                    print(f"Failed to initialize; invalid image: {image.media_path}")

            except Exception as e:
                print(f"Failed to initialize: {image_path}")
                raise e


def find_database() -> str:
    """
    Find the database file from default locations.

    Returns:
        Path to the database file

    Raises:
        FileNotFoundError: If no database file is found
    """
    for db_path in DEFAULT_DB_PATHS:
        if os.path.isfile(db_path):
            return db_path

    raise FileNotFoundError(
        f"Database file not found in any of these locations: {DEFAULT_DB_PATHS}"
    )


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Database cleanup utility for organizing pictures"
    )

    parser.add_argument(
        "operation",
        choices=["reconcile-db", "reconcile-files", "reconcile-json", "init-files"],
        help="Operation to perform",
    )

    parser.add_argument(
        "-b",
        "--base-dir",
        default=DEFAULT_BASE_DIR,
        help=f"Base directory for images (default: {DEFAULT_BASE_DIR})",
    )

    parser.add_argument(
        "-s",
        "--subdir",
        help="Subdirectory within base-dir to process",
    )

    parser.add_argument(
        "-d",
        "--db-path",
        help="Path to database file (auto-detected if not specified)",
    )

    parser.add_argument(
        "-m",
        "--max-files",
        type=int,
        default=MAX_FILES_PER_BATCH,
        help=f"Maximum files to process per batch (default: {MAX_FILES_PER_BATCH})",
    )

    return parser.parse_args()


def main():
    """Main entry point for the cleandb command."""
    register_heif_opener()

    args = parse_arguments()

    # Determine base directory
    base_dir = args.base_dir
    if args.subdir:
        subdir_path = os.path.join(base_dir, args.subdir)
        if not os.path.isdir(subdir_path):
            print(f"Error: Subdirectory '{subdir_path}' does not exist")
            sys.exit(1)
        base_dir = subdir_path

    # Determine database path
    db_path = args.db_path if args.db_path else find_database()

    print(f"Base directory: {base_dir}")
    print(f"Database: {db_path}")
    print(f"Operation: {args.operation}")
    print()

    # Create cleaner and run operation
    cleaner = DatabaseCleaner(db_path, base_dir)

    if args.operation == "reconcile-db":
        cleaner.reconcile_db(max_files=args.max_files)
    elif args.operation == "reconcile-files":
        cleaner.reconcile_files()
    elif args.operation == "reconcile-json":
        cleaner.reconcile_json_files()
    elif args.operation == "init-files":
        cleaner.init_files()


if __name__ == "__main__":
    main()
