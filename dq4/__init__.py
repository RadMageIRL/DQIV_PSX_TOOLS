"""dq4: read-only library for the Dragon Quest IV PlayStation disc.

Every module here is a port of a result that was measured and gated in Phases 0
through 3c. Nothing in this package extends those results, and nothing here
writes to a disc image.

  iso           Mode 2 Form 1 sector reads, ISO9660 directory parse, extraction
  hbd           HBD1PS1D block scanner, sub-block parser, type census
  textblock     type 40 / 42 six-int header, invariants, region map
  huffman       dual-base tree build, decode, encode
  dictionary    0x7Exx phrase table parse and expansion
  sectortable   level sector table locate, parse, LBA translation
  glyph         4bpp atlas render and cell extraction
  codes         control code table and census
  lzs           LZSS decompression
  lzs_comp      LZSS compression

The user supplies their own disc images. No ROM data ships here.
"""

from . import iso, hbd, textblock, huffman, dictionary, sectortable, glyph, codes
from . import lzs, lzs_comp

__all__ = ["iso", "hbd", "textblock", "huffman", "dictionary",
           "sectortable", "glyph", "codes", "lzs", "lzs_comp"]
