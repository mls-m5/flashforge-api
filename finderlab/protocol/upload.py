"""Framing verified in FINDER-UPLOAD-005/006, not a universal firmware spec."""

import struct
import zlib

MAGIC = b"\x5a\x5a\xa5\xa5"
BLOCK_SIZE = 4096
HEADER = struct.Struct("!4sIII")
FRAME_SIZE = HEADER.size + BLOCK_SIZE


def encode_frame(index: int, data: bytes) -> bytes:
    """Encode one logical block without modifying GX/container/thumbnail bytes."""
    if not 0 <= index <= 0xFFFFFFFF or not 1 <= len(data) <= BLOCK_SIZE:
        raise ValueError("Invalid upload block index or logical length")
    return HEADER.pack(MAGIC, index, len(data), zlib.crc32(data)) + data.ljust(BLOCK_SIZE, b"\x00")


def decode_frame(frame: bytes, expected_index: int, remaining: int) -> bytes:
    """Validate one captured-style frame and return only its logical file bytes.

    Error/retry behavior was not captured. The mock closes on invalid framing;
    it does not invent retransmission semantics or silently fall back to raw data.
    """
    if len(frame) != FRAME_SIZE:
        raise ValueError("Invalid upload frame size")
    magic, index, length, crc = HEADER.unpack_from(frame)
    if magic != MAGIC:
        raise ValueError("Invalid upload magic")
    if index != expected_index:
        raise ValueError("Unexpected upload block index")
    if remaining <= 0 or length != min(BLOCK_SIZE, remaining):
        raise ValueError("Invalid upload block length")
    data = frame[HEADER.size:HEADER.size + length]
    if zlib.crc32(data) != crc:
        raise ValueError("Invalid upload CRC32")
    if any(frame[HEADER.size + length:]):
        raise ValueError("Nonzero upload padding")
    return data
