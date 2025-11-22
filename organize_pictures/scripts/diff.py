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

@cache
def get_min_size(min_size: int) -> tuple[int, int]:
    return min_size, min_size


def display_image(image):
    """Display an image using tkinter."""
    root = tk.Tk()
    root.title("Image Viewer")

    # Convert PIL image to PhotoImage
    photo = ImageTk.PhotoImage(image)

    # Create a label to display the image
    label = tk.Label(root, image=photo)
    label.pack()

    # Keep a reference to prevent garbage collection
    label.image = photo

    # Start the GUI event loop
    root.mainloop()


def create_collage(images: tuple[Image, Image, Image]) -> Image:
    """Create a side-by-side collage of three images."""
    # Get dimensions
    widths, heights = zip(*(i.size for i in images))

    # Calculate total width and max height
    total_width = sum(widths)
    max_height = max(heights)

    # Create new image with white background
    collage = Image.new('RGB', (total_width, max_height), (255, 255, 255))

    # Paste images side by side
    x_offset = 0
    for img in images:
        collage.paste(img, (x_offset, 0))
        x_offset += img.width

    return collage


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


def add_to_delete() -> bool:
    """Prompt user to decide if files should be marked for deletion."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    result = tk.messagebox.askyesno("Delete?", "Mark these files for deletion?")
    root.destroy()

    return result


def delete_files(file_pairs: list[tuple[str, str]]):
    """Delete the second file in each pair."""
    for file1, file2 in file_pairs:
        try:
            print(f"Deleting: {file2}")
            os.remove(file2)
        except Exception as e:
            print(f"Error deleting {file2}: {e}")


def get_file_size(file_path: str) -> int:
    """Get file size in bytes."""
    try:
        return os.path.getsize(file_path)
    except Exception:
        return 0


def choose_file_to_keep(file1: str, file2: str) -> str:
    """Choose which file to keep based on size (keep larger file)."""
    size1 = get_file_size(file1)
    size2 = get_file_size(file2)

    if size1 >= size2:
        return file1
    else:
        return file2


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

