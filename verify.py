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

from dq4 import iso as isomod
from dq4 import hbd, textblock, huffman, dictionary, sectortable, glyph, codes, lzs, fonts
from dq4 import corpus as corpusmod
from dq4 import mips, referrers

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
        rep.gate(17, "glyph atlas, two glyphs per cell, Latin and digits",
                 at.slots == 288 and nb == 268 and drawn == 62,
                 "%d slots, %d non-blank, %d of 62 letters and digits drawn"
                 % (at.slots, nb, drawn),
                 "288 slots, 268 non-blank, 62 of 62 drawn")
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
            if c != 24 or not (0x001 <= bid <= 0x600) or not (24 < a < 0x40000):
                continue
            if e and not (24 < e <= a):
                continue
            if toff + o + a > len(exe):
                continue
            found.append((load + o, bid, a, e))
        rep.gate(28, "text blocks embedded in the executable",
                 [(v, b) for v, b, _a, _e in found]
                 == [(0x800AF1C8, 0x48C), (0x800B0C5C, 0x48D)],
                 ", ".join("0x%08X id 0x%03X" % (v, b) for v, b, _a, _e in found) or "none",
                 "0x800AF1C8 id 0x48C, 0x800B0C5C id 0x48D")

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
    else:
        for g in (23, 24, 25, 26, 27, 28, 29):
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
                 corpusmod.EXE_ROLLUP_EXPECTED[:16] + "... 2 blocks, 779 strings")

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

    return 0 if rep.summary() else 1


if __name__ == "__main__":
    sys.exit(main())
