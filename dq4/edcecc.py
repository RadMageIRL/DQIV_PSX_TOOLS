"""Mode 2 EDC and ECC for PSX raw 2352-byte sectors. stdlib only.

Layout, Mode 2 Form 1 (subheader byte 2 bit 5 clear):
    0..12      sync
    12..16     header: min, sec, frame, mode
    16..24     subheader, 4 bytes repeated twice
    24..2072   user data, 2048 bytes
    2072..2076 EDC, little endian, over bytes [16, 2072)
    2076..2248 P parity, 172 bytes
    2248..2352 Q parity, 104 bytes

Mode 2 Form 2 (bit set): user data is 2324 bytes at [24, 2348), EDC at
[2348, 2352) over [16, 2348), and there is NO ECC. An all-zero EDC means the
mastering left it disabled, which is legal.

ECC is computed with the 4 header bytes treated as ZERO, which is what makes
Mode 2 ECC independent of the sector address.
"""

# EDC: CRC-32, polynomial 0x8001801B reflected, init 0, no final xor.
_EDC_LUT = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (0xD8018001 if _c & 1 else 0)
    _EDC_LUT.append(_c)

# GF(2^8) doubling table and its inverse, primitive polynomial 0x11D.
_F = [0] * 256
_B = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _F[_i] = _j
    _B[_i ^ _j] = _i


def edc(data):
    """CRC-32 (Mode 2 EDC) over an arbitrary byte range."""
    c = 0
    for b in data:
        c = _EDC_LUT[(c ^ b) & 0xFF] ^ (c >> 8)
    return c & 0xFFFFFFFF


def _block(src, major_count, minor_count, major_mult, minor_inc):
    """One RS pass over src, returning 2 * major_count parity bytes."""
    size = major_count * minor_count
    out = bytearray(2 * major_count)
    F, B = _F, _B
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = 0
        b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = F[a]
        a = B[F[a] ^ b]
        out[major] = a
        out[major + major_count] = a ^ b
    return bytes(out)


def ecc(sector):
    """(P parity 172 bytes, Q parity 104 bytes) for a Mode 2 Form 1 sector.

    Order matters. The Q pass indexes up to 52 * 43 = 2236 bytes from sector+12,
    which runs past the 2064 bytes of data into the P parity at 2076. So P is
    written into the working buffer first and Q is computed over data + P.
    """
    # sector[12:2248] = 4 header + 8 subheader + 2048 data + 4 EDC + 172 P
    src = bytearray(sector[12:2248])
    src[0:4] = bytes(4)                      # Mode 2: header treated as zero
    p = _block(src, 86, 24, 2, 86)
    src[2064:2236] = p                       # P must be in place before Q
    q = _block(src, 52, 43, 86, 88)
    return p, q


def is_form2(sector):
    return bool(sector[18] & 0x20)


def fix(sector):
    """Return the sector with EDC and ECC regenerated. Does not alter data."""
    s = bytearray(sector)
    if is_form2(s):
        # Form 2 EDC is optional. Leave a zero EDC alone: rewriting it would
        # change bytes the mastering deliberately left disabled.
        if s[2348:2352] != bytes(4):
            s[2348:2352] = edc(s[16:2348]).to_bytes(4, "little")
        return bytes(s)
    s[2072:2076] = edc(s[16:2072]).to_bytes(4, "little")
    p, q = ecc(s)
    s[2076:2248] = p
    s[2248:2352] = q
    return bytes(s)
