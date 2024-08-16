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

    args = parser.parse_args()

    return args


def main():
    args = parse_args()

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[ %(asctime)s ][ %(levelname)s ] %(message)s')

    fh = logging.FileHandler(f"{__name__}.log")
    if args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    fh.setLevel(log_level)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    organizer = OrganizePictures(
        logger=logger,
        source_directory=args.source_dir,
        destination_directory=args.destination_dir
    )

    result = organizer.run()

    if not result:
        sys.exit(1)


if __name__ == '__main__':
    main()
