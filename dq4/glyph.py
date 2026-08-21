"""Glyph atlas rendering.

Atlas wraps a 4bpp image and exposes cell extraction, ink extents and ASCII art.
find_atlases() pulls the atlas sub-blocks out of an archive.

  cell(slot)          raw 4bpp values as a list of rows
  plane(slot, p)      one 2-bit plane, which is ONE glyph
  extent(slot)        (ink_percent, top, bottom, left, right)
  art(slot)           ASCII art rows for one cell
  plane_art(slot, p)  ASCII art for a single glyph
  art_row(slots)      several cells side by side

IMPORTANT: the atlas packs TWO glyphs into every cell, one in each 2-bit plane of
the 4bpp pixel, and bit 0 of a character's font descriptor selects which is
visible by choosing a CLUT. cell() and art() return the superposition of both,
which is rarely what you want. Use plane() and dq4.fonts.cell_plane().

A constant DQ4_LATIN_SLOTS used to live here, mapping 13 cells to 13 capitals
identified by hand. It has been REMOVED. It was reading superimposed planes, and
the atlas in fact carries all 26 capitals, all 26 lowercase and all 10 digits.
Derive the mapping from dq4.fonts.table() rather than from a hand-made dict.

Format details are in FORMAT.md sections 8 and 15.
"""

CELL_W = 8
CELL_H = 14
ATLAS_W = 256
PLANES = 2


class Atlas:
    """A 4bpp image, low nibble first."""

    def __init__(self, buf, width=ATLAS_W, cell_w=CELL_W, cell_h=CELL_H):
        self.buf = buf
        self.width = width
        self.cell_w = cell_w
        self.cell_h = cell_h
        self.height = (len(buf) * 2) // width
        self.cols = width // cell_w
        self.bands = self.height // cell_h
        self.slots = self.cols * self.bands

    def pixel(self, x, y):
        i = y * self.width + x
        b = self.buf[i >> 1]
        return (b & 0x0F) if (i & 1) == 0 else (b >> 4)

    def slot_origin(self, slot):
        band, col = divmod(slot, self.cols)
        return col * self.cell_w, band * self.cell_h

    def cell(self, slot):
        """[[intensity]] of one cell, cell_h rows by cell_w columns.

        This is the RAW 4bpp value, which superimposes both glyphs stored in the
        cell. For a single glyph use plane().
        """
        x0, y0 = self.slot_origin(slot)
        return [[self.pixel(x0 + dx, y0 + dy) for dx in range(self.cell_w)]
                for dy in range(self.cell_h)]

    def plane(self, slot, plane):
        """[[0..3]] for ONE glyph: the given 2-bit plane of the cell."""
        if plane not in (0, 1):
            raise ValueError("plane must be 0 or 1, got %r" % (plane,))
        sh = 2 * plane
        return [[(v >> sh) & 3 for v in row] for row in self.cell(slot)]

    def plane_ink(self, slot, plane):
        """Number of non-zero pixels in one glyph. Zero means no glyph there."""
        return sum(1 for row in self.plane(slot, plane) for v in row if v)

    def plane_art(self, slot, plane, hi=2):
        """[str] ASCII art for a single glyph, '#' dark, '+' faint, '.' clear."""
        return ["".join("#" if v >= hi else ("+" if v else ".") for v in row)
                for row in self.plane(slot, plane)]

    def extent(self, slot):
        """(ink_percent, top, bottom, left, right) or (0, None, None, None, None)."""
        c = self.cell(slot)
        pts = [(dy, dx) for dy in range(self.cell_h) for dx in range(self.cell_w) if c[dy][dx]]
        if not pts:
            return 0.0, None, None, None, None
        top = min(p[0] for p in pts)
        bot = max(p[0] for p in pts)
        left = min(p[1] for p in pts)
        right = max(p[1] for p in pts)
        ink = 100.0 * len(pts) / (self.cell_w * self.cell_h)
        return ink, top, bot, left, right

    def is_blank(self, slot):
        return self.extent(slot)[0] == 0.0

    def non_blank_count(self):
        return sum(1 for s in range(self.slots) if not self.is_blank(s))

    def art(self, slot, hi=8, mid=3):
        """[str] ASCII art for one cell, '#' dark, '+' mid, '.' clear."""
        c = self.cell(slot)
        out = []
        for row in c:
            out.append("".join("#" if v >= hi else ("+" if v >= mid else ".") for v in row))
        return out

    def art_row(self, slots, hi=8, mid=3):
        """[str] several cells side by side."""
        cells = [self.art(s, hi, mid) for s in slots]
        return [" ".join(c[r] for c in cells) for r in range(self.cell_h)]


def find_atlases(buf, blocks, atlas_type=1):
    """[(sector, idx, bytes)] for every type 1 sub-block."""
    out = []
    for s in sorted(blocks):
        for sb in blocks[s]["subs"]:
            if sb["type"] == atlas_type:
                out.append((s, sb["idx"], buf[sb["off"]:sb["off"] + sb["dlen"]]))
    return out
