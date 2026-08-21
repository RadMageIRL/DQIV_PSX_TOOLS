"""Who points at which string.

Three measured referrer systems, all carrying the same 32-bit word,
`(text id << 20) | bit offset from the block base`:

  LOOKUP  tail record tables inside type 40 and 42 text blocks   (Phase 10)
  TABLE   word 0 to 2 of each 60-byte type 26 record             (Phase 11, 12)
  ROSTER  word-aligned entries in type 44 sub-blocks             (Phase 12)

Plus the same TABLE mechanism reaching the two executable-resident blocks from
static tables in SLPM_869.16.

Every referrer this module reports was verified against the corpus by a gate:
the offset must land exactly on a string start, and a one-bit shift in either
direction must destroy the match. Nothing here is inferred. Strings with no
entry are UNRESOLVED, which means no referrer has been found, not that none
exists.
"""
import collections
import struct

from . import hbd, huffman, lzs, textblock

LOOKUP, TABLE, ROSTER = "LOOKUP", "TABLE", "ROSTER"

# type 26 records are 60 bytes; the reference sits in words 0 to 2, and words
# 3 to 11 never hold a text id in any of the 2,425 records on the disc.
T26_RECORD_WORDS = 15
T26_REF_WORDS = 3

# the two executable tables the disassembly names, as (base VA, stride, fields)
EXE_TABLES = ((0x800A9FA0, 48, (20, 24)), (0x80019CE4, 16, (8,)))


def block_index(arch, blocks):
    """{text id: (TextBlock, [bit offset per string], {offset: index})}."""
    out = {}
    for sector, sub in sorted(hbd.text_sub_blocks(blocks),
                              key=lambda p: (p[0], p[1]["idx"])):
        tb = textblock.TextBlock(hbd.sub_bytes(arch, sub))
        if tb.id in out:
            continue
        offs = huffman.string_offsets(tb)
        out[tb.id] = (tb, offs, {o: i for i, o in enumerate(offs)})
    return out


def _resolve(index, word):
    """(text id, string index) for a reference word, or None."""
    tid = word >> 20
    ent = index.get(tid)
    if ent is None:
        return None
    tb, offs, pos = ent
    i = pos.get((word & 0xFFFFF) - tb.c * 8)
    # the final offset begins the trailing residue, not a string
    if i is None or i + 1 >= len(offs):
        return None
    return tid, i


def _distinct(arch, blocks, want_type):
    """[(sector, sub, bytes)] for one sub-block per distinct content."""
    out, seen = [], set()
    for sector, sub in sorted(hbd.sub_blocks(blocks),
                              key=lambda p: (p[0], p[1]["idx"])):
        if sub["type"] != want_type:
            continue
        raw = hbd.sub_bytes(arch, sub)
        if sub["flags"] == hbd.FLAG_LZS:
            try:
                raw = lzs.decompress(raw, sub["ulen"])
            except Exception:
                continue
        if raw in seen:
            continue
        seen.add(raw)
        out.append((sector, sub, raw))
    return out


def tail_records(tb, raw):
    """[(index, A, B, byte offset of the record)] from the block's tail table."""
    self_ptr = ((tb.a + 3) // 4) * 4
    if self_ptr + 8 > len(raw):
        return []
    if struct.unpack_from("<I", raw, self_ptr)[0] != tb.a:
        return []
    count = struct.unpack_from("<I", raw, self_ptr + 4)[0]
    base = self_ptr + 8
    if count <= 0 or base + 8 * count > len(raw):
        return []
    out = []
    for i in range(count):
        o = base + 8 * i
        a, b = struct.unpack_from("<2I", raw, o)
        out.append((i, a, b, o))
    return out


def build(arch, blocks, index=None):
    """{(text id, string index): [(system, location text)]}, archive only."""
    if index is None:
        index = block_index(arch, blocks)
    refs = collections.defaultdict(list)

    # LOOKUP: one sub-block per text id, since byte-identical copies repeat it
    for tid in sorted(index):
        tb = index[tid][0]
        for i, _a, b, off in tail_records(tb, tb.raw):
            hit = _resolve(index, b)
            if hit is not None:
                refs[hit].append((LOOKUP, "record %d @ tail+0x%X" % (i, off)))

    # TABLE: word 0 to 2 of each 60-byte type 26 record
    for sector, sub, raw in _distinct(arch, blocks, 26):
        for k in range(len(raw) // 4):
            if k % T26_RECORD_WORDS >= T26_REF_WORDS:
                continue
            hit = _resolve(index, struct.unpack_from("<I", raw, 4 * k)[0])
            if hit is not None:
                refs[hit].append(
                    (TABLE, "type 26 sector %d sub %d +0x%X"
                     % (sector, sub["idx"], 4 * k)))

    # ROSTER: word-aligned entries in type 44
    for sector, sub, raw in _distinct(arch, blocks, 44):
        for o in range(0, len(raw) - 3, 4):
            hit = _resolve(index, struct.unpack_from("<I", raw, o)[0])
            if hit is not None:
                refs[hit].append(
                    (ROSTER, "type 44 sector %d sub %d +0x%X"
                     % (sector, sub["idx"], o)))
    return dict(refs)


# ---------------------------------------------------------------- executable

def exe_blocks(exe, load, toff, tsize):
    """[(va, TextBlock)] for text blocks embedded in the executable.

    Located by the six-u32 header signature, the same structural test used on
    DW7 in Phase 6: c == 24, a plausible a, and e either zero or inside a.
    """
    out = []
    for o in range(0, tsize - 24, 4):
        a, bid, c, d, e, f6 = struct.unpack_from("<6I", exe, toff + o)
        if c != 24 or not (0x001 <= bid <= 0x600) or not (24 < a < 0x40000):
            continue
        if e and not (24 < e <= a):
            continue
        if toff + o + a > len(exe):
            continue
        out.append((load + o, textblock.TextBlock(exe[toff + o:toff + o + a + 4])))
    return out


def exe_refs(exe, load, toff, tsize, index):
    """{(text id, string index): [(system, location)]} for EXE-resident blocks.

    Two sources: the tables the disassembly names, and every other word in the
    image whose top 12 bits are one of those block ids. A blind sweep of the
    whole image for ARCHIVE ids is noise (103 hits against a shuffled 104), so
    it is deliberately not done here; only ids that name an EXE block count.
    """
    refs = collections.defaultdict(list)
    named = set()
    for base, stride, fields in EXE_TABLES:
        for i in range(4096):
            stop = False
            for f in fields:
                va = base + stride * i + f
                o = toff + (va - load)
                if not (0 <= va - load < tsize - 3):
                    stop = True
                    break
                w = struct.unpack_from("<I", exe, o)[0]
                hit = _resolve(index, w)
                if hit is None and (w >> 20) not in index:
                    stop = True
                    break
                if hit is not None:
                    refs[hit].append((TABLE, "exe table 0x%08X" % va))
                    named.add(va)
            if stop:
                break
    for o in range(0, tsize - 3, 4):
        va = load + o
        if va in named:
            continue
        hit = _resolve(index, struct.unpack_from("<I", exe, toff + o)[0])
        if hit is not None:
            refs[hit].append((TABLE, "exe 0x%08X" % va))
    return dict(refs)
