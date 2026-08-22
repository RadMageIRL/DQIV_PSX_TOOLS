"""Who points at which string.

Three measured referrer systems, all carrying the same 32-bit word,
`(text id << 20) | bit offset from the block base`:

  LOOKUP  tail record tables inside type 40 and 42 text blocks   (Phase 10)
  TABLE   word 0 to 2 of each 60-byte type 26 record             (Phase 11, 12)
  ROSTER  word-aligned entries in type 44 sub-blocks             (Phase 12)
  SCRIPT  the 3-byte command C0 21 A0 in type 39 cutscene
          scripts, followed by the same packed word              (Phase 15)

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

LOOKUP, TABLE, ROSTER, SCRIPT = "LOOKUP", "TABLE", "ROSTER", "SCRIPT"

# The cutscene dialogue command. It is a THREE-byte opcode on a byte-aligned
# stream, not a word-aligned u32: the same bytes occur at all four alignments
# (15207 / 6737 / 4515 / 10735), so reading only the 4-aligned ones sees a
# quarter of the stream and calls the rest noise.
SCRIPT_CMD = bytes((0xC0, 0x21, 0xA0))

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
            # Deliberately NOT wrapped in a bare except. A swallowed exception
            # here silently drops sub-blocks from the measurement, which is
            # exactly how 922 of 976 type 39 blocks went unexamined for three
            # phases: decompress() takes one argument and was being called with
            # two, so every compressed sub-block raised TypeError into an
            # `except Exception: continue`.
            raw = lzs.decompress(raw)
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
    # SCRIPT: the 3-byte command followed by a packed reference, byte aligned
    for sector, sub, raw in _distinct(arch, blocks, 39):
        o = raw.find(SCRIPT_CMD)
        while o >= 0:
            p = o + len(SCRIPT_CMD)
            if p + 4 <= len(raw):
                hit = _resolve(index, struct.unpack_from("<I", raw, p)[0])
                if hit is not None:
                    refs[hit].append(
                        (SCRIPT, "type 39 sector %d sub %d +0x%X"
                         % (sector, sub["idx"], p)))
            o = raw.find(SCRIPT_CMD, o + 1)
    return dict(refs)


# ---------------------------------------------------------------- executable

def exe_blocks(exe, load, toff, tsize):
    """[(va, TextBlock)] for text blocks embedded in the executable.

    Located by the six-u32 header signature: a plausible a, e either zero or
    inside a, and c consistent with the dictionary pointer f6.

    CORRECTED, Phase 46. The test used to require c == 24, which is only true of
    a block with NO dictionary. A block that has one carries its dictionary in
    [24, c), so c is greater than 24 and f6 is 24. Requiring c == 24 made every
    such block invisible, and one is: 0x048F at 0x800B0D24, c = 648, f6 = 24.
    """
    out = []
    for o in range(0, tsize - 24, 4):
        a, bid, c, d, e, f6 = struct.unpack_from("<6I", exe, toff + o)
        if not (0x001 <= bid <= 0x600) or not (24 < a < 0x40000):
            continue
        if f6 == 0:
            if c != 24:
                continue
        elif f6 == 24:
            if not (24 < c < a):
                continue
        else:
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
