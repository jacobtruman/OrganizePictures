#!/usr/bin/env python3
"""
Temporary script to fix mis-associated JSON files.

This script finds JPG files that have matching HEIC files, and renames
their .jpg.json files to .heic.json so they're properly associated.
"""

import os
import sys
import shutil
from glob import glob


def get_base_filename(file_path: str) -> str:
    """Extract the base filename without extension."""
    return os.path.splitext(os.path.basename(file_path))[0]


def fix_json_associations(base_dir: str, category_folders: list[str], dry_run: bool = False, verbose: bool = False):
    """
    Fix JSON files that are associated with JPG when HEIC exists.

    Args:
        base_dir: Base directory containing all folders
        category_folders: List of category folder names to search
        dry_run: If True, only show what would be done without actually doing it
        verbose: If True, show detailed debug information
    """
    stats = {'renamed': 0, 'failed': 0, 'skipped': 0}

    for category in category_folders:
        category_path = os.path.join(base_dir, category)

        if not os.path.exists(category_path):
            print(f"Warning: Category folder not found: {category_path}")
            continue

        print(f"\n{'='*80}")
        print(f"Checking: {category}")
        print(f"{'='*80}")

        # Find all HEIC files (these are the ones we want to keep)
        heic_files = glob(os.path.join(category_path, '*.heic')) + glob(os.path.join(category_path, '*.HEIC'))

        if verbose:
            print(f"  Found {len(heic_files)} HEIC files")

        for heic_file in sorted(heic_files):
            base_name = get_base_filename(heic_file)
            heic_basename = os.path.basename(heic_file)

            if verbose:
                print(f"\n  Checking HEIC: {heic_basename}")

            # Look for .jpg.json or .JPG.json files (mis-associated)
            jpg_json_lower = os.path.join(category_path, f"{base_name}.jpg.json")
            jpg_json_upper1 = os.path.join(category_path, f"{base_name}.JPG.json")
            jpg_json_upper2 = os.path.join(category_path, f"{base_name}.jpg.JSON")
            jpg_json_upper3 = os.path.join(category_path, f"{base_name}.JPG.JSON")

            # Look for .heic.json files (correctly associated)
            heic_json = os.path.join(category_path, f"{heic_basename}.json")
            heic_json_upper = os.path.join(category_path, f"{heic_basename}.JSON")

            # Check what exists
            jpg_json_exists = None
            for jpg_json_path in [jpg_json_lower, jpg_json_upper1, jpg_json_upper2, jpg_json_upper3]:
                if os.path.exists(jpg_json_path):
                    jpg_json_exists = jpg_json_path
                    break

            heic_has_json = os.path.exists(heic_json) or os.path.exists(heic_json_upper)

            if verbose:
                print(f"    .jpg.json exists: {jpg_json_exists is not None} ({jpg_json_exists if jpg_json_exists else 'none'})")
                print(f"    .heic.json exists: {heic_has_json} ({heic_json if os.path.exists(heic_json) else heic_json_upper if os.path.exists(heic_json_upper) else 'none'})")

            if jpg_json_exists:
                if heic_has_json:
                    # Both exist - skip to avoid overwriting
                    print(f"  ⚠️  SKIP: {os.path.basename(jpg_json_exists)} (HEIC JSON already exists)")
                    stats['skipped'] += 1
                else:
                    # Rename .jpg.json to .heic.json
                    dest_json = heic_json

                    if dry_run:
                        print(f"  [DRY RUN] Would rename: {os.path.basename(jpg_json_exists)} → {os.path.basename(dest_json)}")
                        stats['renamed'] += 1
                    else:
                        try:
                            print(f"  📝 Renaming: {os.path.basename(jpg_json_exists)} → {os.path.basename(dest_json)}")
                            shutil.move(jpg_json_exists, dest_json)
                            stats['renamed'] += 1
                        except Exception as e:
                            print(f"  ❌ ERROR renaming {os.path.basename(jpg_json_exists)}: {e}")
                            stats['failed'] += 1

    return stats


def main():
    """Main function."""
    # Default configuration
    base_dir = "/Users/jatruman/Desktop/newpics"
    category_folders = ["beauwedding", "tballSophia", "2018/Jul", "lacrosse"]
    
    # Parse command line arguments
    dry_run = "--dry-run" in sys.argv or len(sys.argv) == 1  # Default to dry-run if no args
    execute = "--execute" in sys.argv
    verbose = "-v" in sys.argv or "--verbose" in sys.argv

    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        print("\nUsage: fix_json_associations.py [OPTIONS]")
        print("\nOptions:")
        print("  --dry-run    Show what would be renamed (default)")
        print("  --execute    Actually rename the files")
        print("  -v, --verbose Show detailed debug information")
        print("  -h, --help   Show this help message")
        print("\nExamples:")
        print("  # Preview what would be fixed (safe)")
        print("  python fix_json_associations.py")
        print("  python fix_json_associations.py --dry-run")
        print()
        print("  # See detailed debug info")
        print("  python fix_json_associations.py -v")
        print()
        print("  # Actually fix the files")
        print("  python fix_json_associations.py --execute")
        sys.exit(0)

    if execute:
        dry_run = False

    print(f"Base directory: {base_dir}")
    print(f"Category folders: {', '.join(category_folders)}")
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'EXECUTE (files will be renamed)'}")

    # Fix JSON associations
    stats = fix_json_associations(base_dir, category_folders, dry_run=dry_run, verbose=verbose)
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"{'='*80}")
    if dry_run:
        print(f"  JSON files that would be renamed: {stats['renamed']}")
        print(f"  Files that would be skipped: {stats['skipped']}")
        print(f"\n💡 Run with --execute to actually rename the files")
    else:
        print(f"  📝 JSON files renamed: {stats['renamed']}")
        print(f"  ⚠️  Files skipped: {stats['skipped']}")
        if stats['failed'] > 0:
            print(f"  ❌ Operations failed: {stats['failed']}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()

