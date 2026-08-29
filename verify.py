#!/usr/bin/env python3
"""Run every proven gate against a real disc image and report measured values.

Usage:
    python verify.py --dq4 "path/to/Dragon Quest IV (Japan).bin"

No paths are hardcoded. The user supplies their own disc image; no ROM data
ships with this tool.

Each gate prints its measured value next to the expected one. Gates 9 and 10 are
companion metrics: gate 8, a byte-exact round trip, passed on a collapsed decoder
during Phase 1 and only the bits-per-symbol figure exposed it. Any gate that can
pass degenerately carries a companion.
"""

import argparse
import collections
import hashlib
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# THIS SUITE MUST NOT DIE OF ITS OWN OUTPUT, and it has.
#
# Gate 7 prints a Japanese string as its expected value. When stdout is a pipe or
# a file rather than a console, Python picks the locale encoding, which on a
# Windows box is cp1252, and the print raises UnicodeEncodeError. The suite died
# there after six gates with a return code of 1.
#
# That alone is an annoyance. What made it expensive is that a driver capturing
# the output parsed the rows already printed and reported "5 gates, 5 pass, 0
# FAIL": A TRUNCATED SUITE WEARING THE SHAPE OF A CLEAN ONE. The full suite is 38
# gates. The companion disc, which exists to fail and so prove the suite can
# fail, also reported zero failures, because it too had crashed long before
# reaching the gate that would have caught it.
#
# Fixed here rather than in the caller. A tool whose correctness depends on the
# caller setting PYTHONIOENCODING has moved its own defect one level up.
# `backslashreplace` is deliberate: it can mangle a character but it can never
# raise, and a suite that cannot be killed by a print is worth a little mojibake
# on a console that could not have rendered the character anyway.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from dq4 import iso as isomod
from dq4 import hbd, textblock, huffman, dictionary, sectortable, glyph, codes, lzs, fonts
from dq4 import corpus as corpusmod
from dq4 import mips, referrers, overlay, splitimm

Q41_SIZE = 319436800
# Phase 0 SHA-256 is of the DISC IMAGE file, not of the extracted archive.
DISC_SHA256 = "100d87db9deadf8f9fa4bb891d3a5d0bb112acbf5adbcbc93c637848ed9c7531"

PHASE0_CENSUS = {
    0x01: 6, 0x06: 1730, 0x07: 1458, 0x08: 309, 0x09: 473, 0x0A: 256, 0x0B: 309,
    0x0C: 309, 0x0D: 970, 0x0E: 44, 0x0F: 2, 0x11: 5, 0x12: 5, 0x13: 141,
    0x14: 3, 0x15: 3317, 0x16: 72, 0x17: 44, 0x18: 1062, 0x19: 27, 0x1A: 573,
    0x1F: 1025, 0x20: 32, 0x22: 975, 0x23: 1576, 0x24: 1506, 0x25: 1033,
    0x26: 1377, 0x27: 976, 0x28: 1315, 0x29: 1730, 0x2A: 213, 0x2B: 24,
    0x2C: 152, 0x2D: 140, 0x2E: 612, 0x2F: 27,
}

STRING_10 = "どうした？　<7F1F>。<7F02>もう　降参かい？"


def _carriers_of(arch, exe, tid):
    """([(where, bytes)], unexaminable) for text block `tid`, in BOTH media.

    Written for gate 44. The point is coverage, not speed: it walks every
    sub-block of every type rather than the four types a census happened to
    enumerate, because the defect this gate exists to catch is precisely a
    carrier nobody thought to look in.

    THE SECOND RETURN VALUE IS THE WHOLE REASON THIS SIGNATURE IS NOT JUST A
    LIST. A sub-block that will not decompress, or that the overlay scanner
    cannot read, is not evidence that the id is absent from it. It is a carrier
    THIS FUNCTION DID NOT LOOK IN, which is the exact thing gate 44 exists to
    make impossible, so it is counted and handed back rather than skipped.

    A coverage gate that silently drops the carriers it could not read reports
    N/N over a denominator it quietly shrank, and N/N is the answer it gives
    when everything is fine. `referrers.py` carries the same warning from the
    other end: a swallowed exception is how 922 of 976 type 39 blocks went
    unexamined for three phases.

    MEASURED on the pristine disc, 2026-08-28: 23,828 sub-blocks, 5,821 of them
    LZS, and `unexaminable` is ZERO. So this is a latent defect being closed,
    not an active undercount being corrected, and the figure the gate prints
    today does not move. A BUILT disc is where it would bite, and a built disc
    is the only thing gate 44 is ever pointed at.

    The handlers stay broad rather than being narrowed to particular exception
    types, because no failure has been observed here and narrowing to a guessed
    list would convert an unexpected error into a crash rather than into a
    count. Broad and COUNTED is the safe combination; broad and SILENT is not.
    """
    out = []
    unexaminable = 0
    if exe:
        load, _pc, tsize, toff = mips.exe_mapping(exe)
        for _va, tb in referrers.exe_blocks(exe, load, toff, tsize):
            if tb.id == tid:
                out.append(("exe:%04X" % tb.id, tb.raw[:tb.a]))
    blocks = hbd.scan_blocks(arch)
    for sec, sb in hbd.sub_blocks(blocks):
        raw = hbd.sub_bytes(arch, sb)
        if sb["flags"] == hbd.FLAG_LZS:
            try:
                raw = lzs.decompress(raw)
            except Exception:
                unexaminable += 1
                continue
        try:
            found = overlay.scan_image(raw)
        except Exception:
            unexaminable += 1
            continue
        for off, tb in found:
            if tb.id == tid:
                out.append(("%d/%d t%d+%06X" % (sec, sb["idx"], sb["type"], off),
                            raw[off:off + tb.a]))
    return out, unexaminable


class Report:
    def __init__(self):
        self.rows = []

    def gate(self, n, name, ok, measured, expected):
        self.rows.append((n, name, bool(ok), measured, expected))
        print("  %-4s gate %-3s %-46s measured %-28s expected %s"
              % ("PASS" if ok else "FAIL", n, name, measured, expected))

    def note(self, n, name, measured):
        """Informational, never counted toward the pass total.

        Used where the honest answer is a fact rather than a verdict: gate 1
        asks whether this is the pinned source disc, and for a build the answer
        is legitimately no.
        """
        print("  NOTE gate %-2s  %-46s measured %s" % (n, name, measured))

    def summary(self):
        bad = [r for r in self.rows if not r[2]]
        print("\n%d / %d gates pass" % (len(self.rows) - len(bad), len(self.rows)))
        if bad:
            print("FAILED:")
            for n, name, _, m, e in bad:
                print("   gate %s %s: measured %s, expected %s" % (n, name, m, e))
        return not bad


def main():
    ap = argparse.ArgumentParser(description="verify the dq4 library against a disc image")
    ap.add_argument("--dq4", required=True, help="path to the DQ4 (Japan) .bin disc image")
    ap.add_argument("--corpus-out", default=None,
                    help="directory for gate 22 to regenerate the corpus into; "
                         "gate 22 is skipped when omitted")
    ap.add_argument("--edited-ids", default=None,
                    help="comma-separated text block ids this image edited, e.g. "
                         "047C,048F. Enables gate 44, CARRIER COVERAGE, which "
                         "checks EVERY carrier of each id in BOTH media and "
                         "reports N/N. Without it gate 44 renders a NOTE, "
                         "because a build that does not declare what it edited "
                         "cannot be checked for having missed a copy.")
    args = ap.parse_args()

    rep = Report()
    print("verifying against: %s\n" % args.dq4)

    with isomod.RawISO(args.dq4) as disc:
        found = disc.find("HBD1PS1D.Q41")
        if not found:
            print("HBD1PS1D.Q41 not found in that image")
            return 2
        lba, size = found
        print("HBD1PS1D.Q41 at LBA %d, %d bytes" % (lba, size))
        arch = disc.extract(lba, size)
        exe_found = disc.find("SLPM_869.16")
        exe = disc.extract(*exe_found) if exe_found else b""

    # 1
    h = hashlib.sha256()
    with open(args.dq4, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sha = h.hexdigest()
    # Gate 1 asks "is this the pinned source disc". For a build the answer is
    # legitimately no, and a gate that fails by construction on every modified
    # disc stops being read. So gate 1 only renders a verdict on the source; on
    # any other image it becomes a NOTE and gate 1b carries the structural work.
    is_source = (sha == DISC_SHA256)
    if is_source:
        rep.gate(1, "source integrity: pinned disc SHA-256", True,
                 sha[:16] + "...", DISC_SHA256[:16] + "...")
    else:
        rep.note(1, "source integrity: NOT the pinned source disc",
                 "%s... (source is %s...)" % (sha[:16], DISC_SHA256[:16]))

    # 1b  output integrity, which every image must satisfy including builds:
    # ISO9660 parses, the three files are present, the archive extracts to the
    # size the directory entry records.
    with isomod.RawISO(args.dq4) as _d:
        _files = {n.split(";")[0].lstrip("/"): (l, sz) for n, l, sz, _t in _d.files()}
    ok1b = (sorted(_files) == ["HBD1PS1D.Q41", "SLPM_869.16", "SYSTEM.CNF"]
            and _files["HBD1PS1D.Q41"] == (362, Q41_SIZE)
            and len(arch) == Q41_SIZE
            and os.path.getsize(args.dq4) % 2352 == 0)
    rep.gate("1b", "output integrity: ISO parses, archive extracts", ok1b,
             "%d files, archive %d bytes at lba %d"
             % (len(_files), len(arch), _files.get("HBD1PS1D.Q41", (0, 0))[0]),
             "3 files, archive %d bytes at lba 362" % Q41_SIZE)

    # 2
    blocks = hbd.scan_blocks(arch)
    rep.gate(2, "valid block count", len(blocks) == 3243, len(blocks), 3243)

    # 3
    vids = hbd.count_video_sectors(arch)
    rep.gate(3, "60 01 01 80 sector count", vids == 26635, vids, 26635)

    # 4
    census = hbd.type_census(blocks)
    total_subs = sum(v["count"] for v in census.values())
    counts_match = {t: v["count"] for t, v in census.items()} == PHASE0_CENSUS
    rep.gate(4, "sub-block total and per-type census",
             total_subs == 23828 and counts_match,
             "%d subs, census %s" % (total_subs, "matches" if counts_match else "DIFFERS"),
             "23828 subs, census matches")

    # 5
    texts = hbd.text_sub_blocks(blocks)
    n40 = sum(1 for _, sb in texts if sb["type"] == 40)
    n42 = sum(1 for _, sb in texts if sb["type"] == 42)
    rep.gate(5, "text sub-block count",
             len(texts) == 1528 and n40 == 1315 and n42 == 213,
             "%d (%d type 40, %d type 42)" % (len(texts), n40, n42),
             "1528 (1315, 213)")

    # parse every text block once
    parsed = []
    for s, sb in texts:
        raw = hbd.sub_bytes(arch, sb)
        parsed.append((s, sb, textblock.TextBlock(raw), raw))

    # 6
    inv = sum(1 for _, _, tb, _ in parsed if tb.invariants_hold())
    rep.gate(6, "header invariants", inv == 1528, "%d / 1528" % inv, "1528 / 1528")

    # decode everything once; collect for gates 7 through 16
    total_bits = 0
    total_syms = 0
    min_depth = 99
    rt_ok = 0
    unresolved = 0
    ctrl_counts = collections.Counter()
    ids_with_real = set()
    all_ids = set()
    block_006c = None
    block_0021 = None

    for s, sb, tb, raw in parsed:
        tree = huffman.HuffmanTree(tb)
        leaves, _, _ = tree.walk()
        min_depth = min(min_depth, tree.min_leaf_depth(leaves))
        syms = tree.decode()
        total_syms += len(syms)
        total_bits += (tb.e - tb.c) * 8
        if tree.round_trip_ok():
            rt_ok += 1
        entries = dictionary.parse(raw, tb)
        expanded, bad = dictionary.expand(syms, entries)
        unresolved += bad
        for kind, val in expanded:
            if kind == "CTRL":
                ctrl_counts[val] += 1
        text = huffman.render(expanded)
        all_ids.add(tb.id)
        stripped = text.replace("<END>", "").replace("<7F0B>", "").strip()
        if stripped != "ダミー":
            ids_with_real.add(tb.id)
        if tb.id == 0x006C and block_006c is None:
            block_006c = (tree, syms, entries)
        if tb.id == 0x0021 and block_0021 is None:
            block_0021 = entries

    # 7
    tree, syms, entries = block_006c
    expanded, _ = dictionary.expand(syms, entries)
    strings, residue = huffman.split_strings(expanded)
    # Phase 1 counted 12 pieces: 11 terminated by END plus the trailing residue,
    # which decodes from bits that complete no further code.
    pieces = len(strings) + (1 if residue else 0)
    s10 = huffman.render(strings[10]) if len(strings) > 10 else "(missing)"
    # Pinned to the unmodified decode, so any build that edits 0x006C fails it by
    # construction. Same treatment as gate 1: a verdict on the source, a NOTE
    # elsewhere, so a THIRD unexpected failure stays visible instead of hiding
    # among expected ones.
    if is_source:
        rep.gate(7, "text id 0x006C decode",
                 pieces == 12 and s10 == STRING_10,
                 "%d pieces (%d END-terminated + residue), [10] = %s"
                 % (pieces, len(strings), s10),
                 "12 pieces, [10] = %s" % STRING_10)
    else:
        rep.note(7, "text id 0x006C decode: not the source disc",
                 "%d pieces, [10] = %s" % (pieces, s10))

    # 8
    rep.gate(8, "byte-exact round trip", rt_ok == 1528, "%d / 1528" % rt_ok, "1528 / 1528")

    # 9  COMPANION to gate 8
    bps = total_bits / total_syms if total_syms else 0
    rep.gate(9, "corpus bits per symbol  (COMPANION)",
             abs(bps - 7.81) < 0.01, "%.3f" % bps, "7.81")

    # 10 COMPANION to gate 8
    rep.gate(10, "minimum leaf depth  (COMPANION)",
             min_depth >= 2, min_depth, ">= 2")

    # 11
    rep.gate(11, "unresolved 0x7Exx references", unresolved == 0, unresolved, 0)

    # 12
    me = dictionary.mean_expansion(block_0021) if block_0021 else 0.0
    rep.gate(12, "dictionary mean expansion, block 0x0021",
             abs(me - 2.33) < 0.01, "%.3f symbols" % me, "2.33 symbols")

    # 13
    probes = sectortable.find_probe(exe)
    ents = sectortable.entries(exe)
    rep.gate(13, "sector table extent and probe",
             len(probes) == 1 and probes[0] == sectortable.PROBE_OFFSET and len(ents) == 3283,
             "probe x%d at %s, %d entries"
             % (len(probes), ", ".join(hex(p) for p in probes) or "none", len(ents)),
             "probe x1 at 0x93b2c, 3283 entries")

    # 14
    hits, tot = sectortable.resolve(exe, blocks)
    rep.gate(14, "lba minus 362 resolves to block headers",
             hits == 3241 and tot == 3283, "%d / %d" % (hits, tot), "3241 / 3283")

    # 15
    rep.gate(15, "distinct non-dummy text ids",
             len(ids_with_real) == 925, len(ids_with_real), 925)

    # 16
    missing, extra = codes.diff_against_mandy(ctrl_counts)
    rep.gate(16, "control codes and Mandy subset",
             len(ctrl_counts) == 43 and not missing,
             "%d distinct, %d of hers missing" % (len(ctrl_counts), len(missing)),
             "43 distinct, 0 missing")

    # 17  The atlas holds TWO glyphs per cell, one per 2-bit plane. This gate used
    # to assert "13 Latin capitals" against a hand-made dict, which was reading the
    # superposition of both planes and was wrong. It now resolves every letter and
    # digit through the game's own font table and checks the named plane has ink.
    atlases = glyph.find_atlases(arch, blocks)
    big = [b for _, _, b in atlases if len(b) == 16128]
    wanted = list(range(0x8260, 0x827A)) + list(range(0x8281, 0x829B)) \
        + list(range(0x824F, 0x8259))
    if big and exe:
        at = glyph.Atlas(big[0])
        nb = at.non_blank_count()
        _load, _pc, _tsz, _toff = mips.exe_mapping(exe)
        _img = exe[_toff:_toff + _tsz]
        tbl = fonts.table(_img, _load, fonts.FONT1)
        drawn = 0
        for code in wanted:
            e = tbl.get(code)
            if e is None:
                continue
            c, p = fonts.cell_plane(e.descriptor)
            if at.plane_ink(c, p):
                drawn += 1
        # The non-blank COUNT is a property of the pristine atlas, so it is
        # pinned only on the source disc. A built disc may legitimately draw new
        # glyphs into blank half-cells. The structural half of the gate, 288
        # slots and 62 of 62 letters and digits resolving through the game's own
        # table to a half-cell with ink, is asserted on every disc and is the
        # part that catches a broken table or a mispacked atlas.
        ok17 = at.slots == 288 and drawn == 62 and nb >= 268
        if is_source:
            ok17 = ok17 and nb == 268
        rep.gate(17, "glyph atlas, two glyphs per cell, Latin and digits", ok17,
                 "%d slots, %d non-blank, %d of 62 letters and digits drawn"
                 % (at.slots, nb, drawn),
                 "288 slots, 62 of 62 drawn"
                 + (", 268 non-blank" if is_source
                    else ", non-blank not pinned off-source (was 268)"))
    else:
        rep.gate(17, "glyph atlas, two glyphs per cell, Latin and digits", False,
                 "atlas or executable not found",
                 "288 slots, 268 non-blank, 62 of 62 drawn")

    # 39  Sub-block alignment. Every sub-block in the shipped archive has a length
    # that is a multiple of 4 and starts 4-byte aligned, 23,828 of 23,828. The
    # engine reads the text block header with lw, so a misaligned block raises an
    # Address Error. Four builds hung on exactly this while passing every other
    # gate here, because every other gate was written from our own model of the
    # format. This one is written from a property the shipped game exhibits.
    # It is an invariant, not a pinned value, so it renders a verdict on any disc.
    a_tot = 0
    a_bad = []
    for _sec in sorted(blocks):
        _b = blocks[_sec]
        _off = 16 + 16 * _b["nsub"]
        for _s in _b["subs"]:
            a_tot += 1
            if _s["dlen"] % 4 or _off % 4:
                a_bad.append((_sec, _s["idx"]))
            _off += _s["dlen"]
    rep.gate(39, "sub-block 4-byte alignment, whole archive",
             a_tot == 23828 and not a_bad,
             "%d sub-blocks, %d misaligned%s"
             % (a_tot, len(a_bad),
                "" if not a_bad else " (first sector %d sub %d)" % a_bad[0]),
             "23828 sub-blocks, 0 misaligned")

    # 18, 19, 20  LZS
    flagged = [(s, sb) for s, sb in hbd.sub_blocks(blocks) if sb["flags"] == hbd.FLAG_LZS]
    mismatch_flagged = [(s, sb) for s, sb in flagged if sb["dlen"] != sb["ulen"]]
    mismatch_unflagged = [(s, sb) for s, sb in hbd.sub_blocks(blocks)
                          if sb["flags"] != hbd.FLAG_LZS and sb["dlen"] != sb["ulen"]]

    deltas = collections.Counter()
    lzs_pass = 0
    flag_ok = {}
    for s, sb in flagged:
        d = lzs.overrun(hbd.sub_bytes(arch, sb), sb["ulen"])
        deltas[d] += 1
        ok = 0 <= d <= 17
        flag_ok[(s, sb["idx"])] = ok
        if ok:
            lzs_pass += 1
    rep.gate(18, "LZS decompress on flags == 0x0500",
             lzs_pass == 5821 and len(flagged) == 5821,
             "%d / %d" % (lzs_pass, len(flagged)), "5821 / 5821")

    with_flag = sum(1 for s, sb in mismatch_flagged if flag_ok[(s, sb["idx"])])
    without_flag_fail = sum(1 for s, sb in mismatch_unflagged
                            if not (0 <= lzs.overrun(hbd.sub_bytes(arch, sb), sb["ulen"]) <= 17))
    rep.gate(19, "compression predicate separation",
             with_flag == 5820 and without_flag_fail == 147
             and len(mismatch_unflagged) == 147,
             "%d pass with flag, %d fail without, overlap %d"
             % (with_flag, without_flag_fail, len(mismatch_unflagged) - without_flag_fail),
             "5820 pass, 147 fail, overlap 0")

    # 20 COMPANION to gate 18: a decompressor that padded or guessed would not
    # produce a two-valued delta distribution.
    two_valued = sorted(deltas.items()) == [(0, 3089), (3, 2732)]
    rep.gate(20, "LZS overrun distribution  (COMPANION)", two_valued,
             sorted(deltas.items()), "[(0, 3089), (3, 2732)]")

    # 21
    vrows = hbd.video_sectors(arch)
    sane, dims, frames, streams = hbd.video_summary(vrows)
    rep.gate(21, "STR video band parses",
             sane == 26635 and len(vrows) == 26635 and dims.get((128, 120)) == 26635
             and frames == 5327 and streams == 40,
             "%d / %d sane, %s, %d frames, %d streams"
             % (sane, len(vrows), sorted(dims), frames, streams),
             "26635 / 26635, [(128, 120)], 5327 frames, 40 streams")

    # 23 to 26  MIPS disassembler
    if exe:
        load, entry_pc, tsize, toff = mips.exe_mapping(exe)
        tot = dec = rtok = 0
        histo = collections.Counter()
        jal_t = collections.Counter()
        wmap = {}
        for va, w in mips.iter_words(exe, load, toff, tsize):
            wmap[va] = w
            tot += 1
            t = mips.dis(w, va)
            if t is None:
                continue
            dec += 1
            histo[t.split()[0]] += 1
            if t.startswith("jal 0x"):
                jal_t[int(t.split()[1], 16)] += 1
            try:
                if mips.asm(t, va) == w:
                    rtok += 1
            except Exception:
                pass
        rep.gate(23, "MIPS decode round trip", rtok == dec,
                 "%d / %d decodable" % (rtok, dec), "all decodable words")

        core = sum(histo[m] for m in ("lw", "sw", "addiu", "jal", "nop",
                                      "beq", "bne", "lui", "addu", "or"))
        share = 100.0 * core / dec
        rep.gate(24, "instruction histogram is MIPS-shaped", share > 50.0,
                 "core-10 share %.1f%%, top %s" % (share, histo.most_common(1)[0][0]),
                 "core-10 share > 50%")

        head = [t for _, _, t in mips.disasm_range(exe, load, entry_pc, 24)]
        entry_ok = any(t and t.startswith("lui gp,") for t in head) and             any(t and t.startswith(("j 0x", "jal 0x")) for t in head)
        rep.gate(25, "entry point looks like an entry", entry_ok,
                 "gp setup and a jump present" if entry_ok else "no gp setup or jump",
                 "gp setup plus jump into main")

        intext = [t for t in jal_t if load <= t < load + tsize]
        pre = sum(1 for t in intext if mips.dis(wmap.get(t - 8, 0), t - 8) == "jr ra")
        frac = 100.0 * pre / max(1, len(intext))
        rep.gate(26, "jal targets are function starts", frac >= 80.0,
                 "%d targets in text, %.1f%% after 'jr ra'" % (len(intext), frac),
                 ">= 80% preceded by 'jr ra'")
        # 27  COMPANION to gate 23. A round trip cannot see a wrong-but-consistent
        # rendering: ori/andi/xori zero-extend, and printing those immediates signed
        # reassembles perfectly while misleading every human reader. Gate on the text.
        logical = [w for w in wmap.values() if (w >> 26) in (0x0C, 0x0D, 0x0E)]
        shown = [mips.dis(w, 0) for w in logical]
        bad = sum(1 for t in shown if t and t.rsplit(",", 1)[1].startswith("-"))
        arith = [w for w in wmap.values() if (w >> 26) in (0x08, 0x09)]
        negs = sum(1 for w in arith
                   if (mips.dis(w, 0) or ",0").rsplit(",", 1)[1].startswith("-"))
        rep.gate(27, "logical immediates render unsigned  (COMPANION)",
                 bad == 0 and negs > 0,
                 "%d logical, %d signed; %d arithmetic, %d negative"
                 % (len(logical), bad, len(arith), negs),
                 "0 signed logical, arithmetic still shows negatives")
        # 28  text blocks embedded in the executable, found by header shape alone
        found = []
        for o in range(0, tsize - 24, 4):
            w = struct.unpack_from("<6I", exe, toff + o)
            a, bid, c, _d, e, _f6 = w
            # c == 24 only for a block with no dictionary; one WITH a dictionary
            # carries it in [24, c) and sets f6 to 24. Phase 46.
            if not (0x001 <= bid <= 0x600) or not (24 < a < 0x40000):
                continue
            if _f6 == 0:
                if c != 24:
                    continue
            elif _f6 == 24:
                if not (24 < c < a):
                    continue
            else:
                continue
            if e and not (24 < e <= a):
                continue
            if toff + o + a > len(exe):
                continue
            found.append((load + o, bid, a, e))
        rep.gate(28, "text blocks embedded in the executable",
                 [(v, b) for v, b, _a, _e in found]
                 == [(0x800AF1C8, 0x48C), (0x800B0C5C, 0x48D), (0x800B0D24, 0x48F)],
                 ", ".join("0x%08X id 0x%03X" % (v, b) for v, b, _a, _e in found) or "none",
                 "0x800AF1C8 id 0x48C, 0x800B0C5C id 0x48D, 0x800B0D24 id 0x48F")

        # 29  COMPANION to 28. The block is only real if references resolve INTO it.
        # Two static tables the disassembly names must land on its string starts, and a
        # one-bit shift must destroy that. Without this, gate 28 only proves six integers
        # happened to look like a header.
        blk = textblock.TextBlock(exe[toff + (0x800AF1C8 - load):
                                      toff + (0x800AF1C8 - load) + 6796 + 4])
        starts = huffman.string_starts(blk)
        def _tbl(base, stride, fields):
            out = []
            for i in range(4096):
                vs = []
                for f in fields:
                    off = toff + (base + stride * i + f - load)
                    vs.append(struct.unpack_from("<I", exe, off)[0])
                if (vs[0] >> 20) != 0x48C:
                    break
                out += [v & 0xFFFFF for v in vs if (v >> 20) == 0x48C]
            return out
        refs = _tbl(0x800A9FA0, 48, (20, 24)) + _tbl(0x80019CE4, 16, (8,))
        c8 = blk.c * 8
        hit = sum(1 for v in refs if (v - c8) in starts)
        off1 = sum(1 for v in refs if (v - c8 + 1) in starts)
        rep.gate(29, "executable tables resolve into it  (COMPANION)",
                 len(refs) == 213 and hit == len(refs) and off1 == 0,
                 "%d refs, %d on a string start, %d at +1 bit" % (len(refs), hit, off1),
                 "213 refs, all on a string start, 0 at +1 bit")

        # 45  THE SPLIT-IMMEDIATE RECOGNIZER, scored before anything believes it.
        #
        # Gates 29 and 30 cover references STORED as a word. This covers the ones
        # the code CONSTRUCTS, which no search for a literal can find, and which
        # a rewriter that cannot see them silently declines to fix. That is not a
        # hypothetical: an undercounting recognizer is an undercount someone may
        # notice, but a REWRITER with the same blind spot leaves the reference
        # stale and the build is green, because the gate was handed the same list
        # the rewriter used. This gate breaks that loop by scoring the recognizer
        # against sites confirmed by disassembly rather than by the rewriter.
        #
        # Three parts, and the second is the one that matters most:
        #
        #   POSITIVE  the three lui/ori pairs that build 0x048C09A31 in a1.
        #   READ-WRITE AGREEMENT  rewrite those halves to a different valid
        #             string start and rescan. The recognizer must recover the
        #             SAME three offsets carrying the NEW value. A reader and a
        #             writer that disagree is exactly how a build ships half
        #             translated, and nothing else here would catch it.
        #   NEGATIVE  ids that name no executable block must score zero.
        #
        # WHAT IS DELIBERATELY NOT USED AS A CONTROL, because it was measured and
        # it does not discriminate. The +/-1 bit shift that makes gate 29 sharp
        # is useless here: string offset 0 is a real start, so shifting the set
        # by one admits the immediate 1, and `lui rX,0x048C` then `ori rX,rX,1`
        # is an ordinary code shape. It scores 32 against the real 3. A shuffled
        # starts set of the same size scores 0, 10, 15, 15 and 0 over five seeds,
        # which is not a control either. A DISCRIMINATOR THAT WORKS FOR ONE
        # INSTRUMENT DOES NOT TRANSFER TO ANOTHER JUST BECAUSE THE POPULATION IS
        # THE SAME, and both figures are recorded here so nobody re-derives them.
        #
        # SCOPE, stated because a scoped sweep must report a scoped number: the
        # executable only. The archive carries far more of these, in overlay
        # images, and sweeping it costs minutes.
        si_text = exe[toff:toff + tsize]
        si_starts = huffman.string_offsets(
            [b for _v, b in referrers.exe_blocks(exe, load, toff, tsize)
             if b.id == 0x048C][0])
        si_sites = splitimm.find_word_refs(si_text, 0x048C, si_starts, base=load)
        si_pairs = [(s.hi_off, s.lo_off) for s in si_sites]
        si_vals = sorted(set(s.value for s in si_sites))
        # READ-WRITE AGREEMENT. Rewrite both halves at every site to a different
        # valid reference and rescan. Both halves always, never the low one
        # alone: a low-half-only patch is correct until the value crosses a
        # 0x10000 boundary and then silently is not.
        si_new = (0x048C << 20) | sorted(si_starts)[5]
        si_buf = bytearray(si_text)
        for s in si_sites:
            hi, lo = splitimm.halves(si_new, s.lo_op)
            for _o, _imm in ((s.hi_off - load, hi), (s.lo_off - load, lo)):
                _w = struct.unpack_from("<I", si_buf, _o)[0]
                struct.pack_into("<I", si_buf, _o, (_w & 0xFFFF0000) | _imm)
        si_again = splitimm.find_word_refs(bytes(si_buf), 0x048C, si_starts,
                                           base=load)
        si_rt = ([(s.hi_off, s.lo_off) for s in si_again] == si_pairs
                 and sorted(set(s.value for s in si_again)) == [si_new])
        si_ctrl = {t: len(splitimm.find_word_refs(si_text, t, si_starts,
                                                 base=load))
                   for t in (0x0001, 0x0123, 0x0999, 0x0FFF)}
        rep.gate(45, "split-immediate recognizer  (COMPANION)",
                 si_pairs == [(0x8002C070, 0x8002C078), (0x8002C168, 0x8002C170),
                              (0x8008D4AC, 0x8008D4B4)]
                 and si_vals == [0x048C09A31] and si_rt
                 and not any(si_ctrl.values()),
                 "%d sites, value(s) %s, rewrite round trip %s, controls %s"
                 % (len(si_sites), ", ".join("0x%08X" % v for v in si_vals),
                    "OK" if si_rt else "FAILED",
                    ", ".join("%04X:%d" % kv for kv in sorted(si_ctrl.items()))),
                 "3 sites building 0x048C09A31, rewrite round trip OK, "
                 "0 for every control id")
        # 42  MENU TEXT RESOLVES IN FONT 1, which is a different table from the
        # one gate 38 checks. MEASURED, Phase 59: the message box draws from
        # FONT2 and the menus draw from FONT1. The tables are not the same set,
        # so a menu string checked against font 2 is not checked at all.
        # The range is exe block 0x048C indices 550 to 778, which is the menu
        # vocabulary: the command menu, the item and spell verbs, the tactics
        # list, the adventure-log menu and the Yes/No pair at 757 and 758.
        fimg = exe[toff:toff + tsize]
        menu_codes = set()
        n_menu = 0
        for _va, tb in referrers.exe_blocks(exe, load, toff, tsize):
            if tb.id != 0x048C:
                continue
            tree = huffman.HuffmanTree(tb)
            syms = tree.decode()
            entries = dictionary.parse(tb.raw, tb)
            expanded, _u = dictionary.expand(syms, entries)
            estr, _t = huffman.split_strings(expanded)
            for st in estr[550:779]:
                n_menu += 1
                for kind, val in st:
                    if kind == huffman.SJIS:
                        menu_codes.add(val)
        miss1 = fonts.missing(fimg, load, fonts.FONT1, menu_codes)
        rep.gate(42, "menu strings resolve in font 1",
                 n_menu == 229 and len(menu_codes) == 172 and not miss1,
                 "%d strings, %d distinct codes, %d missing from font 1"
                 % (n_menu, len(menu_codes), len(miss1)),
                 "229 strings, 172 codes, 0 missing")

        # 43  COMPANION to 42, and it validates the INSTRUMENT rather than the
        # data. Gate 42 passes trivially on the shipped disc because the shipped
        # menu is Japanese and every code it draws is present; a checker that
        # always returned "nothing missing" would pass it too. So: feed the
        # checker a code KNOWN to be absent from font 1 and require it to say so,
        # and assert the two tables actually differ, because if `table` ever
        # returned the same set for both bases gate 42 would be checking font 2.
        # 0x8166 is the apostrophe. It has no font 1 entry in the shipped
        # executable, which is exactly why an English menu cannot use one yet.
        probe = fonts.missing(fimg, load, fonts.FONT1, {0x8166, 0x8147})
        t1 = set(fonts.table(fimg, load, fonts.FONT1))
        t2 = set(fonts.table(fimg, load, fonts.FONT2))
        rep.gate(43, "the font 1 checker detects a known absence  (COMPANION)",
                 probe == [0x8147, 0x8166] and len(t1 - t2) == 98
                 and len(t2 - t1) == 86 and len(t1 & t2) == 435,
                 "probe reported %d of 2 absent; font1-only %d, font2-only %d,"
                 " shared %d" % (len(probe), len(t1 - t2), len(t2 - t1),
                                 len(t1 & t2)),
                 "both probes absent; 98 / 86 / 435")
    else:
        for g in (23, 24, 25, 26, 27, 28, 29, 42, 43):
            print("  SKIP gate %d  MIPS gates need SLPM_869.16" % g)

    # 35  the bit budget identity. A string's encoded length is the span from its
    # start offset to the next END; those spans plus the trailing residue must
    # account for the code stream exactly. This is arithmetic, so any failure is a
    # decoder fault, not a tolerance.
    bad = 0
    tot_region = tot_consumed = tot_residue = 0
    for _s, sb in hbd.text_sub_blocks(blocks):
        tb = textblock.TextBlock(hbd.sub_bytes(arch, sb))
        offs = huffman.string_offsets(tb)
        region = (tb.e - tb.c) * 8
        residue = region - offs[-1]
        spans = sum(offs[n + 1] - offs[n] for n in range(len(offs) - 1))
        tot_region += region
        tot_consumed += offs[-1]
        tot_residue += residue
        if spans + residue != region:
            bad += 1
    rep.gate(35, "bit budget accounts for the code stream exactly",
             bad == 0 and tot_consumed + tot_residue == tot_region,
             "%d blocks fail; %d region = %d consumed + %d residue"
             % (bad, tot_region, tot_consumed, tot_residue),
             "0 blocks fail, totals balance")

    # 30  the type 26 referrer system, with its own shuffled control.
    # Scoped to the 30 most-referenced text ids so it stays cheap; the point is the
    # separation from the control, not the absolute count.
    t26 = [sb for _s, sb in hbd.sub_blocks(blocks) if sb["type"] == 26]
    bufs = []
    seen_c = set()
    for sb in t26:
        raw = hbd.sub_bytes(arch, sb)
        if sb["flags"] == hbd.FLAG_LZS:
            try:
                raw = lzs.decompress(raw)
            except Exception:
                continue
        if raw not in seen_c:
            seen_c.add(raw)
            bufs.append(raw)
    cand = collections.Counter()
    for b in bufs:
        for k in range(0, len(b) - 3, 4):
            w = struct.unpack_from("<I", b, k)[0]
            cand[w >> 20] += 1
    tb_by_id = {}
    for _s, sb in hbd.text_sub_blocks(blocks):
        tb = textblock.TextBlock(hbd.sub_bytes(arch, sb))
        tb_by_id.setdefault(tb.id, tb)
    # every valid text id the data actually names, not a top-N slice: a slice by
    # candidate volume is dominated by ids that appear only by chance and drags the
    # measured rate away from the population figure.
    want = [i for i in cand if i in tb_by_id]
    starts = {i: huffman.string_starts(tb_by_id[i]) for i in want}
    wantset = set(want)

    def _t26(bs):
        tot = hit = 0
        for b in bs:
            for k in range(0, len(b) - 3, 4):
                # Scope to the reference field, words 0 to 2 of each 60-byte record.
                # Rating a whole sub-block mixes the field with unrelated words whose
                # top 12 bits happen to fall in the id range, dragging 98% down to 43%.
                if (k // 4) % 15 > 2:
                    continue
                w = struct.unpack_from("<I", b, k)[0]
                i = w >> 20
                if i not in wantset:
                    continue
                tot += 1
                if ((w & 0xFFFFF) - tb_by_id[i].c * 8) in starts[i]:
                    hit += 1
        return tot, hit

    tot26, hit26 = _t26(bufs)
    rnd = random.Random(9)
    ctrl = [bytes(sorted(b, key=lambda _c: rnd.random())) for b in bufs]
    ctot, chit = _t26(ctrl)
    real_rate = 100.0 * hit26 / max(1, tot26)
    ctrl_rate = 100.0 * chit / max(1, ctot)
    rep.gate(30, "type 26 is a referrer system  (COMPANION)",
             real_rate > 95.0 and ctrl_rate < 3.0 and real_rate > 20 * ctrl_rate,
             "real %.2f%% (%d/%d), shuffled %.2f%% (%d/%d)"
             % (real_rate, hit26, tot26, ctrl_rate, chit, ctot),
             "real > 95%, shuffled < 3%, real at least 20x control")

    # 31  COMPANION to 30. The 60-byte record period must hold WITHOUT the corpus,
    # otherwise gate 30's scoping is fitted to the hit data. Two structural facts:
    # every sub-block is a whole number of records, and residues 3 to 11 never carry a
    # word whose top 12 bits are a text id.
    ids_present = set(tb_by_id)
    whole26 = sum(1 for b in bufs if (len(b) % 60) == 0)
    stray = 0
    for b in bufs:
        for k in range(0, len(b) - 3, 4):
            if 3 <= (k // 4) % 15 <= 11:
                if (struct.unpack_from("<I", b, k)[0] >> 20) in ids_present:
                    stray += 1
    rep.gate(31, "type 26 record period holds without the corpus  (COMPANION)",
             whole26 == len(bufs) and stray == 0,
             "%d / %d sub-blocks are whole 60-byte records, %d stray ids in residues 3-11"
             % (whole26, len(bufs), stray),
             "all sub-blocks whole, 0 stray")

    # 32  type 44 is a third referrer system. Its absolute hit rate is only ~1.7%,
    # because these sub-blocks are large and mostly other data, so the rate is NOT the
    # discriminator and a gate on it would be meaningless. Concentration is: a real
    # pointer table names a handful of text ids, shuffled bytes scatter across many.
    t44, seen44 = [], set()
    for _s, sb in hbd.sub_blocks(blocks):
        if sb["type"] != 44:
            continue
        raw = hbd.sub_bytes(arch, sb)
        if sb["flags"] == hbd.FLAG_LZS:
            try:
                raw = lzs.decompress(raw)
            except Exception:
                continue
        if raw not in seen44:
            seen44.add(raw)
            t44.append(raw)
    starts44 = {}

    def _t44(bs):
        refs = set()
        for b in bs:
            for k in range(0, len(b) - 3, 4):
                w = struct.unpack_from("<I", b, k)[0]
                i = w >> 20
                if i not in tb_by_id:
                    continue
                if i not in starts44:
                    starts44[i] = huffman.string_starts(tb_by_id[i])
                off = (w & 0xFFFFF) - tb_by_id[i].c * 8
                if off in starts44[i]:
                    refs.add((i, off))
        return refs

    r44 = _t44(t44)
    rnd2 = random.Random(77)
    c44 = _t44([bytes(sorted(b, key=lambda _c: rnd2.random())) for b in t44])
    nr, nc = len({i for i, _o in r44}), len({i for i, _o in c44})
    rep.gate(32, "type 44 references concentrate  (COMPANION)",
             len(r44) > 1400 and nr <= 20 and nc >= 40,
             "real %d refs in %d ids, shuffled %d refs in %d ids"
             % (len(r44), nr, len(c44), nc),
             "real > 1400 refs in <= 20 ids, shuffled scattered over >= 40 ids")

    # 37  the cutscene command. Three bytes on a BYTE-aligned stream, not a
    # word-aligned u32: the same bytes occur at all four alignments, so reading
    # only the 4-aligned quarter sees a quarter of the stream. Gated by the
    # one-bit collapse, which no alignment artifact survives.
    t39, seen39 = [], set()
    for _s, sb in hbd.sub_blocks(blocks):
        if sb["type"] != 39:
            continue
        raw = hbd.sub_bytes(arch, sb)
        if sb["flags"] == hbd.FLAG_LZS:
            raw = lzs.decompress(raw)
        if raw not in seen39:
            seen39.add(raw)
            t39.append(raw)
    idx39 = referrers.block_index(arch, blocks)

    def _t39(shift):
        tot = hit = 0
        for raw in t39:
            o = raw.find(referrers.SCRIPT_CMD)
            while o >= 0:
                q = o + 3
                if q + 4 <= len(raw):
                    w = struct.unpack_from("<I", raw, q)[0]
                    ent = idx39.get(w >> 20)
                    if ent is not None:
                        tot += 1
                        tb, offs, pos = ent
                        i = pos.get((w & 0xFFFFF) - tb.c * 8 + shift)
                        if i is not None and i + 1 < len(offs):
                            hit += 1
                o = raw.find(referrers.SCRIPT_CMD, o + 1)
        return tot, hit

    n39, h39 = _t39(0)
    _t, hp = _t39(1)
    _t, hm = _t39(-1)
    rep.gate(37, "type 39 cutscene command resolves  (COMPANION)",
             len(t39) == 927 and h39 == 3388 and hp == 0 and hm == 0,
             "%d scripts, %d of %d valid-id commands on a string start, +1 %d, -1 %d"
             % (len(t39), h39, n39, hp, hm),
             "927 scripts, 3388 hits, 0 at +/-1 bit")

    # 22  corpus roll-up
    if args.corpus_out:
        built = corpusmod.build(args.dq4, args.corpus_out)
        roll = built["rollup"]
        # Pinned to a corpus built from unmodified text, so ANY content build moves
        # it. Verdict on the source, NOTE elsewhere, same reason as gate 7.
        if is_source:
            rep.gate(22, "corpus roll-up hash", roll == corpusmod.ROLLUP_EXPECTED,
                     roll[:16] + "...", corpusmod.ROLLUP_EXPECTED[:16] + "...")
        else:
            rep.note(22, "corpus roll-up: not the source disc",
                     "%s... (source is %s...)"
                     % (roll[:16], corpusmod.ROLLUP_EXPECTED[:16]))

        # 33  the executable-resident subtree hashes separately, so a moved archive
        # roll-up still means exactly one thing.
        eroll = built["exe_rollup"]
        rep.gate(33, "corpus exe subtree roll-up",
                 eroll == corpusmod.EXE_ROLLUP_EXPECTED,
                 "%s... %d blocks, %d strings"
                 % (eroll[:16], built["exe"]["blocks"], built["exe"]["strings"]),
                 corpusmod.EXE_ROLLUP_EXPECTED[:16] + "... 3 blocks, 1120 strings")

        # 40  The third population, the type 46 MIPS overlays. Gated the same way
        # the executable subtree is, and with the same reason: a moved archive
        # roll-up must keep meaning exactly one thing. The companion figures are
        # asserted alongside the hash so a hash that matches for the wrong reason
        # still fails. MEASURED, Phase 52 and 53.
        oroll = built["ov_rollup"]
        ovs = built["overlay"]
        rep.gate(40, "corpus overlay subtree roll-up",
                 (oroll == corpusmod.OVERLAY_ROLLUP_EXPECTED
                  and ovs["blocks"] == 15 and ovs["strings"] == 1695
                  and ovs["chars"] == 28602 and ovs["occurrences"] == 451),
                 "%s... %d blocks, %d strings, %d chars, %d occurrences"
                 % (oroll[:16], ovs["blocks"], ovs["strings"], ovs["chars"],
                    ovs["occurrences"]),
                 corpusmod.OVERLAY_ROLLUP_EXPECTED[:16]
                 + "... 15 blocks, 1695 strings, 28602 chars, 451 occurrences")

        # 41  COMPANION to 40. A roll-up over 15 files can match while the
        # LOCATOR is wrong, so assert the property the locator rests on: every
        # overlay text id is absent from both other populations. If type 46 ever
        # started duplicating archive ids, gate 40 alone would not notice.
        ov_ids = set()
        for line in open(os.path.join(args.corpus_out, "overlay", "blockindex.txt"),
                         encoding="utf-8"):
            if line.startswith("#") or "|" not in line:
                continue
            ov_ids.add(int(line.split("|")[0].strip(), 16))
        arch_ids = set()
        for sector, sub in hbd.text_sub_blocks(blocks):
            raw = hbd.sub_bytes(arch, sub)
            if len(raw) >= 24:
                arch_ids.add(textblock.TextBlock(raw).id)
        eids = {tb.id for _va, tb in referrers.exe_blocks(exe, load, toff, tsize)}
        rep.gate(41, "overlay ids are a population of their own  (COMPANION)",
                 len(ov_ids) == 15 and not (ov_ids & arch_ids) and not (ov_ids & eids),
                 "%d overlay ids, %d shared with the archive, %d with the executable"
                 % (len(ov_ids), len(ov_ids & arch_ids), len(ov_ids & eids)),
                 "15 overlay ids, 0 shared with either")


        # 34  COMPANION. The corpus must agree with Phase 12 Task D on the operative
        # per-block figure. If the generator and the phase report disagree, one of
        # them is wrong and a matching roll-up would hide it.
        # chars_clean is the NON-DUMMY figure. Dummy-only blocks are trivially
        # CLEAN, and counting their 543 characters inflated the published total to
        # 139,735. Both numbers are asserted so neither basis can drift.
        # The BLOCK counts are structural and hold on any content build, so they
        # stay a verdict. The CHARACTER totals are pinned to unmodified text and
        # a growth build moves them, so they are only asserted on the source.
        # Build 2c moved them by exactly +9, the symbols it duplicated, which is
        # how this split was found.
        ok34 = built["clean_nd"] == 673 and built["total_nd"] == 925
        if is_source:
            ok34 = (ok34 and built["chars_clean"] == 491333
                    and built["chars_clean_dummy"] == 543)
        rep.gate(34, "per-block editability matches Phase 15  (COMPANION)", ok34,
                 "%d CLEAN of %d non-dummy blocks, %d chars CLEAN non-dummy"
                 " + %d in dummy-only blocks"
                 % (built["clean_nd"], built["total_nd"], built["chars_clean"],
                    built["chars_clean_dummy"]),
                 "673 CLEAN of 925 non-dummy"
                 + (", 491333 chars + 543 dummy" if is_source
                    else ", character totals not pinned off-source"))

        # 36  the suffix rule. A string is editable exactly when no unresolved
        # string sits after it, so the editable set is the suffix from the last
        # unresolved index. Asserted because it is the operative figure and it is
        # derived from the referrer map rather than the lossy status column.
        # Same split as gate 34: the STRING count is structural, the character
        # totals are pinned to unmodified text.
        ok36 = built["ed_strings"][0] == 13891
        if is_source:
            ok36 = (ok36 and built["ed_chars"][0] == 598364
                    and built["ed_chars"][1] == 69540)
        rep.gate(36, "suffix-rule editability, non-dummy blocks", ok36,
                 "%d editable strings, %d editable chars, %d frozen"
                 % (built["ed_strings"][0], built["ed_chars"][0], built["ed_chars"][1]),
                 "13891 strings"
                 + (", 598364 chars editable, 69540 frozen" if is_source
                    else ", character totals not pinned off-source"))
    else:
        print("  SKIP gates 22, 33, 34  corpus gates need --corpus-out <dir>")


    # 44  CARRIER COVERAGE.
    #
    # DQ4_2026_08_27_INN.bin passed 35 gates and shipped with 0x047C English in
    # 65 of its 69 carriers: the four TYPE 44 copies were still Japanese. No
    # gate covered carrier coverage, so nothing failed.
    #
    # scratch/p119/carriers.py had written the warning down -- "if a type 44
    # carrier holds a byte-different copy of the same id, editing the type 46
    # copies leaves that one Japanese" -- and it never fired, because a note in
    # a file is not a gate. This is that note, promoted.
    #
    # An id lives in more than one carrier and in more than one MEDIUM: the
    # executable, type 40/42 sub-blocks, type 44 overlays and type 46 overlay
    # images. A build that rewrites one medium and not the others produces an
    # image whose every structural gate passes and whose text is half
    # translated.
    if args.edited_ids:
        want_ids = []
        for tok in args.edited_ids.split(","):
            tok = tok.strip()
            if tok:
                want_ids.append(int(tok, 16))
        rows44 = []
        blind44 = 0
        for tid in want_ids:
            copies, blind = _carriers_of(arch, exe, tid)
            blind44 = max(blind44, blind)
            if not copies:
                rows44.append((tid, 0, 0, "id not located in any carrier"))
                continue
            # Group by the block's own bytes. Every carrier of one id should
            # hold the same block after a build; a carrier holding a different
            # payload is a copy the build did not reach.
            groups = {}
            for where, blob in copies:
                groups.setdefault(hashlib.sha256(blob).hexdigest(), []).append(where)
            top = max(groups.values(), key=len)
            rows44.append((tid, len(top), len(copies),
                           "" if len(groups) == 1 else
                           "%d distinct payloads; smallest group: %s"
                           % (len(groups),
                              ", ".join(sorted(min(groups.values(), key=len))[:4]))))
        # blind44 is part of the VERDICT, not a footnote. A carrier this scan
        # could not read is a carrier it did not check, and N/N over a shrunken
        # denominator is the same string N/N over the true one produces.
        ok44 = (all(n == m for _, n, m, _ in rows44) and bool(rows44)
                and blind44 == 0)
        detail = "; ".join("%04X %d/%d%s" % (t, n, m, (" " + w) if w else "")
                           for t, n, m, w in rows44)
        detail += "; %d unexaminable sub-blocks" % blind44
        rep.gate(44, "carrier coverage, every carrier of every edited id", ok44,
                 detail,
                 "N/N on every declared id, both media, 0 unexaminable")
    else:
        rep.note(44, "carrier coverage",
                 "SKIPPED, no --edited-ids. A build that does not declare what "
                 "it edited cannot be checked for having missed a copy.")

    return 0 if rep.summary() else 1


if __name__ == "__main__":
    sys.exit(main())
