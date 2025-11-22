#!/usr/bin/env python3

import os
from glob import glob
from PIL import Image, ImageChops, ImageOps, ImageTk
from pillow_heif import register_heif_opener
from organize_pictures.TruImage import TruImage
import numpy as np
import sys
from functools import cache
import time
import tkinter as tk

register_heif_opener()


@cache
def resize_image(_image_path: str, new_size: tuple[int, int], attempt: int = 0) -> Image:

    try:
        image = Image.open(_image_path)
        try:
            display_image(image)  # Display the collage image
        except Exception as e:
            print(f"Error displaying image: {e}")
            # If display fails, just continue without showing it
            pass
        exit()
        tru_image = TruImage(_image_path)
        tru_or = tru_image.exif_data.get("EXIF:Orientation")
        match tru_or:
            case 3:
                # Rotate 180 degrees
                image = image.transpose(Image.ROTATE_180)
            case 6:
                # Rotate 270 degrees clockwise
                image = image.transpose(Image.ROTATE_270)
            case 8:
                # Rotate 90 degrees counterclockwise
                image = image.transpose(Image.ROTATE_90)
    except Exception:
        print(f"Error opening image {_image_path}: {sys.exc_info()[1]}")
        if attempt < 3:
            attempt += 1
            return resize_image(_image_path, new_size, attempt)
        else:
            print(f"Failed to open image {_image_path} after 3 attempts.")
            return Image.new("RGB", new_size)
    return image.resize(new_size)

@cache
def get_max_diff(_size: tuple[int, int]) -> int:
    return _size[0] * _size[1] * 255 * 3

def display_image(_image: Image):
    print("Displaying image...")
    root = tk.Tk()

    # def my_function(arg1):
    #     print(f"Arguments: {arg1}")
    #     root.destroy()
    #
    # print("Creating buttons...")
    # button1 = tk.Button(root, text="Yes", command=lambda: my_function(1))
    # button1.pack()
    #
    # button2 = tk.Button(root, text="No", command=lambda: my_function(0))
    # button2.pack()

    print("Creating photo...")
    photo = ImageTk.PhotoImage(_image)
    print("Creating label...")
    image_label = tk.Label(root, image=photo)
    image_label.image = photo  # Keep a reference to avoid garbage collection
    image_label.pack()

    root.mainloop()

def get_max_file(_files: set[str]) -> str:
    max_file = None
    max_size = 0
    for file in _files:
        if os.path.isfile(file):
            size = os.path.getsize(file)
            if size > max_size:
                max_size = size
                max_file = file
    return max_file

def get_min_size(size: int = 800) -> tuple[int, int]:
    return size, size

def get_image_difference(image1_path: str, image2_path: str, size: tuple[int, int]) -> tuple[int, float, Image]:
    image1 = resize_image(image1_path, size)
    image2 = resize_image(image2_path, size)

    try:
        diff = ImageChops.difference(image1, image2)
        diff_array = np.array(diff)
        _numerical_diff = np.sum(np.abs(diff_array))
        _diff_percentage = (_numerical_diff / get_max_diff(size)) * 100
    except Exception as e:
        print(f"Error calculating difference: {e}")
        diff = None
        _numerical_diff = 100
        _diff_percentage = 100

    return _numerical_diff, _diff_percentage, diff

def group_files(_files: list[tuple[str, str]]) -> list[set[str]]:
    file_groups = []
    for files in _files:
        file1, file2 = files
        found = False
        for file_group in file_groups:
            if file1 in file_group or file2 in file_group:
                file_group.update({file1, file2})
                found = True
                break
        if not found:
            file_groups.append({file1, file2})
    return file_groups

def delete_files(file_lists: list[tuple[str, str]]) -> None:
    groups = group_files(file_lists)
    image_min_size = get_min_size(1000)
    for index, group in enumerate(groups, 1):
        print(f"Group {index} / {len(groups)}")
        max_file = get_max_file(group)
        max_json_file = f"{max_file}.json"
        # print(f"Keeping: {max_file} :: {group}")
        json_file = None
        group.discard(max_file)
        image1 = resize_image(max_file, image_min_size)
        for image_file in group:
            if image_file != max_file:
                if not os.path.isfile(image_file):
                    continue
                print(f"Removing: {image_file}")
                image2 = resize_image(image_file, image_min_size)
                create_collage((image1, image2)).show()
                image = TruImage(image_file)
                if not os.path.isfile(max_json_file) and image.json_file_path:
                    json_file = image.json_file_path
                os.remove(image_file)
        if json_file:
            # rename json file
            print(f"Renaming: {json_file} to {max_json_file}")
            os.rename(json_file, max_json_file)

def add_to_delete():
    resp = input('Add to delete? ').lower()
    if resp not in ['y', 'yes', 'n', 'no']:
        add_to_delete()
    return resp in ['y', 'yes']

def add_border(image, border_size, color):
    bordered_image = ImageOps.expand(image, border=border_size, fill=color)
    return bordered_image

def create_collage(images, border_size=5, border_color="red"):
    # Add borders to each image
    bordered_images = [add_border(img, border_size, border_color) for img in images]

    # Calculate total width and maximum height
    total_width = sum(img.width for img in bordered_images)
    max_height = max(img.height for img in bordered_images)

    # Create new image
    new_image = Image.new("RGB", (total_width, max_height))

    # Paste images into new image
    x_offset = 0
    for img in bordered_images:
        new_image.paste(img, (x_offset, 0))
        x_offset += img.width

    return new_image

def main(base_dir: str, min_size: int = 800, diff_limit: float = 5, delete: bool = False):
    start = time.time()

    files = sorted(glob(f"./{base_dir}/*.jpg"))

    image_min_size = get_min_size(min_size)

    count = len(files)
    for index, image_path in enumerate(files, 1):
        print(f"Pre-processing [{index} / {count}]: {image_path}")
        resize_image(image_path, image_min_size)

    evaluate = []
    similar_files = []
    i = 0
    total = len(files)
    while len(files) > 0:
        i += 1
        source_file = files.pop(0)
        sub_total = len(files)
        remove = []
        for j, image_path in enumerate(files, 1):
            diff_value, diff_percentage, _ = get_image_difference(source_file, image_path, image_min_size)
            print(
                f"[ {i} / {total} ][ {j} / {sub_total} ] Difference between {source_file} and {image_path}: {diff_value} :: {diff_percentage}%"
            )
            if diff_percentage < diff_limit:
                if diff_percentage > 1.5:
                    evaluate.append((source_file, image_path))
                else:
                    similar_files.append((source_file, image_path))
                    remove.append(image_path)
        i += len(remove)
        files = [x for x in files if x not in remove]

    for index, files in enumerate(evaluate, 1):
        image_min_size = get_min_size(min_size * 2)
        image1_path, image2_path = files
        image1 = resize_image(image1_path, image_min_size)
        image2 = resize_image(image2_path, image_min_size)
        _, diff_percentage, diff = get_image_difference(image1_path, image2_path, image_min_size)

        print(f"Creating collage [{index} / {len(evaluate)}]: {files} :: {diff_percentage}%")
        create_collage((image1, image2, diff)).show()

        if add_to_delete():
            similar_files.append(files)
    if delete:
        delete_files(similar_files)

    end = time.time()
    print("\nProcess took", end - start, "seconds to run")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: diff.py <directory>")
        exit(1)
    main(sys.argv[1], min_size=400, delete=True, diff_limit=3)
