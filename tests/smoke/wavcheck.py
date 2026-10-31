"""Loudness of a 16-bit PCM WAV (stdlib only)."""

import array
import math
import sys
import wave


def wav_rms(path):
    """RMS over every sample of every channel; 0.0 for an empty file."""
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM, got {8 * w.getsampwidth()}-bit")
        samples = array.array("h")
        samples.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))
