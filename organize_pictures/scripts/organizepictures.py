#!/usr/bin/env python

import os
import argparse
import re
from importlib.metadata import version

from organize_pictures import OrganizePictures, MEDIA_TYPES, OFFSET_CHARS


extensions = []
for exts in MEDIA_TYPES.values():
    extensions += [ext.replace(".", "") for ext in exts]


def extensions_list_str(values):
    return [ext if ext.startswith(".") else f".{ext}" for ext in values.split(',')]


def resolve_path(path):
    return os.path.abspath(os.path.expanduser(path))


def parse_offset(offset):
    offsets = OrganizePictures.init_offset()
    for value, char in re.findall(rf"(\d+)([{OFFSET_CHARS}])", offset):
        offsets[char] = int(value)
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
        help="Media destination directory (must not be inside source_dir)",
        default="./pictures_organized",
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
        '-n', '--dry_run',
        action='store_true',
        dest='dry_run',
        help='Simulate the run without copying, deleting, mutating files, or writing the database',
        default=False,
    )

    parser.add_argument(
        '-b', '--no_sub_dirs',
        action='store_false',
        dest='sub_dirs',
        help='Disable year/month subdirectory creation (sub_dirs is enabled by default)',
        default=True,
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

    src = os.path.realpath(args.source_dir)
    dst = os.path.realpath(args.destination_dir)
    if dst == src or dst.startswith(src + os.sep) or src.startswith(dst + os.sep):
        parser.error(
            f"Destination directory ({args.destination_dir}) cannot be inside the "
            f"source directory ({args.source_dir}), or vice versa."
        )

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
        dry_run=args.dry_run,
    )

    result = organizer.run()

    if result:
        # Display results summary with nice formatting
        organizer.logger.info("\n" + "=" * 50)
        organizer.logger.info("📊 ORGANIZATION RESULTS SUMMARY")
        organizer.logger.info("=" * 50)

        result_labels = {
            'moved': ('✅', 'Files Moved'),
            'duplicate': ('🔄', 'Duplicates Skipped'),
            'failed': ('❌', 'Failed (No Date/Copy Error)'),
            'manual': ('⚠️', 'Manual Review Required'),
            'invalid': ('🚫', 'Invalid Files'),
            'deleted': ('🗑️', 'Files Deleted'),
        }

        for key, count in result.items():
            icon, label = result_labels.get(key, ('•', key.capitalize()))
            organizer.logger.info(f"{icon}\t{label:.<35} {count:>5}")

        organizer.logger.info("=" * 50)

        total_processed = result.get('moved', 0) + result.get('duplicate', 0) + result.get('failed', 0)
        if total_processed > 0:
            success_rate = (result.get('moved', 0) / total_processed * 100)
            organizer.logger.info(f"✨ Success Rate: {success_rate:.1f}%")
            organizer.logger.info("=" * 50 + "\n")

        sections = [
            ('⚠️  Manual Review Required', organizer.manual_review_files),
            ('❌ Failed', organizer.failed_files),
            ('🚫 Invalid', organizer.invalid_files),
        ]
        for header, paths in sections:
            if not paths:
                continue
            organizer.logger.info(f"{header} ({len(paths)}):")
            for path in paths:
                organizer.logger.info(f"\t- {path}")
            organizer.logger.info("")


if __name__ == '__main__':
    main()
