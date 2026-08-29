"""The two font tables, reconstructed from executable bytes.

A character code becomes a glyph through a chained hash table, not through
arithmetic. The lookup lives at 0x8008F7B0 and both fonts are registered from
fixed addresses inside SLPM_869.16, which is why no scan of the archive ever
found them.

  record(img, load, base)   the 24-byte font record for a registered block
  table(img, load, base)    {code: Entry} for that font, whole table
  cell_plane(descriptor)    (atlas cell, 2-bit plane) for a font 1 descriptor

FONT1 draws every character in a fixed 8 by 14 cell. FONT2 is proportional,
carries per-glyph width and height, and its pixels are a 2 bits per pixel run
length stream expanded on demand.

The atlas packs TWO glyphs into every cell, one in each 2-bit plane of the 4bpp
pixel, and bit 0 of the descriptor selects which plane is visible by choosing a
CLUT. Reading a cell as a single 4bpp image superimposes both glyphs; that error
survived three phases and is why cell_plane() exists.

Format details are in docs/FONTS.md.
"""

import collections
import struct

FONT1 = 0x800B2A3C          # 8 x 14 fixed cell, modulus 137
FONT2 = 0x800B3600          # proportional, modulus 29

Entry = collections.namedtuple("Entry", "code descriptor width height offset")


def _u16(img, load, va):
    return struct.unpack_from("<H", img, va - load)[0]


def _u32(img, load, va):
    return struct.unpack_from("<I", img, va - load)[0]


def record(img, load, base):
    """The 24-byte font record reached through the block header at base+12.

    Returns a dict. `buckets` and `glyphs` are offsets FROM THE BLOCK BASE, which
    is what makes them fragile: anything that moves the block's regions has to
    move them too.
    """
    rec = base + _u32(img, load, base + 12) + 4
    f = struct.unpack_from("<IIHHHHHHHH", img, rec - load)
    return {
        "address": rec,
        "buckets": f[0],
        "glyphs": f[1],
        "modulus": f[2],
        "font_id": f[3],
        "descriptors": f[5],
        "cell_w": f[8],
        "cell_h": f[9],
        # nonzero cell_w and cell_h select the 4-byte chain layout
        "stride": 4 if (f[8] and f[9]) else 8,
    }


def table(img, load, base):
    """{code: Entry} for the font registered at `base`.

    The walk is 0x8008F7B0's: bucket = code % modulus, the bucket halfword is a
    self relative offset to a chain, and a zero code terminates the chain. Bounded
    on every axis, so a code with no entry simply misses.
    """
    r = record(img, load, base)
    buckets = base + r["buckets"]
    stride = r["stride"]
    coff = 2 if stride == 4 else 4
    out = {}
    for b in range(r["modulus"]):
        slot = buckets + 2 * b
        head = _u16(img, load, slot)
        if head == 0:
            continue
        e = slot + head
        while True:
            code = _u16(img, load, e + coff)
            if code == 0:
                break
            if stride == 4:
                desc = _u16(img, load, e)
                w, h = r["cell_w"], r["cell_h"]
            else:
                desc = _u32(img, load, e)
                w = img[e - load + 6]
                h = img[e - load + 7]
            out.setdefault(code, Entry(code, desc, w, h, e))
            e += stride
    return out


def cell_plane(descriptor):
    """(atlas cell, plane) for a font 1 descriptor.

    The renderer does exactly this, at 0x80087364 to 0x80087374: bit 0 picks the
    CLUT and the rest is the cell index. Texture coordinates then follow as
    U = (cell % 32) * 8 and V = (cell / 32) * 14, read from 0x800873A8 onward.
    """
    return descriptor >> 1, descriptor & 1


def uv(cell, cols=32, cell_w=8, cell_h=14):
    """(U, V) for an atlas cell, as the renderer computes them."""
    return (cell % cols) * cell_w, (cell // cols) * cell_h

def missing(img, load, base, wanted):
    """Codes in `wanted` that have NO entry in the font table at `base`.

    A miss is SILENT at runtime: the lookup walks the bucket chain, finds no
    matching code, and draws nothing. Nothing on screen distinguishes a missing
    glyph from a space, which is why this is asserted rather than eyeballed.

    MENU text draws through FONT1 and DIALOGUE through FONT2 (Phase 59), and the
    two tables are NOT the same set: 435 codes are in both, 98 in font 1 only and
    86 in font 2 only. A string checked against the wrong table is not checked.
    """
    have = set(table(img, load, base))
    return sorted(c for c in wanted if c not in have)
