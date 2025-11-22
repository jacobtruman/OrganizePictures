#!/usr/bin/env python

import sys
import os
import pathlib
import sqlite3
from glob import glob
import atexit

from pillow_heif import register_heif_opener

from organize_pictures.TruImage import TruImage


def _print(*args, **kwargs):
    __builtins__.print(*args, **kwargs)
    sys.stdout.flush()


print = _print

register_heif_opener()

IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "heic"]
# BASE_DIR = "/raid/media/Pictures"
BASE_DIR = "/Users/jatruman/workspace/personal/OrganizePictures/tests"

if len(sys.argv) > 1 and os.path.isdir(f"{BASE_DIR}/{sys.argv[1]}"):
    BASE_DIR = f"{BASE_DIR}/{sys.argv[1]}"

DB_FILENAME = 'pictures.db'
TABLE_NAME = "image_hashes"
if os.path.isfile(f'/raid2/{DB_FILENAME}'):
    db_file = f'/raid2/{DB_FILENAME}'
else:
    db_file = f'./{DB_FILENAME}'

if not os.path.isfile(db_file):
    print(f"DB file '{db_file}' not found")
    exit()

conn = sqlite3.connect(db_file)
c = conn.cursor()


def complete():
    print("EXIT: Committing final records")
    conn.commit()
    conn.close()


atexit.register(complete)


def restart():
    complete()
    print("RESTARTING")
    os.execv(sys.argv[0], sys.argv)


def get_records():
    sql = f"SELECT * FROM {TABLE_NAME} WHERE image_path LIKE \"{BASE_DIR}%\""
    return dict(c.execute(sql).fetchall())


def remove_record(image_path):
    sql = f"DELETE FROM {TABLE_NAME} WHERE image_path = \"{image_path}\""
    print(f"Removing record: {image_path}")
    c.execute(sql)


def update_record(image_path, image_path_new):
    sql = f"UPDATE {TABLE_NAME} SET image_path = \"{image_path_new}\" WHERE image_path = \"{image_path}\""
    print(f"Updating record: {image_path} -> {image_path_new}")
    c.execute(sql)


def insert_image_hash(_image: TruImage):
    if _image.hash is not None:
        sql = f'INSERT INTO image_hashes VALUES ("{_image.media_path}","{_image.hash}")'
        c.execute(sql)
        return True
    return False


def update_image_hash(_image: TruImage):
    if _image.hash is not None:
        sql = f'UPDATE image_hashes SET hash = "{_image.hash}" WHERE image_path = "{_image.media_path}"'
        print(f"Updating record: {_image.media_path}: {_image.hash}")
        c.execute(sql)
        return True
    return False


def get_image_paths(_base_dir: str = '.', pattern: str = '**/*', recursive: bool = True):
    return [
        os.path.abspath(_file) for _file in sorted(glob(f"{BASE_DIR}/{pattern}", recursive=recursive))
        if pathlib.Path(_file).suffix.replace(".", "").lower() in IMAGE_EXTENSIONS
    ]


def get_json_paths(_base_dir: str = '.', pattern: str = '**/*', recursive: bool = True):
    return [
        os.path.abspath(_file) for _file in sorted(glob(f"{BASE_DIR}/{pattern}", recursive=recursive))
        if pathlib.Path(_file).suffix.replace(".", "").lower() in ['json']
    ]


def reconcile_db():
    max_files = 450
    processed = 0
    records = get_records()
    image_paths = get_image_paths(_base_dir=BASE_DIR)
    for image_path in image_paths:
        if image_path not in records:
            processed += 1
            image = TruImage(media_path=image_path)
            print(f"Record not found: {image_path}")
            if insert_image_hash(image):
                print(f"[{processed}]\tInserted record: {image_path}")
            del image
            if processed >= max_files:
                restart()


def reconcile_files():
    records = get_records()
    image_paths = get_image_paths(_base_dir=BASE_DIR)
    for image_path, _ in records.items():
        print(image_path)
        if image_path not in image_paths:
            print(f"Image not found: {image_path}")
            remove_record(image_path)


def reconcile_json_files():
    json_paths = get_json_paths(_base_dir=BASE_DIR)
    for json_path in json_paths:
        print(json_path)
        image_file = json_path.replace(".json", "")
        if not os.path.isfile(image_file):
            print(f"Removing JSON file without image: {json_path}")
            os.remove(json_path)


def init_files():
    image_paths = get_image_paths(_base_dir=BASE_DIR)
    for image_path in image_paths:
        print(f"Initializing: {image_path}", end='\x1b[1K\r')
        try:
            image = TruImage(media_path=image_path)
            if image.valid:
                print(f"Successfully initialized: {image.media_path}")
                if image.regenerated:
                    print(f"Regenerated: {image.media_path}")
                    update_image_hash(image)
            else:
                print(f"Failed to initialize; invalid image: {image.media_path}")
        except Exception as e:
            print(f"Failed to initialize: {image_path}")
            raise e


# reconcile_db()
# reconcile_files()
# reconcile_json_files()
# init_files()
