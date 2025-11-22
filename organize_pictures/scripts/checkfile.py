#!/usr/bin/env python

import sys
import os
import time
import sqlite3
from pillow_heif import register_heif_opener

from organize_pictures.TruImage import TruImage

register_heif_opener()

image_extensions = ["jpg", "jpeg", "png", "heic"]
base_dir = "/raid/media/Pictures"

db_filename = 'pictures.db'
table_name = "image_hashes"
if os.path.isfile(f'/raid2/{db_filename}'):
    db_file = f'/raid2/{db_filename}'
else:
    db_file = f'./{db_filename}'
create = False
if not os.path.isfile(db_file):
    print(f"DB file '{db_file}' not found")
    exit()

conn = sqlite3.connect(db_file)
c = conn.cursor()


def get_record(image_path: TruImage | str):
    if isinstance(image_path, TruImage):
        image_path = image_path.media_path

    sql = f"SELECT * FROM {table_name} WHERE image_path = \"{image_path}\""
    return dict(c.execute(sql).fetchall())


_file = os.path.abspath(sys.argv[1])
if not os.path.isfile(_file):
    print(f"File not found: {_file}")

# if record := get_record(_file):
#     print(f"Record found: {record}")
# exit()
_image = TruImage(media_path=_file)
print(_image.exif_data)
print(f"Checking: {_image.media_path}")
print("Hash:", _image.hash)
if record := get_record(_image):
    print(f"Record found: {record}")
