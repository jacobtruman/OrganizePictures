"""Tests for organize_pictures.image_hash."""
import io
import struct
from unittest.mock import patch

import piexif
import pytest
from PIL import Image, PngImagePlugin

from organize_pictures.image_hash import hash_image_file


# JPEG ------------------------------------------------------------------------

class TestJPEGHashing:
    """Format-aware JPEG hashing should ignore metadata segments."""

    def _write_jpeg(self, path, exif_bytes=None, comment=None, color="red"):
        img = Image.new("RGB", (32, 32), color)
        kwargs = {"format": "JPEG", "quality": 85}
        if exif_bytes is not None:
            kwargs["exif"] = exif_bytes
        if comment is not None:
            kwargs["comment"] = comment
        img.save(path, **kwargs)

    def test_returns_md5_hex(self, tmp_path):
        p = tmp_path / "a.jpg"
        self._write_jpeg(p)
        digest = hash_image_file(str(p))
        assert digest is not None
        assert len(digest) == 32
        int(digest, 16)  # hex

    def test_same_image_different_exif_same_hash(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        exif_a = piexif.dump({
            "0th": {piexif.ImageIFD.Make: b"AcmeCam"},
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2020:01:01 00:00:00"},
        })
        exif_b = piexif.dump({
            "0th": {piexif.ImageIFD.Make: b"DifferentCam"},
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2099:12:31 23:59:59"},
        })
        self._write_jpeg(a, exif_bytes=exif_a)
        self._write_jpeg(b, exif_bytes=exif_b)
        assert a.read_bytes() != b.read_bytes()
        assert hash_image_file(str(a)) == hash_image_file(str(b))

    def test_same_image_with_and_without_exif_same_hash(self, tmp_path):
        a = tmp_path / "no_exif.jpg"
        b = tmp_path / "with_exif.jpg"
        self._write_jpeg(a)
        self._write_jpeg(b, exif_bytes=piexif.dump({"0th": {piexif.ImageIFD.Make: b"X"}}))
        assert hash_image_file(str(a)) == hash_image_file(str(b))

    def test_same_image_different_comment_same_hash(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        self._write_jpeg(a, comment=b"hello")
        self._write_jpeg(b, comment=b"goodbye")
        assert hash_image_file(str(a)) == hash_image_file(str(b))

    def test_different_pixels_different_hash(self, tmp_path):
        a = tmp_path / "red.jpg"
        b = tmp_path / "blue.jpg"
        self._write_jpeg(a, color="red")
        self._write_jpeg(b, color="blue")
        assert hash_image_file(str(a)) != hash_image_file(str(b))

    def test_truncated_jpeg_returns_none(self, tmp_path):
        p = tmp_path / "trunc.jpg"
        self._write_jpeg(p)
        data = p.read_bytes()
        p.write_bytes(data[: len(data) // 2])
        assert hash_image_file(str(p)) is None


# PNG -------------------------------------------------------------------------

class TestPNGHashing:
    """PNG hashing should include pixel-affecting chunks and ignore text/eXIf/tIME."""

    def _write_png(self, path, color="red"):
        img = Image.new("RGB", (32, 32), color)
        img.save(path, format="PNG")

    def test_returns_md5_hex(self, tmp_path):
        p = tmp_path / "a.png"
        self._write_png(p)
        digest = hash_image_file(str(p))
        assert digest is not None
        assert len(digest) == 32

    def test_text_chunks_ignored(self, tmp_path):
        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        img = Image.new("RGB", (32, 32), "red")
        info_a = PngImagePlugin.PngInfo()
        info_a.add_text("Author", "alice")
        info_b = PngImagePlugin.PngInfo()
        info_b.add_text("Author", "bob")
        info_b.add_text("Comment", "different")
        img.save(a, format="PNG", pnginfo=info_a)
        img.save(b, format="PNG", pnginfo=info_b)
        assert a.read_bytes() != b.read_bytes()
        assert hash_image_file(str(a)) == hash_image_file(str(b))

    def test_different_pixels_different_hash(self, tmp_path):
        a = tmp_path / "r.png"
        b = tmp_path / "b.png"
        self._write_png(a, color="red")
        self._write_png(b, color="blue")
        assert hash_image_file(str(a)) != hash_image_file(str(b))

    def test_truncated_png_returns_none(self, tmp_path):
        p = tmp_path / "trunc.png"
        self._write_png(p)
        data = p.read_bytes()
        p.write_bytes(data[:20])
        assert hash_image_file(str(p)) is None


# ISOBMFF / HEIF --------------------------------------------------------------
#
# HEIC hashing routes through `ffmpeg -c copy -f md5`. We test the dispatch and
# parsing here with mocked ffmpeg; the real-file metadata-insensitivity guarantee
# is provided by ffmpeg/libheif itself and was validated end-to-end in the
# review process against actual Google Takeout HEIC files.

def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + box_type + payload


def _ftyp(major: bytes = b"heic") -> bytes:
    return _box(b"ftyp", major + b"\x00\x00\x00\x00" + b"heic" + b"mif1")


def _minimal_heif_bytes() -> bytes:
    return _ftyp() + _box(b"meta", b"\x00\x00\x00\x00") + _box(b"mdat", b"PIXELS")


class TestISOBMFFHashing:

    def test_dispatches_to_ffmpeg_on_heif_brand(self, tmp_path):
        p = tmp_path / "a.heic"
        p.write_bytes(_minimal_heif_bytes())
        with patch("organize_pictures.image_hash.ffmpeg") as mock_ffmpeg:
            mock_ffmpeg.input.return_value = "stream"
            mock_ffmpeg.output.return_value = "stream"
            mock_ffmpeg.run.return_value = (b"MD5=cafebabecafebabecafebabecafebabe\n", b"")
            digest = hash_image_file(str(p))
            assert digest == "cafebabecafebabecafebabecafebabe"
            mock_ffmpeg.output.assert_called_once()
            _, kwargs = mock_ffmpeg.output.call_args
            assert kwargs.get("format") == "md5"
            assert kwargs.get("codec") == "copy"

    def test_falls_back_to_raw_md5_on_ffmpeg_error(self, tmp_path):
        import hashlib

        p = tmp_path / "a.heic"
        payload = _minimal_heif_bytes()
        p.write_bytes(payload)
        expected = hashlib.md5(payload).hexdigest()

        with patch("organize_pictures.image_hash.ffmpeg") as mock_ffmpeg:
            class FakeFFmpegError(Exception):
                pass
            mock_ffmpeg.Error = FakeFFmpegError
            mock_ffmpeg.input.side_effect = FakeFFmpegError("not a real heic")
            digest = hash_image_file(str(p))
            assert digest == expected

    def test_falls_back_when_ffmpeg_output_unparseable(self, tmp_path):
        import hashlib

        p = tmp_path / "a.heic"
        payload = _minimal_heif_bytes()
        p.write_bytes(payload)
        expected = hashlib.md5(payload).hexdigest()

        with patch("organize_pictures.image_hash.ffmpeg") as mock_ffmpeg:
            mock_ffmpeg.input.return_value = "stream"
            mock_ffmpeg.output.return_value = "stream"
            mock_ffmpeg.run.return_value = (b"garbage output without MD5 prefix\n", b"")
            digest = hash_image_file(str(p))
            assert digest == expected


# Fallback / dispatch ---------------------------------------------------------

class TestFallback:

    def test_unknown_format_falls_back_to_raw_md5(self, tmp_path):
        import hashlib

        p = tmp_path / "blob.bin"
        payload = b"this is not a recognized image format"
        p.write_bytes(payload)
        expected = hashlib.md5(payload).hexdigest()
        assert hash_image_file(str(p)) == expected

    def test_missing_file_returns_none(self, tmp_path):
        assert hash_image_file(str(tmp_path / "nope.jpg")) is None
