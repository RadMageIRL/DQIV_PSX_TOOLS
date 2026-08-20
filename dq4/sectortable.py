"""Level sector table access.

find_probe() locates the known probe pattern. entries() parses the table into
(offset, raw, length, lba, archive_sector) rows. resolve() counts how many entries
land on a valid block header with a matching sector count. unreferenced_blocks()
returns valid blocks the table never points at.

lba_to_sector() applies the archive LBA base. Callers translating by hand should
use it rather than subtracting a literal.

Format details are in FORMAT.md section 7.
"""

import struct

ARCHIVE_LBA_BASE = 362        # see FORMAT.md section 7
PROBE = b"\x3A\xA2\xD1\x04"   # town level, text id 0x0067, length 0x4D, LBA 0x1A23A
PROBE_OFFSET = 0x93B2C
TABLE_START = 0x935F4
TABLE_END = 0x9693C           # offset of the LAST entry, inclusive


def unpack(v):
    """(length_in_sectors, disc_lba)"""
    return v >> 20, v & 0xFFFFF


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


def entries(exe, start=TABLE_START, end=TABLE_END):
    """[(offset, raw_u32, length, lba, archive_sector)] over the table."""
    out = []
    for off in range(start, end + 4, 4):
        v = struct.unpack_from("<I", exe, off)[0]
        length, lba = unpack(v)
        out.append((off, v, length, lba, lba_to_sector(lba)))
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
    """Valid blocks the table never points at. Five in DQ4, three of which hold
    the type 1 glyph atlas."""
    covered = set()
    for _, _, _, lba, _ in entries(exe, start, end):
        covered.add(lba - base)
    return sorted(set(blocks) - covered)
