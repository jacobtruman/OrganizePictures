#!/usr/bin/env python

import sys
import os
import sqlite3
from pillow_heif import register_heif_opener

from organize_pictures.TruImage import TruImage

TABLE_NAME = "image_hashes"
DB_FILENAME = "pictures.db"


def find_db_file() -> str:
    for candidate in (f"/raid2/{DB_FILENAME}", f"./{DB_FILENAME}"):
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(f"DB file '{DB_FILENAME}' not found in /raid2/ or ./")


def get_record(cursor, image_path: TruImage | str) -> dict:
    if isinstance(image_path, TruImage):
        image_path = image_path.media_path
    sql = f"SELECT * FROM {TABLE_NAME} WHERE image_path = ?"
    return dict(cursor.execute(sql, (image_path,)).fetchall())


def main():
    register_heif_opener()

    if len(sys.argv) < 2:
        print("Usage: checkfile.py <path-to-image>")
        sys.exit(1)

    db_file = find_db_file()
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        _file = os.path.abspath(sys.argv[1])
        if not os.path.isfile(_file):
            print(f"File not found: {_file}")
            sys.exit(1)

        image = TruImage(media_path=_file)
        print(image.exif_data)
        print(f"Checking: {image.media_path}")
        print("Hash:", image.hash)
        if record := get_record(cursor, image):
            print(f"Record found: {record}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
