#!/usr/bin/env python3
"""Extract the observed GX embedded 24-bit BMP without changing printer code.

Supports only the reviewed xgcode 1.0 / BITMAPINFOHEADER / BI_RGB layout.
No printer connection, slicer invocation, rendering or GX generation.
"""

import argparse
import json
from pathlib import Path
import struct

MAX_SIZE = 64 * 1024 * 1024


def decode_preview(data):
    if not 58 <= len(data) <= MAX_SIZE or data[:12] != b"xgcode 1.0\n\x00":
        raise ValueError("Expected a bounded xgcode 1.0 file with the observed 58-byte header")
    reserved, image_offset, code_offset, secondary_offset = struct.unpack_from("<4I", data, 12)
    if not 58 <= image_offset < code_offset <= len(data):
        raise ValueError("Invalid GX preview/code offsets")
    bmp = data[image_offset:code_offset]
    if len(bmp) < 54:
        raise ValueError("Truncated BMP")
    magic, size, r1, r2, pixels = struct.unpack_from("<2sIHHI", bmp)
    dib, width, height, planes, depth, compression, image_size, xppm, yppm, colors, important = struct.unpack_from("<IiiHHIIiiII", bmp, 14)
    if (magic != b"BM" or size != len(bmp) or r1 or r2 or pixels != 54 or dib != 40
            or planes != 1 or depth != 24 or compression != 0 or colors != 0
            or not 1 <= width <= 2048 or not 1 <= abs(height) <= 2048):
        raise ValueError("Unsupported BMP layout; expected uncompressed bounded 24-bit RGB")
    stride = (width * 3 + 3) & ~3
    if len(bmp) != pixels + stride * abs(height) or image_size not in (0, stride * abs(height)):
        raise ValueError("BMP pixel length/stride does not match dimensions")
    rgb = bytearray()
    rows = range(abs(height)-1, -1, -1) if height > 0 else range(abs(height))
    for row in rows:
        raw = bmp[pixels + row * stride:pixels + row * stride + width * 3]
        for index in range(0, len(raw), 3):
            rgb.extend((raw[index+2], raw[index+1], raw[index]))
    info = {"gx_preview_offset": image_offset, "gx_code_offset": code_offset,
            "gx_u32_at_12": reserved, "gx_u32_at_24": secondary_offset,
            "unknown_gx_fields_not_interpreted": True,
            "width": width, "height": abs(height), "bmp_bytes": len(bmp),
            "bits_per_pixel": depth, "compression": "BI_RGB (uncompressed)",
            "pixel_order": "BGR", "row_order": "bottom-up" if height > 0 else "top-down",
            "stride_bytes": stride, "row_padding_bytes": stride-width*3,
            "pixels_per_metre": [xppm, yppm]}
    ppm = f"P6\n{width} {abs(height)}\n255\n".encode("ascii") + rgb
    return info, bmp, ppm


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("file", type=Path)
    cli.add_argument("--output", type=Path, help="new .bmp (original image bytes) or .ppm (decoded RGB) file")
    args = cli.parse_args()
    try:
        with args.file.open("rb") as reader:
            data = reader.read(MAX_SIZE + 1)
        info, bmp, ppm = decode_preview(data)
        if args.output:
            suffix = args.output.suffix.lower()
            if suffix not in (".bmp", ".ppm"):
                raise ValueError("Output must use .bmp or .ppm")
            with args.output.open("xb") as writer:
                writer.write(bmp if suffix == ".bmp" else ppm)
        print(json.dumps(info, indent=2))
    except (ValueError, OSError) as exc:
        cli.exit(1, f"Cannot extract GX preview: {exc}\n")


if __name__ == "__main__":
    main()
