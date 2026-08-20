"""Phrase dictionary parse and expansion.

parse(raw, tb) returns the block's phrase table as a list of symbol sequences, or
an empty list when the block has no dictionary. expand(symbols, entries) replaces
DICT symbols with their phrases and returns (symbols, unresolved_count).

mean_expansion() is a health check on a parsed table, not a format fact.

The table belongs to one block. Never reuse a table across blocks.

Format details are in FORMAT.md section 5.
"""

import struct

CTRL, SJIS = "CTRL", "SJIS"


def parse(raw, tb):
    """[phrase] where phrase is [(kind, value)]. Empty list when f6 == 0."""
    start = tb.f6
    if start == 0:
        return []
    first = struct.unpack_from("<H", raw, start)[0] & 0x0FFF
    count = (first - start) // 2
    if count <= 0:
        return []
    entries = []
    for i in range(count):
        w = struct.unpack_from("<H", raw, start + 2 * i)[0]
        length = (w >> 12) & 0xF          # in 16-bit units
        offset = w & 0x0FFF               # byte offset from sub-block start
        seq = []
        j = offset
        end = offset + length * 2
        while j + 1 < end + 1 and j + 1 < len(raw) and j < end:
            if raw[j] == 0xFF:
                seq.append((CTRL, 0x7F00 | raw[j + 1]))
            else:
                seq.append((SJIS, (raw[j] << 8) | raw[j + 1]))
            j += 2
        entries.append(seq)
    return entries


def expand(symbols, entries):
    """Replace DICT symbols with their phrases. Returns (symbols, unresolved).

    Corpus-wide this resolves with 0 unresolved references.
    """
    out = []
    unresolved = 0
    for kind, val in symbols:
        if kind == "DICT":
            idx = (val & 0xFF) - 1
            if 0 <= idx < len(entries):
                out.extend(entries[idx])
            else:
                out.append(("BAD", val))
                unresolved += 1
        else:
            out.append((kind, val))
    return out, unresolved


def mean_expansion(entries):
    """Mean phrase length in symbols, as a health check on a parsed table.

    A value at or below 1 across the board means the table was misread.
    """
    if not entries:
        return 0.0
    return sum(len(e) for e in entries) / len(entries)
