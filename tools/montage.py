"""Stdlib-only contact sheet: py -3 tools/montage.py OUT.png COLS SCALE_DIV IN1.png IN2.png ...

Decodes 8-bit RGB/RGBA non-interlaced PNGs, downsamples by SCALE_DIV
(nearest), tiles them COLS wide with a 2-px gap and writes an RGB PNG.
"""

import struct
import sys
import zlib


def read_png(path):
    data = open(path, "rb").read()
    pos = 8
    idat = b""
    w = h = ctype = None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace:
                raise ValueError(f"{path}: unsupported PNG")
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows = []
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ft == 1:
                line[x] = (line[x] + a) & 255
            elif ft == 2:
                line[x] = (line[x] + b) & 255
            elif ft == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, bpp, rows


def main():
    out, cols, div = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    imgs = [read_png(p) for p in sys.argv[4:]]
    cw = max(i[0] for i in imgs) // div
    ch = max(i[1] for i in imgs) // div
    gap = 2
    nrows = (len(imgs) + cols - 1) // cols
    W = cols * (cw + gap)
    H = nrows * (ch + gap)
    canvas = [bytearray(b"\x40\x40\x40" * W) for _ in range(H)]
    for k, (w, h, bpp, rows) in enumerate(imgs):
        ox = (k % cols) * (cw + gap)
        oy = (k // cols) * (ch + gap)
        for y in range(min(ch, h // div)):
            src = rows[y * div]
            dst = canvas[oy + y]
            for x in range(min(cw, w // div)):
                s = x * div * bpp
                dst[(ox + x) * 3:(ox + x) * 3 + 3] = src[s:s + 3]
    raw = b"".join(b"\x00" + bytes(r) for r in canvas)
    png = b"\x89PNG\r\n\x1a\n"

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6))
    png += chunk(b"IEND", b"")
    open(out, "wb").write(png)


if __name__ == "__main__":
    main()
