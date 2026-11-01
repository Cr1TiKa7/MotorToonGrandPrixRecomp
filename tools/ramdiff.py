"""Find RAM bytes whose values follow an expected sequence across snapshots.

Typical use: take one main-RAM snapshot (read_ram 0x80000000 0x200000) per
known game state (menu item 0, 1, 2, ...) and look for the byte that holds
the state.

    py -3 tools/ramdiff.py --snapshots s0.bin s1.bin s2.bin --expected 0 1 2

Prints matching addresses as 0x8XXXXXXX (at most 50), one per line.
"""

import argparse
import sys

RAM_BASE = 0x80000000
MAX_PRINT = 50


def candidates(snapshots, expected):
    """Offsets i where snapshots[k][i] == expected[k] for every k."""
    if len(snapshots) != len(expected):
        raise ValueError("need exactly one expected value per snapshot")
    if len({len(s) for s in snapshots}) > 1:
        raise ValueError("snapshots differ in length")
    first, rest = snapshots[0], list(zip(snapshots[1:], expected[1:]))
    hits = []
    pos = first.find(bytes([expected[0]]))
    while pos != -1:
        if all(snap[pos] == value for snap, value in rest):
            hits.append(pos)
        pos = first.find(bytes([expected[0]]), pos + 1)
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshots", nargs="+", required=True)
    ap.add_argument("--expected", nargs="+", type=int, required=True)
    args = ap.parse_args(argv)
    snaps = []
    for path in args.snapshots:
        with open(path, "rb") as fh:
            snaps.append(fh.read())
    hits = candidates(snaps, args.expected)
    for off in hits[:MAX_PRINT]:
        print(f"0x{RAM_BASE + off:08X}")
    if len(hits) > MAX_PRINT:
        print(f"... {len(hits) - MAX_PRINT} more", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
