#!/usr/bin/env python
"""
Recompute hashes in pictures.db using the current hashing logic.

The hashing strategy changed (see organize_pictures/image_hash.py and
TruVideo._get_media_hash). Existing rows hold legacy hashes that the new code
will never reproduce, so duplicate detection silently breaks. This script
re-hashes every row in place.

Behavior:
  - For each row, look up the file on disk.
  - If the file exists, recompute its hash using the live code path that the
    organizer would use (TruImage / TruVideo) and update the row.
  - If the file is missing, by default keep the row but log it. With
    -p/--prune-missing, delete those rows instead.
  - Rows whose hash didn't change are skipped silently.
  - Use -n/--dry-run to see what would happen without writing.

Progress is rendered with tqdm pinned to the bottom of the terminal. Log lines
print above it via tqdm's logging redirect, so they never collide with the
progress bar. When stderr isn't a TTY (piped, CI), tqdm degrades to plain
periodic updates.

The script writes incrementally (commit per N updates) so it's safe to Ctrl-C.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sqlite3
import sys
from contextlib import closing

from pillow_heif import register_heif_opener
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from organize_pictures.TruImage import TruImage
from organize_pictures.TruVideo import TruVideo
from organize_pictures.utils import MEDIA_TYPES, get_logger


TABLE_NAME = "image_hashes"
DB_FILENAME = "pictures.db"
COMMIT_EVERY = 100


def find_db_file(explicit: str | None) -> str:
    if explicit:
        if not os.path.isfile(explicit):
            raise FileNotFoundError(f"DB file not found: {explicit}")
        return explicit
    for candidate in (f"/raid2/{DB_FILENAME}", f"./{DB_FILENAME}"):
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(f"DB file '{DB_FILENAME}' not found in /raid2/ or ./")


def detect_media_type(path: str) -> str | None:
    ext = pathlib.Path(path).suffix.lower()
    for media_type, exts in MEDIA_TYPES.items():
        if ext in exts:
            return media_type
    return None


def compute_new_hash(path: str, media_type: str, logger) -> str | None:
    if media_type == "image":
        media = TruImage(media_path=path, logger=logger)
    elif media_type == "video":
        media = TruVideo(media_path=path, logger=logger)
    else:
        return None
    return media.hash


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Rehash entries in pictures.db using current hashing logic.",
    )
    p.add_argument(
        "-d", "--db",
        dest="db",
        help=f"Path to DB file (default: /raid2/{DB_FILENAME} or ./{DB_FILENAME})",
        default=None,
    )
    p.add_argument(
        "-n", "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Compute new hashes and report, but don't write",
        default=False,
    )
    p.add_argument(
        "-p", "--prune-missing",
        dest="prune_missing",
        action="store_true",
        help="Delete rows whose file no longer exists on disk (default: keep them)",
        default=False,
    )
    p.add_argument(
        "-l", "--limit",
        dest="limit",
        type=int,
        default=None,
        help="Process at most N rows (debug)",
    )
    p.add_argument(
        "-v", "--verbose",
        dest="verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging on the console",
        default=False,
    )
    p.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        help="Disable the progress bar (use plain log output)",
        default=True,
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logger = get_logger(verbose=args.verbose)
    register_heif_opener()

    try:
        db_path = find_db_file(args.db)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1

    logger.info("DB: %s", db_path)
    if args.dry_run:
        logger.warning("DRY RUN: no changes will be written")
    if args.prune_missing:
        logger.info("Prune-missing enabled: rows for missing files will be deleted")
    if args.limit:
        logger.info("Row limit: %d", args.limit)

    with closing(sqlite3.connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT image_path, hash FROM {TABLE_NAME}")
        rows = cur.fetchall()
        if args.limit:
            rows = rows[: args.limit]

        total = len(rows)
        logger.info("Rows to process: %d", total)

        stats = {
            "updated": 0,
            "unchanged": 0,
            "missing_kept": 0,
            "missing_pruned": 0,
            "unhashable": 0,
            "unknown_type": 0,
        }
        pending_updates: list[tuple[str, str]] = []
        pending_deletes: list[tuple[str]] = []

        # tqdm renders to stderr by default, matching the project logger's stream.
        # disable=None lets tqdm auto-detect whether stderr is a TTY (which is
        # what we want when --no-progress is not set); --no-progress forces it off.
        bar = tqdm(
            total=total,
            unit="row",
            dynamic_ncols=True,
            disable=(not args.progress) or None,
            leave=False,
        )

        with logging_redirect_tqdm(loggers=[logger]), bar:
            for path, old_hash in rows:
                bar.set_postfix_str(_postfix(stats, path), refresh=False)

                if not os.path.isfile(path):
                    if args.prune_missing:
                        stats["missing_pruned"] += 1
                        pending_deletes.append((path,))
                        logger.debug("MISSING (pruned): %s", path)
                    else:
                        stats["missing_kept"] += 1
                        logger.warning("MISSING (kept): %s", path)
                    bar.update(1)
                    continue

                media_type = detect_media_type(path)
                if media_type is None:
                    stats["unknown_type"] += 1
                    logger.warning("UNKNOWN TYPE: %s", path)
                    bar.update(1)
                    continue

                try:
                    new_hash = compute_new_hash(path, media_type, logger)
                except Exception as exc:  # noqa: BLE001 -- migration tool, log and continue
                    stats["unhashable"] += 1
                    try:
                        exc_summary = f"{type(exc).__name__}: {exc!s}"
                    except Exception:  # noqa: BLE001
                        exc_summary = type(exc).__name__
                    logger.error("HASH ERROR: %s -- %s", path, exc_summary)
                    bar.update(1)
                    continue

                if not new_hash:
                    stats["unhashable"] += 1
                    logger.warning("HASH NONE: %s", path)
                    bar.update(1)
                    continue

                if new_hash == old_hash:
                    stats["unchanged"] += 1
                    logger.debug("UNCHANGED: %s", path)
                    bar.update(1)
                    continue

                stats["updated"] += 1
                logger.debug("UPDATE: %s  %s -> %s", path, old_hash, new_hash)
                pending_updates.append((new_hash, path))

                if not args.dry_run and len(pending_updates) >= COMMIT_EVERY:
                    cur.executemany(
                        f"UPDATE {TABLE_NAME} SET hash = ? WHERE image_path = ?",
                        pending_updates,
                    )
                    conn.commit()
                    logger.debug("Committed %d updates", len(pending_updates))
                    pending_updates.clear()

                bar.update(1)

        if not args.dry_run:
            if pending_updates:
                cur.executemany(
                    f"UPDATE {TABLE_NAME} SET hash = ? WHERE image_path = ?",
                    pending_updates,
                )
                logger.debug("Committed final %d updates", len(pending_updates))
            if pending_deletes:
                cur.executemany(
                    f"DELETE FROM {TABLE_NAME} WHERE image_path = ?",
                    pending_deletes,
                )
                logger.debug("Committed %d deletes", len(pending_deletes))
            conn.commit()

        logger.info("=" * 50)
        logger.info("REHASH SUMMARY")
        logger.info("=" * 50)
        for k in ("updated", "unchanged", "missing_kept", "missing_pruned", "unhashable", "unknown_type"):
            logger.info("  %-18s %6d", k, stats[k])
        logger.info("  %-18s %6d", "total", total)
        if args.dry_run:
            logger.warning("(dry run; nothing written)")
    return 0


def _postfix(stats: dict, current_path: str) -> str:
    label = os.path.basename(current_path)
    if len(label) > 40:
        label = "..." + label[-37:]
    return (
        f"upd={stats['updated']} unc={stats['unchanged']} "
        f"miss={stats['missing_kept'] + stats['missing_pruned']} "
        f"err={stats['unhashable']} {label}"
    )


if __name__ == "__main__":
    sys.exit(main())
