#!/usr/bin/env python
import os
import sys
import shutil
import argparse
import ffmpeg
from datetime import datetime

ENCODED_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
FILENAME_DATE_FORMAT = "%Y%m%d_%H%M%S"


def parse_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Convert GIF to MP4',
    )

    parser.add_argument(
        dest='image',
        help="Path to image file",
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='verbose',
        help='Enable verbose logging',
        default=False,
    )

    parser.add_argument(
        '-d', '--date',
        dest='date',
        help="Date to set for image",
    )

    parser.add_argument(
        '-p', '--pattern',
        dest='pattern',
        help=f"Pattern to use for image date. Ex: {ENCODED_DATE_FORMAT.replace('%', '%%')}",
    )

    parser.add_argument(
        '-c', '--cleanup',
        action='store_true',
        dest='cleanup',
        help='Cleanup source file after successful run',
        default=False,
    )

    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"ERROR: {args.image} is not a file")
        parser.print_help()
        sys.exit(1)

    return args


def get_file_ext(file):
    _, ext = os.path.splitext(os.path.basename(file))
    return ext


def get_json_file(_file, check: bool = True):
    """Get the json file name for the given file"""
    if "(" in _file and ")" in _file:
        ext = get_file_ext(_file)
        start = _file.find("(")
        end = _file.find(")")
        base_file = _file[:start]
        file_num = _file[start + 1:end]
        _file = f"{base_file}{ext}({file_num})"
    json_file = f"{_file}.json"
    if check and not os.path.isfile(json_file):
        return None
    return json_file


def main():
    args = parse_args()
    cleanup_files = [args.image]

    new_image = args.image.replace(".gif", ".mp4")

    if args.date is not None:
        if args.pattern is not None:
            date_time_obj = datetime.strptime(args.date, args.pattern)
        else:
            date_time_obj = datetime.strptime(args.date, FILENAME_DATE_FORMAT)
    else:
        image_basename = os.path.basename(args.image)
        image_filename = image_basename[0: image_basename.rfind(".")]
        date_time_obj = datetime.strptime(image_filename[0:image_filename.rfind("-")], FILENAME_DATE_FORMAT)

    image_date = date_time_obj.strftime(ENCODED_DATE_FORMAT)

    print(f"Converting {args.image} to {new_image}")
    stream = ffmpeg.input(args.image)
    stream = ffmpeg.output(
        stream,
        new_image,
        acodec="aac",
        vcodec="h264",
        map_metadata=0,
        loglevel="verbose" if args.verbose else "quiet",
        **{'metadata': f"comment=Converted {args.image} to {new_image}", 'metadata:': f"creation_time={image_date}"},
    )
    _, err = ffmpeg.run(stream)
    if err is not None:
        print(err)
        sys.exit(1)
    else:
        json_file = get_json_file(args.image)
        if json_file is not None:
            new_json_file = get_json_file(new_image, check=False)
            print(f"Copying {json_file} to {new_json_file}")
            shutil.copyfile(json_file, new_json_file)
            cleanup_files.append(json_file)
        if args.cleanup:
            for media_file in cleanup_files:
                print(f"Removing {media_file}")
                os.remove(media_file)


if __name__ == '__main__':
    main()
