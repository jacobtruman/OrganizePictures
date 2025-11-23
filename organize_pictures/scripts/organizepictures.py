#!/usr/bin/env python

import logging
import os
import argparse
import re
from importlib.metadata import version

from organize_pictures import OrganizePictures, MEDIA_TYPES, OFFSET_CHARS


extensions = []
for exts in MEDIA_TYPES.values():
    extensions += [ext.replace(".", "") for ext in exts]


def extensions_list_str(values):
    if values is None:
        return None
    return [ext if ext.startswith(".") else f".{ext}" for ext in values.split(',')]


def resolve_path(path):
    return os.path.abspath(os.path.expanduser(path))


def parse_offset(offset):
    offsets = OrganizePictures.init_offset()
    ofsset_options = re.findall(r"\d{1,3}[A-Za-z]{1}", offset)
    for offset_option in ofsset_options:
        if offset_option[-1] in OFFSET_CHARS:
            offsets[offset_option[-1]] = int(offset_option[:-1])
        else:
            logging.error(f"Invalid offset option: {offset_option}")
    return offsets


def parse_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Run OrganizePictures Functions',
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {version("OrganizePictures")}',
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
        '-d', '--destination_dir',
        dest='destination_dir',
        help="Media destination directory",
        default="./pictures/renamed",
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

    parser.add_argument(
        '-b', '--sub_dirs',
        action='store_true',
        dest='sub_dirs',
        help='Create year/month subdirectories',
        default=False,
    )

    parser.add_argument(
        '-o', '--offset',
        dest='offset',
        help='Time offset (0Y0M0D0h0m0s)',
        default=None,
        type=parse_offset,
    )

    parser.add_argument(
        '-m', '--minus',
        action='store_true',
        dest='minus',
        help='Subtract offset',
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

    organizer = OrganizePictures(
        source_directory=args.source_dir,
        destination_directory=args.destination_dir,
        media_type=args.media_type,
        extensions=args.extensions,
        cleanup=args.cleanup,
        sub_dirs=args.sub_dirs,
        offset=args.offset,
        minus=args.minus,
        verbose=args.verbose,
    )

    result = organizer.run()

    if result:
        # Display results summary with nice formatting
        organizer.logger.info("\n" + "=" * 50)
        organizer.logger.info("📊 ORGANIZATION RESULTS SUMMARY")
        organizer.logger.info("=" * 50)

        # Define labels and emojis for each result type
        result_labels = {
            'moved': ('✅', 'Files Moved', 'success'),
            'duplicate': ('🔄', 'Duplicates Skipped', 'info'),
            'failed': ('❌', 'Failed (No Date/Copy Error)', 'error'),
            'manual': ('⚠️', 'Manual Review Required', 'warning'),
            'invalid': ('🚫', 'Invalid Files', 'error'),
            'deleted': ('🗑️', 'Files Deleted', 'info'),
        }

        # Display each result with appropriate formatting
        for key, count in result.items():
            icon, label, category = result_labels.get(key, (key.capitalize(), 'info'))
            organizer.logger.info(f"{icon} {label:.<35} {count:>5}")

        organizer.logger.info("=" * 50)

        # Display summary message
        total_processed = result.get('moved', 0) + result.get('duplicate', 0) + result.get('failed', 0)
        if total_processed > 0:
            success_rate = (result.get('moved', 0) / total_processed * 100) if total_processed > 0 else 0
            organizer.logger.info(f"✨ Success Rate: {success_rate:.1f}%")
            organizer.logger.info("=" * 50 + "\n")


if __name__ == '__main__':
    main()
