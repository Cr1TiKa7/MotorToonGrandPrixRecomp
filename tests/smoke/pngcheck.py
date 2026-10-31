"""Inspect PNG screenshots: distinct colors and pixel difference (stdlib only).

Supports 8-bit RGB (color type 2) and RGBA (color type 6), non-interlaced,
all five PNG filter types. Anything else raises ValueError.
"""

import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _read_chunks(data):
    pos = len(_SIGNATURE)
    while pos + 8 <= len(data):
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        yield tag, data[pos + 8:pos + 8 + length]
        pos += 12 + length


def read_pixels(path):
    """(width, height, bytes_per_pixel, rows) with every row unfiltered."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(_SIGNATURE):
        raise ValueError(f"{path}: not a PNG")

    width = height = bpp = None
    idat = bytearray()
    for tag, body in _read_chunks(data):
        if tag == b"IHDR":
            width, height, depth, ctype, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace != 0:
                raise ValueError(
                    f"{path}: unsupported PNG (depth={depth}, color type={ctype}, interlace={interlace})"
                )
            bpp = 3 if ctype == 2 else 4
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if width is None:
        raise ValueError(f"{path}: missing IHDR")

    raw = zlib.decompress(bytes(idat))
    stride = width * bpp
    prev = bytearray(stride)
    rows = []
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            if ftype == 1:
                row[i] = (row[i] + a) & 0xFF
            elif ftype == 2:
                row[i] = (row[i] + b) & 0xFF
            elif ftype == 3:
                row[i] = (row[i] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                c = prev[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + _paeth(a, b, c)) & 0xFF
            elif ftype != 0:
                raise ValueError(f"{path}: bad filter type {ftype}")
        rows.append(bytes(row))
        prev = row
    return width, height, bpp, rows


def distinct_colors(path, limit=256):
    _w, _h, bpp, rows = read_pixels(path)
    seen = set()
    for row in rows:
        for i in range(0, len(row), bpp):
            seen.add(row[i:i + bpp])
            if len(seen) >= limit:
                return limit
    return len(seen)


def mean_abs_diff(path_a, path_b):
    """Mean absolute difference over every channel byte of two same-size PNGs."""
    wa, ha, bpa, rows_a = read_pixels(path_a)
    wb, hb, bpb, rows_b = read_pixels(path_b)
    if (wa, ha, bpa) != (wb, hb, bpb):
        raise ValueError(f"size mismatch: {wa}x{ha}x{bpa} vs {wb}x{hb}x{bpb}")
    total = sum(abs(x - y) for ra, rb in zip(rows_a, rows_b) for x, y in zip(ra, rb))
    return total / (wa * ha * bpa)


def diff_share(path_a, path_b):
    """Share of pixels whose bytes differ (0..1). A size change (display mode
    switch, e.g. menu 320 wide vs race 512 wide) counts as a full change."""
    wa, ha, bpa, rows_a = read_pixels(path_a)
    wb, hb, bpb, rows_b = read_pixels(path_b)
    if (wa, ha, bpa) != (wb, hb, bpb):
        return 1.0
    changed = 0
    for ra, rb in zip(rows_a, rows_b):
        if ra == rb:
            continue
        changed += sum(1 for i in range(0, len(ra), bpa) if ra[i:i + bpa] != rb[i:i + bpa])
    return changed / (wa * ha)


def half_diffs(path_a, path_b):
    """(top, bottom): mean absolute difference of the upper and lower half (split screen)."""
    wa, ha, bpa, rows_a = read_pixels(path_a)
    wb, hb, bpb, rows_b = read_pixels(path_b)
    if (wa, ha, bpa) != (wb, hb, bpb):
        raise ValueError(f"size mismatch: {wa}x{ha}x{bpa} vs {wb}x{hb}x{bpb}")
    mid = ha // 2

    def diff(lo, hi):
        total = sum(abs(x - y) for ra, rb in zip(rows_a[lo:hi], rows_b[lo:hi]) for x, y in zip(ra, rb))
        return total / ((hi - lo) * wa * bpa)

    return diff(0, mid), diff(mid, ha)
