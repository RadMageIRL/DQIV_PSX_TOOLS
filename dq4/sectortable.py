"""Level sector table access.

find_probe() locates the known probe pattern. entries() parses the table into
(offset, raw, length, lba, archive_sector) rows. resolve() counts how many entries
land on a valid block header with a matching sector count. unreferenced_blocks()
returns valid blocks the table never points at.

lba_to_sector() applies the archive LBA base. Callers translating by hand should
use it rather than subtracting a literal.

THE LENGTH FIELD IS ELEVEN BITS AND BIT 31 IS A SEPARATE FLAG.

This module decoded the length as twelve bits until 2026-08-29. Reads were
unaffected, because on every entry that names a block the flag is clear and the
two decodes agree, so nothing measured under the old form is retracted. A WRITE
was not safe: an entry rebuilt as `length << 20 | lba` drops bit 31. Use pack()
or repack() rather than assembling a word by hand. repack() carries the flag
across unchanged, which is the whole reason it exists.

check_table() is the build-time invariant. Relocation is a write, and a partial
or flag-dropping relocation is invisible to booting: duplicate copies mask a
stale entry, and most byte-identical block groups hold no drawable text at all.
Run check_table() before writing any image whose sector table has been touched.

Format details are in FORMAT.md section 7.
"""

import collections
import struct

ARCHIVE_LBA_BASE = 362        # see FORMAT.md section 7
PROBE = b"\x3A\xA2\xD1\x04"   # town level, text id 0x0067, length 0x4D, LBA 0x1A23A
PROBE_OFFSET = 0x93B2C
TABLE_START = 0x935F4
TABLE_END = 0x9693C           # offset of the LAST entry, inclusive
ENTRY_COUNT = (TABLE_END - TABLE_START) // 4 + 1

# The field layout, read out of the reader entered at 0x800592CC:
#     800592EC  and  v0,v0,a2      a2 = 0x000FFFFF, the lba
#     80059300  srl  v0,v0,31      the flag, on its own
#     80059304  sll  v0,v0,2       into bit 2 of the per-level status word
#     80059338  srl  v0,a1,20      the length
#     8005933C  andi v0,v0,0x07FF  eleven bits of it
LEN_SHIFT = 20
LEN_MASK = 0x7FF              # 11 bits. Max expressible nsec is 2047.
LBA_MASK = 0xFFFFF            # 20 bits, absolute disc LBA
FLAG_BIT = 0x80000000         # bit 31. NOT part of the length.

# Sub-block types that carry a text id. Kept local so check_table() does not
# depend on hbd being importable; hbd.TEXT_TYPES is the same set.
TEXT_TYPES = (40, 42)

# The entries that carry the flag in the SHIPPED GAME. MEASURED 2026-08-29 on
# the pristine Japanese disc 100d87db... and on two built discs, all three
# identical: 2 of 3,283, the last two words of the table, raw 0x80102448 and
# 0x80219158. Both read as KSEG0 addresses and neither target holds a block
# header, which is why the flag is set on these two and on nothing else.
#
# This constant exists so check_table() has force when it is handed one
# executable as both base and build. Comparing a disc against itself can never
# notice a flag that was dropped from both sides; comparing it against the
# shipped game's own figure can.
FLAGGED_INDEXES = (3281, 3282)


class Entry(tuple):
    """(offset, raw, length, lba, archive_sector), with .flag alongside.

    A tuple subclass so the five-way unpacking every existing caller does keeps
    working. The flag is reached by name because it has no place in a row that
    older code destructures positionally.
    """

    __slots__ = ()

    def __new__(cls, offset, raw, length, lba, archive_sector):
        return tuple.__new__(cls, (offset, raw, length, lba, archive_sector))

    offset = property(lambda self: self[0])
    raw = property(lambda self: self[1])
    length = property(lambda self: self[2])
    lba = property(lambda self: self[3])
    archive_sector = property(lambda self: self[4])
    flag = property(lambda self: (self[1] >> 31) & 1)


def unpack(v):
    """(length_in_sectors, disc_lba). The flag is NOT folded into the length."""
    return (v >> LEN_SHIFT) & LEN_MASK, v & LBA_MASK


def flag(v):
    """Bit 31, as 0 or 1. Preserve it across any rewrite."""
    return (v >> 31) & 1


def pack(length, lba, flag_bit=0):
    """Build a table word. Raises rather than truncating a field silently."""
    if not 0 <= length <= LEN_MASK:
        raise ValueError("length %d does not fit in 11 bits" % (length,))
    if not 0 <= lba <= LBA_MASK:
        raise ValueError("lba %d does not fit in 20 bits" % (lba,))
    if flag_bit not in (0, 1):
        raise ValueError("flag must be 0 or 1, not %r" % (flag_bit,))
    return (flag_bit << 31) | (length << LEN_SHIFT) | lba


def repack(v, length=None, lba=None):
    """Rewrite one field of an existing word and CARRY THE FLAG ACROSS.

    This is the call a relocation wants. repack(v) with nothing changed is the
    identity on every word, flagged or not.
    """
    cur_len, cur_lba = unpack(v)
    return pack(cur_len if length is None else length,
                cur_lba if lba is None else lba,
                flag(v))


def lba_to_sector(lba, base=ARCHIVE_LBA_BASE):
    return lba - base


def find_probe(exe):
    """All offsets of the known probe pattern. Expect exactly one."""
    out = []
    i = exe.find(PROBE)
    while i >= 0:
        out.append(i)
        i = exe.find(PROBE, i + 1)
    return out


def entries(exe, start=TABLE_START, end=TABLE_END, base=ARCHIVE_LBA_BASE):
    """[Entry] over the table. Each row unpacks five ways as it always did.

    `base` is threaded through to archive_sector rather than defaulted inside,
    because a caller that passes a base and then reads .archive_sector would
    otherwise get a sector computed from a different base than the one it asked
    for. On DQ4 there is only ever one base, so this could not be found by
    running against the shipped disc; a fabricated table found it.
    """
    out = []
    for off in range(start, end + 4, 4):
        v = struct.unpack_from("<I", exe, off)[0]
        length, lba = unpack(v)
        out.append(Entry(off, v, length, lba, lba_to_sector(lba, base)))
    return out


def resolve(exe, blocks, start=TABLE_START, end=TABLE_END, base=ARCHIVE_LBA_BASE):
    """(hits, total) where a hit is an entry landing on a valid block whose
    stored sector count equals the entry's length field."""
    rows = entries(exe, start, end)
    hits = 0
    for _, _, length, lba, _ in rows:
        sec = lba - base
        blk = blocks.get(sec)
        if blk is not None and blk["nsec"] == length:
            hits += 1
    return hits, len(rows)


def unreferenced_blocks(exe, blocks, start=TABLE_START, end=TABLE_END,
                        base=ARCHIVE_LBA_BASE):
    """Valid blocks the table never points at. Two in DQ4."""
    covered = set()
    for _, _, _, lba, _ in entries(exe, start, end):
        covered.add(lba - base)
    return sorted(set(blocks) - covered)


def live_entries(exe, blocks, start=TABLE_START, end=TABLE_END,
                 base=ARCHIVE_LBA_BASE):
    """[Entry] with the flag CLEAR that land on a valid block header.

    The flagged words are excluded because they are not level pointers. On DQ4
    the two that carry the flag are the last two words of the table and read as
    KSEG0 addresses, not as sectors. An entry whose target holds no block is
    excluded too; forty of them point into the STR video band.
    """
    out = []
    for e in entries(exe, start, end, base):
        if e.flag:
            continue
        if (e.lba - base) in blocks:
            out.append(e)
    return out


# --------------------------------------------------------------------------
# The build-time invariant
# --------------------------------------------------------------------------

Check = collections.namedtuple("Check", "name ok measured expected detail")


class Report(object):
    """The result of check_table(). Falsy when any check failed."""

    def __init__(self, checks):
        self.checks = checks

    ok = property(lambda self: all(c.ok for c in self.checks))
    failures = property(lambda self: [c for c in self.checks if not c.ok])

    def __bool__(self):
        return self.ok

    __nonzero__ = __bool__      # Python 2 callers

    def lines(self):
        out = []
        for c in self.checks:
            out.append("  [%s] %-22s measured %s, expected %s"
                       % ("PASS" if c.ok else "FAIL", c.name,
                          c.measured, c.expected))
            for d in c.detail[:8]:
                out.append("         %s" % d)
            if len(c.detail) > 8:
                out.append("         ... and %d more" % (len(c.detail) - 8))
        out.append("  RESULT: %s" % ("PASS" if self.ok else "REFUSED"))
        return out

    def __str__(self):
        return "\n".join(self.lines())


def check_table(base_exe, built_exe, built_blocks,
                start=TABLE_START, end=TABLE_END, base=ARCHIVE_LBA_BASE,
                text_types=TEXT_TYPES, expect_flagged=None,
                base_blocks=None):
    """Five checks over the WHOLE table. Returns a Report.

    `built_blocks` is hbd.scan_blocks() over the archive that will ship beside
    `built_exe`. `base_exe` is the executable the build started from.

        1  ROUND TRIP     every word re-encodes to itself through unpack/pack
        2  FLAG           bit 31 is set on exactly the indexes that carried it
        3  OVERLAP        no two live entries' sector extents intersect
        4  TEXT REACH     every text sub-block sits in a block a live entry
                          names, that entry's length equals the block's own
                          stored sector count, and the sub-block lies inside
                          the extent the entry declares
        5  COUNT          the entry count, the two boundary words and the set
                          of live entries are all unchanged

    Check 4 folds in the stored-sector-count agreement on purpose: nsec is
    stored twice, in the entry and in the block header at +4, and an extent
    check means nothing while the two disagree about how long the block is.

    `expect_flagged` is the indexes check 2 requires the flag on. It defaults to
    whatever `base_exe` carries. PASS FLAGGED_INDEXES WHEN base_exe AND
    built_exe ARE THE SAME BUFFER: a disc compared against itself can never
    notice a flag that is missing from both sides.

    `base_blocks` is hbd.scan_blocks() over the archive the build STARTED from.
    PASS IT IN A BUILD. Without it check 5 resolves the base entries against
    the built archive, and a relocation whose entry was never rewritten then
    looks non-live on both sides and slips through. With it, the entry named a
    block before and names a zeroed sector now, and the check refuses. It
    defaults to `built_blocks` for the one-image case verify.py is stuck with.
    """
    checks = []
    n = (end - start) // 4 + 1

    def words(buf):
        return [struct.unpack_from("<I", buf, start + 4 * i)[0]
                for i in range(n)]

    # ------------------------------------------------------------------ 1
    #
    # Two halves, and the second one is why this check has teeth. Re-encoding
    # a 32-bit word through a correct decoder is the identity for every input,
    # so the data half alone would pass on any table forever. The field-tiling
    # half fails the moment the DECODER regresses: a twelve-bit LEN_MASK makes
    # the length field overlap bit 31, which is exactly the defect this module
    # carried, and it is caught here before a single word is written.
    bad = []
    span = LEN_MASK << LEN_SHIFT
    if span & LBA_MASK or span & FLAG_BIT or LBA_MASK & FLAG_BIT:
        bad.append("field masks overlap: length 0x%08X, lba 0x%08X, flag 0x%08X"
                   % (span, LBA_MASK, FLAG_BIT))
    if (span | LBA_MASK | FLAG_BIT) != 0xFFFFFFFF:
        bad.append("field masks do not tile 32 bits: 0x%08X"
                   % (span | LBA_MASK | FLAG_BIT))
    if bad:
        # A broken decoder cannot be used to count words, so it is not used to.
        measured = "field layout is not 11 + 20 + 1, no words counted"
    else:
        for i, v in enumerate(words(built_exe)):
            length, lba = unpack(v)
            rt = pack(length, lba, flag(v))
            if rt != v:
                bad.append("index %d offset 0x%X raw 0x%08X re-encoded 0x%08X"
                           % (i, start + 4 * i, v, rt))
        measured = ("%d of %d words re-encode to themselves"
                    % (n - len(bad), n))
    checks.append(Check("1 round trip", not bad, measured,
                        "field layout 11 + 20 + 1 and %d of %d words" % (n, n),
                        bad))

    # ------------------------------------------------------------------ 2
    base_flagged = (list(expect_flagged) if expect_flagged is not None
                    else [i for i, v in enumerate(words(base_exe))
                          if v & FLAG_BIT])
    built_flagged = [i for i, v in enumerate(words(built_exe)) if v & FLAG_BIT]
    detail2 = ["flag DROPPED at index %d, offset 0x%X" % (i, start + 4 * i)
               for i in sorted(set(base_flagged) - set(built_flagged))]
    detail2 += ["flag INVENTED at index %d, offset 0x%X" % (i, start + 4 * i)
                for i in sorted(set(built_flagged) - set(base_flagged))]
    checks.append(Check("2 flag preservation", not detail2,
                        "%d flagged at %s" % (len(built_flagged), built_flagged),
                        "%d flagged at %s" % (len(base_flagged), base_flagged),
                        detail2))

    # ------------------------------------------------------------------ 3
    live = live_entries(built_exe, built_blocks, start, end, base)
    spans = sorted((e.archive_sector, e.length, e.offset) for e in live)
    clash = []
    for k in range(len(spans) - 1):
        s0, n0, o0 = spans[k]
        s1, n1, o1 = spans[k + 1]
        if s0 == s1:
            if n0 != n1:
                clash.append("offsets 0x%X and 0x%X both start at sector %d but"
                             " claim %d and %d sectors" % (o0, o1, s0, n0, n1))
            continue
        if s0 + n0 > s1:
            clash.append("sector %d plus %d sectors runs into sector %d"
                         " (offsets 0x%X and 0x%X)" % (s0, n0, s1, o0, o1))
    checks.append(Check("3 no overlap", not clash,
                        "%d live entries, %d extent clashes"
                        % (len(live), len(clash)),
                        "0 clashes", clash))

    # ------------------------------------------------------------------ 4
    reach = {}
    for e in live:
        reach.setdefault(e.archive_sector, []).append(e)
    stray = []
    ntext = 0
    for sec in sorted(built_blocks):
        blk = built_blocks[sec]
        for sb in blk["subs"]:
            if sb["type"] not in text_types:
                continue
            ntext += 1
            named = reach.get(sec)
            if not named:
                stray.append("text sub-block %d/%d, type %d: no live entry"
                             " names sector %d"
                             % (sec, sb["idx"], sb["type"], sec))
                continue
            for e in named:
                if e.length != blk["nsec"]:
                    stray.append("entry 0x%X says %d sectors, block %d header"
                                 " says %d"
                                 % (e.offset, e.length, sec, blk["nsec"]))
                elif sb["off"] < sec * 2048 or \
                        sb["off"] + sb["dlen"] > (sec + e.length) * 2048:
                    stray.append("text sub-block %d/%d spans [%d,%d) outside"
                                 " entry 0x%X extent [%d,%d)"
                                 % (sec, sb["idx"], sb["off"],
                                    sb["off"] + sb["dlen"], e.offset,
                                    sec * 2048, (sec + e.length) * 2048))
    checks.append(Check("4 text reach", not stray,
                        "%d text sub-blocks, %d outside their entry"
                        % (ntext, len(stray)),
                        "0 outside", stray))

    # ------------------------------------------------------------------ 5
    base_live = set(e.offset for e in live_entries(
        base_exe, built_blocks if base_blocks is None else base_blocks,
        start, end, base))
    now_live = set(e.offset for e in live)
    detail5 = []
    if len(built_exe) != len(base_exe):
        detail5.append("executable length %d, base had %d"
                       % (len(built_exe), len(base_exe)))
    for label, off in (("before", start - 4), ("after", end + 4)):
        b = struct.unpack_from("<I", base_exe, off)[0]
        t = struct.unpack_from("<I", built_exe, off)[0]
        if b != t:
            detail5.append("boundary word %s the table changed 0x%08X to 0x%08X"
                           % (label, b, t))
    for off in sorted(base_live - now_live):
        detail5.append("entry 0x%X named a block on the base and names none now"
                       % off)
    checks.append(Check("5 entry count", not detail5,
                        "%d entries, %d live" % (n, len(now_live)),
                        "%d entries, %d live" % (n, len(base_live)), detail5))

    return Report(checks)
