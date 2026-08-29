"""Text blocks embedded in the type 46 MIPS overlays.

MEASURED, Phase 52. The archive's 612 type 46 sub-blocks are MIPS overlays, 600
of them LZS compressed, and they hold text blocks in the format of FORMAT.md
section 3: six-u32 header, 0x7Exx phrase dictionary, dual-base Huffman tree,
self pointer at `a`. There are 15 distinct blocks, ids 0x0473 to 0x048B, and not
one of those ids occurs in the archive population or the executable population.

This module is a LOCATOR, not a decoder. Everything it finds is handed to the
same TextBlock, HuffmanTree and dictionary the rest of the library uses, which
is the whole reason type 46 needed no new format work.

Two things make the locator honest rather than lucky:

  * a block is claimed only when the structural test passes AND the self pointer
    at `a` holds. 0 of the headers that pass fail to decode.
  * the answer does not depend on the filters. Relaxing the id range to
    0x0001..0xFFFF, or dropping the self pointer requirement, returns the same
    131 occurrences.

Deduplication is by text block CONTENT, because 612 sub-blocks hold only 188
distinct overlay images and those hold 131 occurrences of 15 distinct blocks.
"""

import collections
import struct

from . import hbd, lzs, textblock

OVERLAY_TYPE = 46


def overlay_images(arch, blocks):
    """{bytes: [(sector, sub index)]} for every distinct type 46 image.

    Decompressing is the only expensive step in the whole path, so callers that
    want both this and blocks() should pass the result through.
    """
    out = collections.defaultdict(list)
    for sector, sub in hbd.sub_blocks(blocks):
        if sub["type"] != OVERLAY_TYPE:
            continue
        raw = arch[sub["off"]:sub["off"] + sub["dlen"]]
        if sub["flags"] == hbd.FLAG_LZS:
            raw = lzs.decompress(raw)
        out[raw].append((sector, sub["idx"]))
    return dict(out)


def scan_image(img):
    """[(offset, TextBlock)] for one decompressed overlay.

    The structural test is gate 28's, corrected in Phase 46: a block with no
    dictionary has c == 24, one that has a dictionary carries it in [24, c) and
    sets f6 to 24.
    """
    out = []
    n = len(img)
    o = 0
    while o + 28 <= n:
        a, tid, c, d, e, f6 = struct.unpack_from("<6I", img, o)
        ok = (0x001 <= tid <= 0x600) and (24 < a < 0x40000) and (o + a + 4 <= n)
        if ok:
            if f6 == 0:
                ok = c == 24
            elif f6 == 24:
                ok = 24 < c < a
            else:
                ok = False
        if ok:
            ok = bool(e) and 24 < e <= a and c < e and (d == 0 or e < d <= a)
        if ok and struct.unpack_from("<I", img, o + a)[0] == a:
            try:
                tb = textblock.TextBlock(img[o:o + a + 4])
            except (struct.error, ValueError, IndexError):
                tb = None
            if tb is not None:
                out.append((o, tb))
                o += a
                continue
        o += 4
    return out


def blocks(arch, blocks_map, images=None):
    """[(TextBlock, sites)] deduplicated by text block content.

    `sites` is [(sector, sub index, offset)] for every place the block occurs,
    sorted, so the first entry is a stable identity for the corpus filename and
    the rest are the duplicate list.
    """
    if images is None:
        images = overlay_images(arch, blocks_map)
    seen = {}
    for img, where in images.items():
        for off, tb in scan_image(img):
            sites = seen.setdefault(tb.raw, [tb, []])[1]
            for sector, idx in where:
                sites.append((sector, idx, off))
    out = []
    for _raw, (tb, sites) in seen.items():
        out.append((tb, sorted(sites)))
    out.sort(key=lambda r: (r[0].id, r[1][0]))
    return out
