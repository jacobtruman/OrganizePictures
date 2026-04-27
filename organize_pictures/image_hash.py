"""
Cross-machine, version-stable image hashing.

The strategy mirrors `ffmpeg -c copy -f md5` for video: we don't decode pixels
(decoders aren't bit-identical across libjpeg/libheif/Pillow versions), and we
don't include metadata containers (EXIF, XMP, ICC, IPTC, comments, orientation
tags). Instead we hash only the bytes that determine what the picture actually
looks like.

Two files that came from the same camera shot but had EXIF rewritten / ICC
re-embedded / orientation tag changed / XMP appended will produce the same hash.
A re-encode (different JPEG quality, re-saved by Photos at lower quality, etc.)
will produce a different hash -- this is exact dedup, not perceptual.

Per-format strategy:
  - JPEG: walk the marker stream, strip APP0..APP15 / COM, hash everything else.
  - PNG: walk chunks, keep only IHDR/PLTE/tRNS/IDAT/IEND.
  - HEIC/HEIF/AVIF: route through `ffmpeg -c copy -f md5` (uses libheif under
    the hood) which reads only the coded image bitstream, ignoring all the
    container metadata items (Exif, XMP, etc.).
  - Anything else falls back to a plain file-bytes md5.
"""

from __future__ import annotations

import hashlib
import struct
from typing import BinaryIO

import ffmpeg


_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_HEIF_BRANDS = frozenset({
    b"heic", b"heix", b"hevc", b"hevx",
    b"heim", b"heis", b"hevm", b"hevs",
    b"mif1", b"msf1",
    b"avif", b"avis",
})


def hash_image_file(path: str) -> str | None:
    """
    Return a hex md5 over the picture-defining bytes of `path`, or None on error.

    Dispatch is by magic bytes (not extension) since extensions lie.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(16)
            f.seek(0)

            if head.startswith(_JPEG_MAGIC):
                return _hash_jpeg(f)
            if head.startswith(_PNG_MAGIC):
                return _hash_png(f)
            if _is_heif(head):
                # HEIC/HEIF: route through ffmpeg to extract just the coded image
                # bitstream (no EXIF/XMP/orientation/etc.), via libheif. Falls back
                # to raw md5 if ffmpeg can't read the file.
                heif_hash = _hash_via_ffmpeg(path)
                if heif_hash is not None:
                    return heif_hash
                f.seek(0)
                return _hash_raw(f)

            f.seek(0)
            return _hash_raw(f)
    except OSError:
        return None


def _hash_raw(f: BinaryIO) -> str:
    h = hashlib.md5()
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        h.update(chunk)
    return h.hexdigest()


def _hash_via_ffmpeg(path: str) -> str | None:
    """Run `ffmpeg -i <path> -c copy -f md5 -` and parse the resulting MD5= line."""
    try:
        stream = ffmpeg.input(path)
        stream = ffmpeg.output(stream, "pipe:", format="md5", codec="copy", loglevel="quiet")
        out, _ = ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
        line = out.decode("ascii", errors="replace").strip()
        if not line.startswith("MD5="):
            return None
        return line.split("=", 1)[1].strip()
    except (OSError, ffmpeg.Error):
        return None


# JPEG ------------------------------------------------------------------------
#
# A JPEG is a stream of segments. Each segment starts with 0xFF <marker>.
# - SOI (D8) and EOI (D9) have no length and no payload.
# - RSTn (D0..D7) and TEM (01) also have no length.
# - SOS (DA) is followed by a 2-byte length, then header, then entropy-coded
#   image data that runs until the next non-RST marker.
# - Everything else is followed by a 2-byte big-endian length (length includes
#   the length bytes themselves) and that many bytes of payload.
#
# We strip APP0..APP15 (E0..EF) and COM (FE). Those carry EXIF, XMP, ICC,
# JFIF, IPTC, MakerNotes, Adobe segments, comments. We keep DQT/DHT/SOFn/DRI/
# SOS+ECS/RSTn/EOI -- the bytes that decode to pixels.

def _hash_jpeg(f: BinaryIO) -> str | None:
    h = hashlib.md5()
    data = f.read()
    n = len(data)
    if n < 2 or data[0:2] != b"\xff\xd8":
        return None
    h.update(b"\xff\xd8")
    i = 2
    while i < n:
        if data[i] != 0xFF:
            return None
        # consume any 0xFF fill bytes
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            return None
        marker = data[i]
        i += 1

        if marker == 0xD9:  # EOI
            h.update(b"\xff\xd9")
            return h.hexdigest()
        if marker == 0x00 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            # standalone marker (escaped 0xFF, RSTn, TEM); RSTs only appear inside ECS
            # but if we see one here, just include it
            h.update(bytes([0xFF, marker]))
            continue

        if i + 2 > n:
            return None
        seg_len = struct.unpack(">H", data[i:i + 2])[0]
        if seg_len < 2 or i + seg_len > n:
            return None
        seg_payload_end = i + seg_len  # length includes its own 2 bytes

        is_metadata = (0xE0 <= marker <= 0xEF) or marker == 0xFE
        if not is_metadata:
            h.update(bytes([0xFF, marker]))
            h.update(data[i:seg_payload_end])

        i = seg_payload_end

        if marker == 0xDA:  # SOS -- entropy-coded data follows up to next non-RST marker
            ecs_start = i
            while i < n:
                if data[i] != 0xFF:
                    i += 1
                    continue
                # 0xFF found; check next byte
                if i + 1 >= n:
                    i += 1
                    continue
                nxt = data[i + 1]
                if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                    # 0xFF00 = stuffed byte, 0xFFD0..D7 = restart marker, both part of ECS
                    i += 2
                    continue
                # real marker -> end of ECS
                break
            h.update(data[ecs_start:i])
    return None


# PNG -------------------------------------------------------------------------
#
# A PNG is the 8-byte signature followed by chunks: 4-byte length (big-endian),
# 4-byte type, length bytes of data, 4-byte CRC.
#
# We hash chunks that influence pixel output: IHDR, PLTE, tRNS, IDAT, IEND.
# We skip text/metadata chunks: tEXt, iTXt, zTXt, eXIf, tIME, pHYs, gAMA, cHRM,
# sRGB, iCCP, bKGD, hIST, sPLT, sBIT.
# (gAMA/cHRM/sRGB/iCCP technically affect rendering but only via color
# management; for dedup of "is this the same picture" we want to ignore them.)

_PNG_PIXEL_CHUNKS = frozenset({b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"})


def _hash_png(f: BinaryIO) -> str | None:
    h = hashlib.md5()
    sig = f.read(8)
    if sig != _PNG_MAGIC:
        return None
    h.update(sig)
    while True:
        header = f.read(8)
        if len(header) != 8:
            return None
        length, ctype = struct.unpack(">I4s", header)
        data = f.read(length)
        if len(data) != length:
            return None
        crc = f.read(4)
        if len(crc) != 4:
            return None
        if ctype in _PNG_PIXEL_CHUNKS:
            h.update(header)
            h.update(data)
            h.update(crc)
        if ctype == b"IEND":
            return h.hexdigest()


# ISOBMFF (HEIC / HEIF / AVIF) ------------------------------------------------
#
# Pure-Python parsing of HEIC's iloc/iinf to separate picture-data items from
# Exif/XMP items is non-trivial and error-prone. Instead we shell out to ffmpeg
# (already a project dep), which uses libheif under the hood and reads only the
# coded image bitstream. `-c copy -f md5` then hashes those packets, ignoring
# all metadata. See `_hash_via_ffmpeg`.


def _is_heif(head: bytes) -> bool:
    if len(head) < 12:
        return False
    if head[4:8] != b"ftyp":
        return False
    return head[8:12] in _HEIF_BRANDS
