"""Text sub-block header parsing.

TextBlock parses the six-int header and the tree header and exposes the derived
region boundaries. It does not decode anything; pass it to huffman.HuffmanTree
for that, and to dictionary.parse() for the phrase table.

invariants_hold() checks the two header invariants. regions() returns a gap-free
map of the whole sub-block for inspection.

Format details are in FORMAT.md section 3.
"""

import struct

HEADER_SIZE = 24
TREE_HEADER_SIZE = 10


class TextBlock:
    """One type 40 / 42 sub-block, parsed but not decoded."""

    def __init__(self, raw):
        if len(raw) < HEADER_SIZE:
            raise ValueError("text block shorter than its header")
        self.raw = raw
        (self.a, self.id, self.c, self.d, self.e, self.f6) = struct.unpack_from("<6I", raw)
        self.id &= 0xFFFF
        self.tree_end = self.d if self.d != 0 else self.a
        self.base = struct.unpack_from("<I", raw, self.e)[0]
        self.mid = struct.unpack_from("<I", raw, self.e + 4)[0]
        self.root = struct.unpack_from("<H", raw, self.e + 8)[0]
        self.m = (self.mid - self.base) // 2
        self.npairs = (self.tree_end - self.base) // 2
        self.pairs = [(raw[self.base + i * 2], raw[self.base + i * 2 + 1])
                      for i in range(self.npairs)]

    # --- invariants -----------------------------------------------------

    def invariant_order(self):
        """First header invariant. See FORMAT.md section 3."""
        return self.c < self.e < self.tree_end

    def invariant_self_pointer(self):
        """Second header invariant. See FORMAT.md section 3."""
        if self.a + 4 > len(self.raw):
            return False
        return struct.unpack_from("<I", self.raw, self.a)[0] == self.a

    def invariants_hold(self):
        return self.invariant_order() and self.invariant_self_pointer()

    # --- regions --------------------------------------------------------

    def regions(self):
        """[(start, end, label)] covering the whole sub-block, gap free."""
        rec_start = self.d + 32
        return [
            (0, HEADER_SIZE, "header, six u32"),
            (HEADER_SIZE, self.c, "dictionary" if self.f6 else "dictionary (absent)"),
            (self.c, self.e, "huffman code stream"),
            (self.e, self.base, "tree header: base, mid, root"),
            (self.base, self.tree_end, "tree pair array (%d pairs)" % self.npairs),
            (self.tree_end, min(rec_start, self.a), "record table header"),
            (min(rec_start, self.a), self.a, "records and undecoded region"),
            (self.a, self.a + 4, "self pointer"),
            (self.a + 4, len(self.raw), "tail"),
        ]

    def code_stream(self):
        return self.raw[self.c:self.e]

    def has_dictionary(self):
        return self.f6 != 0
