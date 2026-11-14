"""Synthetic preview pixels only; no private model or printer required."""

from contextlib import redirect_stdout
import io
import struct
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import workspace_tempdir
from tools.extract_gx_preview import decode_preview, main


def sample(height=2):
    # width=1: each 3-byte BGR row has one byte of padding.
    rows = b"\xff\x00\x00\x00\x00\x00\xff\x00"  # blue then red in storage
    bmp = struct.pack("<2sIHHI", b"BM", 62, 0, 0, 54)
    bmp += struct.pack("<IiiHHIIiiII", 40, 1, height, 1, 24, 0, 8, 0, 0, 0, 0) + rows
    header = bytearray(58)
    header[:12] = b"xgcode 1.0\n\0"
    struct.pack_into("<4I", header, 12, 0, 58, 120, 120)
    return bytes(header) + bmp + b"; synthetic printer code unchanged\n"


class PreviewTests(unittest.TestCase):
    def test_bgr_bottom_up_and_row_padding(self):
        info, bmp, ppm = decode_preview(sample())
        self.assertEqual(info["row_padding_bytes"], 1)
        self.assertEqual(info["row_order"], "bottom-up")
        self.assertEqual(ppm, b"P6\n1 2\n255\n\xff\x00\x00\x00\x00\xff")
        self.assertEqual(bmp, sample()[58:120])

    def test_negative_height_is_top_down(self):
        info, _, ppm = decode_preview(sample(-2))
        self.assertEqual(info["row_order"], "top-down")
        self.assertEqual(ppm, b"P6\n1 2\n255\n\x00\x00\xff\xff\x00\x00")

    def test_bad_offsets_dimensions_and_compression_are_rejected(self):
        for offset, fmt, value in ((16, "<I", 0), (20, "<I", 99999), (60, "<I", 123),
                                   (76, "<i", -1), (80, "<i", 0), (86, "<H", 32), (88, "<I", 1)):
            blob = bytearray(sample())
            struct.pack_into(fmt, blob, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): decode_preview(bytes(blob))
        with self.assertRaises(ValueError): decode_preview(sample()[:60])
        with self.assertRaises(ValueError): decode_preview(b"not gx")

    def test_cli_preserves_source_and_refuses_output_overwrite(self):
        with workspace_tempdir() as folder:
            source, target = Path(folder)/"sample.gx", Path(folder)/"preview.bmp"
            source.write_bytes(sample())
            with patch("sys.argv", ["extract_gx_preview.py", str(source), "--output", str(target)]), redirect_stdout(io.StringIO()):
                main()
                with self.assertRaises(SystemExit): main()
            self.assertEqual(source.read_bytes(), sample())
            self.assertEqual(target.read_bytes(), sample()[58:120])
