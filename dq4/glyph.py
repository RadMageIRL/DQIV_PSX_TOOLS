"""Glyph atlas rendering.

Atlas wraps a 4bpp image and exposes cell extraction, ink extents and ASCII art.
find_atlases() pulls the atlas sub-blocks out of an archive.

  cell(slot)      intensities as a list of rows
  extent(slot)    (ink_percent, top, bottom, left, right)
  art(slot)       ASCII art rows for one cell
  art_row(slots)  several cells side by side

DQ4_LATIN_SLOTS maps the slots identified by hand to their letters. Those
identifications are human reads, not machine output.

Format details are in FORMAT.md section 8.
"""

CELL_W = 8
CELL_H = 14
ATLAS_W = 256

# Slots identified by hand in Phase 3b, DQ4's 16,128-byte atlas.
DQ4_LATIN_SLOTS = {26: "Z", 27: "X", 28: "V", 29: "T", 30: "R", 31: "P", 32: "N",
                   33: "L", 34: "J", 35: "H", 36: "F", 37: "D", 38: "B"}


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
        """[[intensity]] of one cell, cell_h rows by cell_w columns."""
        x0, y0 = self.slot_origin(slot)
        return [[self.pixel(x0 + dx, y0 + dy) for dx in range(self.cell_w)]
                for dy in range(self.cell_h)]

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
