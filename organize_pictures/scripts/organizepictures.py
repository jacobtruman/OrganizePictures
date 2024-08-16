#!/usr/bin/env python

import logging
import os
import sys
import argparse

from organize_pictures import OrganizePictures, MEDIA_TYPES


extensions = []
for exts in MEDIA_TYPES.values():
    extensions += [ext.replace(".", "") for ext in exts]


def extensions_list_str(values):
    if values is None:
        return None
    return [ext if ext.startswith(".") else f".{ext}" for ext in values.split(',')]


def resolve_path(path):
    return os.path.abspath(os.path.expanduser(path))


def parse_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Run OrganizePictures Functions',
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='verbose',
        help='Enable verbose logging',
        default=False,
    )

    parser.add_argument(
        '-s', '--source_dir',
        dest='source_dir',
        help="Media source directory",
        default="./pictures",
        type=resolve_path,
    )

    parser.add_argument(
        '-e', '--extensions',
        dest='extensions',
        help=f"Comma separated list of file extensions to process ({', '.join(extensions)})",
        default=None,
        type=extensions_list_str,
    )

    parser.add_argument(
        '-d', '--destination_dir',
        dest='destination_dir',
        help="Media destination directory",
        default="./pictures/renamed",
        type=resolve_path,
    )

    parser.add_argument(
        '-t', '--media_type',
        dest='media_type',
        help=f"The type of media to process ({', '.join(MEDIA_TYPES)})",
        default=None,
        type=str.lower,
    )

    parser.add_argument(
        '-c', '--cleanup',
        action='store_true',
        dest='cleanup',
        help='Cleanup source file(s) after successful run',
        default=False,
    )

    args = parser.parse_args()

    if args.media_type is not None and args.media_type not in MEDIA_TYPES:
        parser.error(f"Invalid media type specified ({args.media_type})\nMust be one of: {', '.join(MEDIA_TYPES)})")

    if args.source_dir == args.destination_dir:
        parser.error("Source and destination directories cannot be the same")

    return args


def main():
    args = parse_args()

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[ %(asctime)s ][ %(levelname)s ] %(message)s')

    file_handle = logging.FileHandler(f"{__name__}.log")
    if args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    file_handle.setLevel(log_level)
    file_handle.setFormatter(formatter)

    stream_handle = logging.StreamHandler()
    stream_handle.setLevel(logging.DEBUG)
    stream_handle.setFormatter(formatter)

    logger.addHandler(file_handle)
    logger.addHandler(stream_handle)

    organizer = OrganizePictures(
        logger=logger,
        source_directory=args.source_dir,
        destination_directory=args.destination_dir,
        media_type=args.media_type,
        extensions=args.extensions,
        cleanup=args.cleanup,
        verbose=args.verbose,
    )

    result = organizer.run()

    if not result:
        sys.exit(1)


if __name__ == '__main__':
    main()
