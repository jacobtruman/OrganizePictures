#!/usr/bin/env python

import logging
import sys
import argparse

from organize_pictures import OrganizePictures


def parse_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Run OrganizePictures Functions',
    )

    parser.add_argument(
        '-d', '--dry_run',
        action='store_true',
        dest='dry_run',
        help='Dry run mode',
        default=False,
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='verbose',
        help='Enable verbose logging',
    )

    parser.add_argument(
        '-s', '--source_dir',
        dest='source_dir',
        help="Media source directory",
        default="./pictures",
    )

    parser.add_argument(
        '-m', '--destination_dir',
        dest='destination_dir',
        help="Media destination directory",
        default="./pictures/renamed",
    )

    parser.add_argument(
        '-c', '--cleanup',
        action='store_true',
        dest='cleanup',
        help='Cleanup source directory after successful run',
        default=False,
    )

    args = parser.parse_args()

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
        cleanup=args.cleanup,
    )

    result = organizer.run()

    if not result:
        sys.exit(1)


if __name__ == '__main__':
    main()
