"""LZSS decompression.

decompress(src) returns the full output of an LZSS stream. It stops when the
input is exhausted, so the final match may overrun the declared uncompressed
length by up to F-1 bytes; callers that want the declared size should slice.

decompress_exact(src, n) does that slice for you.

The ring buffer is ZERO filled, not filled with 0x20. That is the one detail
that separates this from the textbook implementation and it is not optional.

Format details are in FORMAT.md section 2.
"""

N = 4096          # ring buffer size
F = 18            # longest match
THRESHOLD = 2     # minimum match is THRESHOLD + 1
INIT = 0x00       # ring fill byte


def decompress(src):
    """Full LZSS output for src. May overrun the declared length; see module docstring."""
    ring = bytearray(N)
    if INIT:
        for i in range(N):
            ring[i] = INIT
    r = N - F
    out = bytearray()
    i = 0
    n = len(src)
    flags = 0
    while i < n:
        flags >>= 1
        if not (flags & 0x100):
            if i >= n:
                break
            flags = src[i] | 0xFF00
            i += 1
        if flags & 1:
            if i >= n:
                break
            c = src[i]
            i += 1
            out.append(c)
            ring[r] = c
            r = (r + 1) & (N - 1)
        else:
            if i + 1 >= n:
                break
            a = src[i]
            b = src[i + 1]
            i += 2
            off = ((b & 0xF0) << 4) | a
            ln = (b & 0x0F) + THRESHOLD + 1
            for k in range(ln):
                c = ring[(off + k) & (N - 1)]
                out.append(c)
                ring[r] = c
                r = (r + 1) & (N - 1)
    return bytes(out)


def decompress_exact(src, uncompressed_length):
    """Output trimmed to the declared length."""
    return decompress(src)[:uncompressed_length]


def overrun(src, uncompressed_length):
    """len(natural output) - declared length. 0 or +3 on every valid block."""
    return len(decompress(src)) - uncompressed_length
