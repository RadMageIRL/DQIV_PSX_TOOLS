"""HBD1PS1D archive access.

scan_blocks() returns every valid block keyed by sector. parse_block() applies the
validity filter to one candidate and returns None if it does not hold. type_census()
and text_sub_blocks() summarize and select. sub_bytes() returns a sub-block's raw
bytes, still compressed if it is compressed.

Two contracts callers get wrong:

  * scan_blocks() scans every sector boundary. Do not try to walk block to block.
  * sub["compressed"] is derived from the flags word, not from a length comparison.

Format details are in FORMAT.md section 2.
"""

import struct
import collections

SECTOR = 2048
BLOCK_HEADER = 16
SUB_HEADER = 16

FLAG_LZS = 0x0500          # see FORMAT.md section 2
VIDEO_MAGIC = b"\x60\x01\x01\x80"   # LE form of the PSX STR magic 0x80010160

TEXT_TYPES = (40, 42)


def is_video_sector(buf, sector):
    return buf[sector * SECTOR:sector * SECTOR + 4] == VIDEO_MAGIC


def count_video_sectors(buf):
    """Sectors whose first four bytes are the STR video magic."""
    n = len(buf) // SECTOR
    return sum(1 for s in range(n) if buf[s * SECTOR:s * SECTOR + 4] == VIDEO_MAGIC)


def parse_block(buf, sector):
    """Parse a candidate block header at `sector`. Returns a dict or None.

    The validity filter is the whole point of this function. All five conditions
    must hold; see FORMAT.md section 2 for what they are and why.
    """
    off = sector * SECTOR
    if off + BLOCK_HEADER > len(buf):
        return None
    nsub, nsec, total_len, zero = struct.unpack_from("<4I", buf, off)
    if zero != 0 or nsub == 0 or nsec == 0:
        return None
    header = BLOCK_HEADER + nsub * SUB_HEADER
    if off + header > len(buf):
        return None
    subs = []
    data_off = off + header
    running = 0
    for i in range(nsub):
        so = off + BLOCK_HEADER + i * SUB_HEADER
        dlen, ulen, unknown = struct.unpack_from("<3I", buf, so)
        flags, stype = struct.unpack_from("<2H", buf, so + 12)
        subs.append({
            "idx": i,
            "dlen": dlen,
            "ulen": ulen,
            "unknown": unknown,
            "flags": flags,
            "type": stype,
            "off": data_off,
            "compressed": flags == FLAG_LZS,
        })
        data_off += dlen
        running += dlen
    if running != total_len:
        return None
    if (header + total_len + SECTOR - 1) // SECTOR != nsec:
        return None
    return {"sector": sector, "nsub": nsub, "nsec": nsec, "tlen": total_len, "subs": subs}


def scan_blocks(buf):
    """{sector: block} for every valid block in the archive."""
    out = {}
    n = len(buf) // SECTOR
    for s in range(n):
        o = s * SECTOR
        b = buf[o:o + 4]
        # cheap prefilter: first dword is XX 00 00 00 with XX nonzero
        if b[1] or b[2] or b[3] or not b[0]:
            continue
        blk = parse_block(buf, s)
        if blk is not None:
            out[s] = blk
    return out


def sub_blocks(blocks):
    """[(sector, sub)] flattened, in sector then index order."""
    return [(s, sb) for s in sorted(blocks) for sb in blocks[s]["subs"]]


def type_census(blocks):
    """{type: {'count', 'compressed', 'uncompressed'}} over all sub-blocks."""
    out = collections.defaultdict(lambda: {"count": 0, "compressed": 0, "uncompressed": 0})
    for _, sb in sub_blocks(blocks):
        e = out[sb["type"]]
        e["count"] += 1
        if sb["compressed"]:
            e["compressed"] += 1
        else:
            e["uncompressed"] += 1
    return dict(out)


def text_sub_blocks(blocks):
    """[(sector, sub)] for type 40 and 42 only."""
    return [(s, sb) for s, sb in sub_blocks(blocks) if sb["type"] in TEXT_TYPES]


def sub_bytes(buf, sub):
    """Raw (still compressed if it is) bytes of one sub-block."""
    return buf[sub["off"]:sub["off"] + sub["dlen"]]
