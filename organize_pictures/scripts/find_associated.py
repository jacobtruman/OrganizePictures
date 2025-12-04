#!/usr/bin/env python3
"""
Find and move associated files (json, mp4, heic) for images in specified folders.

This script looks for image files in the specified category folders and finds
their associated metadata and media files in the json, mp4, and heic folders,
then moves them to be with the source image files.
"""

import os
import sys
import shutil
from glob import glob
from pathlib import Path
from typing import Dict, List, Set


def get_base_filename(file_path: str) -> str:
    """Extract the base filename without extension."""
    return os.path.splitext(os.path.basename(file_path))[0]


def find_associated_files(base_dir: str, category_folders: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """
    Find associated files for images in category folders.

    Args:
        base_dir: Base directory containing all folders
        category_folders: List of category folder names to search

    Returns:
        Dictionary mapping category -> filename -> list of associated files
    """
    results = {}

    # Extensions to look for in category folders (jpg and heic files)
    image_extensions = ['*.jpg', '*.JPG', '*.heic', '*.HEIC']

    # Associated file folders and their patterns
    # For json files, we need to check for compound extensions like .heic.json, .jpg.json, etc.
    associated_folders = {
        'json': {
            'patterns': ['*.json', '*.JSON'],
            'compound': True  # Check for compound extensions
        },
        'mp4': {
            'patterns': ['*.mp4', '*.MP4'],
            'compound': False
        },
        'heic': {
            'patterns': ['*.heic', '*.HEIC'],
            'compound': False
        }
    }

    for category in category_folders:
        category_path = os.path.join(base_dir, category)

        if not os.path.exists(category_path):
            print(f"Warning: Category folder not found: {category_path}")
            continue

        print(f"\nSearching in: {category}")
        results[category] = {}

        # Find all image files in this category folder
        image_files = []
        for ext in image_extensions:
            image_files.extend(glob(os.path.join(category_path, ext)))

        print(f"  Found {len(image_files)} image files")

        # For each image file, look for associated files
        for image_file in sorted(image_files):
            base_name = get_base_filename(image_file)
            image_basename = os.path.basename(image_file)  # Full filename with extension
            associated = []

            # Check each associated folder
            for folder_name, config in associated_folders.items():
                folder_path = os.path.join(base_dir, folder_name)

                if not os.path.exists(folder_path):
                    continue

                # Look for files with matching base name
                for pattern in config['patterns']:
                    ext = pattern.replace('*', '')

                    if config.get('compound', False):
                        # For json files, use glob pattern to match file_name.*.json
                        # This will match: file_name.json, file_name.jpg.json, file_name.heic.json, etc.
                        glob_pattern = os.path.join(folder_path, f"{base_name}*{ext}")
                        matching_files = glob(glob_pattern)
                        for matching_file in matching_files:
                            if matching_file not in associated:
                                associated.append(matching_file)
                    else:
                        # For mp4 and heic, use exact match
                        simple_pattern = os.path.join(folder_path, f"{base_name}{ext}")
                        if os.path.exists(simple_pattern):
                            associated.append(simple_pattern)

            if associated:
                results[category][image_file] = associated

    return results


def cleanup_jpg_with_heic(base_dir: str, category_folders: List[str], dry_run: bool = False) -> Dict[str, int]:
    """
    Delete JPG files that have a matching HEIC file, and rename JSON files accordingly.

    Args:
        base_dir: Base directory containing all folders
        category_folders: List of category folder names to search
        dry_run: If True, only show what would be done without actually doing it

    Returns:
        Dictionary with counts of deleted and renamed files
    """
    stats = {'jpg_deleted': 0, 'json_renamed': 0, 'failed': 0}

    for category in category_folders:
        category_path = os.path.join(base_dir, category)

        if not os.path.exists(category_path):
            continue

        print(f"\n{'='*80}")
        print(f"Cleanup in: {category}")
        print(f"{'='*80}")

        # Find all JPG files
        jpg_files = glob(os.path.join(category_path, '*.jpg')) + glob(os.path.join(category_path, '*.JPG'))

        for jpg_file in sorted(jpg_files):
            base_name = get_base_filename(jpg_file)

            # Check if matching HEIC exists
            heic_file = os.path.join(category_path, f"{base_name}.heic")
            heic_file_upper = os.path.join(category_path, f"{base_name}.HEIC")

            matching_heic = None
            if os.path.exists(heic_file):
                matching_heic = heic_file
            elif os.path.exists(heic_file_upper):
                matching_heic = heic_file_upper

            if matching_heic:
                # Check for JSON files
                heic_basename = os.path.basename(matching_heic)

                # Look for .jpg.json or .JPG.json files (mis-associated with JPG)
                jpg_json_lower = os.path.join(category_path, f"{base_name}.jpg.json")
                jpg_json_upper1 = os.path.join(category_path, f"{base_name}.JPG.json")
                jpg_json_upper2 = os.path.join(category_path, f"{base_name}.jpg.JSON")
                jpg_json_upper3 = os.path.join(category_path, f"{base_name}.JPG.JSON")

                # Look for .heic.json files (correctly associated with HEIC)
                heic_json = os.path.join(category_path, f"{heic_basename}.json")
                heic_json_upper = os.path.join(category_path, f"{heic_basename}.JSON")

                # Check what exists
                jpg_json_exists = None
                for jpg_json_path in [jpg_json_lower, jpg_json_upper1, jpg_json_upper2, jpg_json_upper3]:
                    if os.path.exists(jpg_json_path):
                        jpg_json_exists = jpg_json_path
                        break

                heic_has_json = os.path.exists(heic_json) or os.path.exists(heic_json_upper)

                # If .jpg.json exists but .heic.json doesn't, rename it to associate with HEIC
                if jpg_json_exists and not heic_has_json:
                    dest_json = heic_json

                    if dry_run:
                        print(f"  [DRY RUN] Would rename JSON: {os.path.basename(jpg_json_exists)} → {os.path.basename(dest_json)}")
                        stats['json_renamed'] += 1
                    else:
                        try:
                            print(f"  📝 Renaming JSON: {os.path.basename(jpg_json_exists)} → {os.path.basename(dest_json)}")
                            shutil.move(jpg_json_exists, dest_json)
                            stats['json_renamed'] += 1
                        except Exception as e:
                            print(f"  ❌ ERROR renaming JSON {os.path.basename(jpg_json_exists)}: {e}")
                            stats['failed'] += 1

                # Delete the JPG file
                if dry_run:
                    print(f"  [DRY RUN] Would delete JPG: {os.path.basename(jpg_file)} (HEIC exists: {os.path.basename(matching_heic)})")
                    stats['jpg_deleted'] += 1
                else:
                    try:
                        print(f"  🗑️  Deleting JPG: {os.path.basename(jpg_file)} (HEIC exists: {os.path.basename(matching_heic)})")
                        os.remove(jpg_file)
                        stats['jpg_deleted'] += 1
                    except Exception as e:
                        print(f"  ❌ ERROR deleting {os.path.basename(jpg_file)}: {e}")
                        stats['failed'] += 1

    return stats


def move_associated_files(results: Dict[str, Dict[str, List[str]]], dry_run: bool = False) -> Dict[str, int]:
    """
    Move associated files to be with their source images.

    Args:
        results: Dictionary mapping category -> filename -> list of associated files
        dry_run: If True, only show what would be moved without actually moving

    Returns:
        Dictionary with counts of moved files
    """
    stats = {'moved': 0, 'failed': 0, 'skipped': 0}

    for category, files in results.items():
        if not files:
            continue

        print(f"\n{'='*80}")
        print(f"Category: {category}")
        print(f"{'='*80}")

        for image_file, associated_files in sorted(files.items()):
            image_dir = os.path.dirname(image_file)

            for assoc_file in associated_files:
                dest_file = os.path.join(image_dir, os.path.basename(assoc_file))

                # Skip if file already exists at destination
                if os.path.exists(dest_file):
                    print(f"  ⚠️  SKIP: {os.path.basename(dest_file)} (already exists)")
                    stats['skipped'] += 1
                    continue

                if dry_run:
                    print(f"  [DRY RUN] Would move: {os.path.basename(assoc_file)}")
                    print(f"            From: {os.path.dirname(assoc_file)}")
                    print(f"            To:   {image_dir}")
                    stats['moved'] += 1
                else:
                    try:
                        print(f"  ✅ Moving: {os.path.basename(assoc_file)}")
                        print(f"     From: {os.path.dirname(assoc_file)}")
                        print(f"     To:   {image_dir}")
                        shutil.move(assoc_file, dest_file)
                        stats['moved'] += 1
                    except Exception as e:
                        print(f"  ❌ ERROR moving {os.path.basename(assoc_file)}: {e}")
                        stats['failed'] += 1

    return stats


def print_results(results: Dict[str, Dict[str, List[str]]], verbose: bool = False):
    """Print the results in a readable format."""
    total_images = 0
    total_associated = 0

    for category, files in results.items():
        if not files:
            continue

        print(f"\n{'='*80}")
        print(f"Category: {category}")
        print(f"{'='*80}")

        images_with_associated = len(files)
        total_images += images_with_associated

        for image_file, associated_files in sorted(files.items()):
            total_associated += len(associated_files)

            if verbose:
                print(f"\n  Image: {os.path.basename(image_file)}")
                for assoc_file in associated_files:
                    print(f"    → {os.path.basename(assoc_file)} ({os.path.dirname(assoc_file).split('/')[-1]})")
            else:
                print(f"  {os.path.basename(image_file)}: {len(associated_files)} associated file(s)")

    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"  Total images with associated files: {total_images}")
    print(f"  Total associated files found: {total_associated}")
    print(f"{'='*80}")


def main():
    """Main function."""
    # Default configuration
    base_dir = "/Users/jatruman/Desktop/newpics"
    category_folders = [
        "basketballGrant",
        "basketballDrake",
        "danceEva",
        "danceSophia",
        "adobe",
        "house",
        "lacrosse",
        "tballSophia",
        "schoolPics",
        "2018/Dec"
    ]

    # Parse command line arguments
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    dry_run = "--dry-run" in sys.argv
    move_files = "--move" in sys.argv

    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        print("\nUsage: find_associated.py [OPTIONS]")
        print("\nOptions:")
        print("  -v, --verbose    Show detailed file listings")
        print("  --dry-run        Show what would be moved without actually moving files")
        print("  --move           Move associated files to be with source images")
        print("  -h, --help       Show this help message")
        print("\nExamples:")
        print("  # Just find and list associated files")
        print("  python find_associated.py")
        print()
        print("  # See what would be moved (dry run)")
        print("  python find_associated.py --dry-run")
        print()
        print("  # Actually move the files")
        print("  python find_associated.py --move")
        sys.exit(0)

    print(f"Base directory: {base_dir}")
    print(f"Category folders: {', '.join(category_folders)}")

    # Find associated files
    results = find_associated_files(base_dir, category_folders)

    # If moving files or doing dry run
    if move_files or dry_run:
        # Step 1: Move associated files
        move_stats = move_associated_files(results, dry_run=dry_run)

        # Step 2: Cleanup JPG files with matching HEIC
        cleanup_stats = cleanup_jpg_with_heic(base_dir, category_folders, dry_run=dry_run)

        # Combined summary
        print(f"\n{'='*80}")
        print(f"Summary:")
        print(f"{'='*80}")
        if dry_run:
            print(f"  Files that would be moved: {move_stats['moved']}")
            print(f"  Files that would be skipped (already exist): {move_stats['skipped']}")
            print(f"  JPG files that would be deleted (HEIC exists): {cleanup_stats['jpg_deleted']}")
            print(f"  JSON files that would be renamed: {cleanup_stats['json_renamed']}")
        else:
            print(f"  ✅ Files moved successfully: {move_stats['moved']}")
            print(f"  ⚠️  Files skipped (already exist): {move_stats['skipped']}")
            print(f"  🗑️  JPG files deleted (HEIC exists): {cleanup_stats['jpg_deleted']}")
            print(f"  📝 JSON files renamed: {cleanup_stats['json_renamed']}")
            total_failed = move_stats['failed'] + cleanup_stats['failed']
            if total_failed > 0:
                print(f"  ❌ Operations failed: {total_failed}")
        print(f"{'='*80}")
    else:
        # Just print results
        print_results(results, verbose=verbose)

        # Suggest next steps
        if any(results.values()):
            print("\n💡 Next steps:")
            print("  • Run with --dry-run to see what would be moved")
            print("  • Run with --move to actually move the files")


if __name__ == "__main__":
    main()

