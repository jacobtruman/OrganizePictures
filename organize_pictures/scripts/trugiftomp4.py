#!/usr/bin/env python
import os
import sys
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

    return args


def main():
    args = parse_args()

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
    elif args.cleanup:
        os.remove(args.image)


if __name__ == '__main__':
    main()
