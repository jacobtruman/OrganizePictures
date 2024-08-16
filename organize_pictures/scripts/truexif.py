#!/usr/bin/env python
import argparse
import piexif


def list_str(values):
    if values is None:
        return None
    return [ext.lower() for ext in values.split(',')]


def parse_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Run OrganizePictures Functions',
    )

    parser.add_argument(
        dest='image',
        help="Path to image file",
    )

    parser.add_argument(
        '-t', '--tags',
        dest='tags',
        help="Comma separated list of tags to display",
        type=list_str,
    )

    args = parser.parse_args()

    return args


def main():
    args = parse_args()

    exif_dict = piexif.load(args.image)
    for tag, value in exif_dict['Exif'].items():
        print_tag = True
        if args.tags is not None and piexif.TAGS['Exif'][tag]["name"].lower() not in args.tags:
            print_tag = False
        if print_tag:
            print(piexif.TAGS['Exif'][tag]["name"], value)


if __name__ == '__main__':
    main()
