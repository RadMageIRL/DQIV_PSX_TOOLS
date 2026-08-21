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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dq4 import iso as isomod
from dq4 import hbd, textblock, huffman, dictionary, sectortable, glyph, codes, lzs
from dq4 import corpus as corpusmod
from dq4 import mips

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
        print("  %-4s gate %-2d  %-46s measured %-28s expected %s"
              % ("PASS" if ok else "FAIL", n, name, measured, expected))

    def summary(self):
        bad = [r for r in self.rows if not r[2]]
        print("\n%d / %d gates pass" % (len(self.rows) - len(bad), len(self.rows)))
        if bad:
            print("FAILED:")
            for n, name, _, m, e in bad:
                print("   gate %d %s: measured %s, expected %s" % (n, name, m, e))
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
    rep.gate(1, "archive size and disc SHA-256",
             size == Q41_SIZE and sha == DISC_SHA256,
             "%d bytes, %s" % (size, sha[:16] + "..."),
             "%d bytes, %s" % (Q41_SIZE, DISC_SHA256[:16] + "..."))

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
    rep.gate(7, "text id 0x006C decode",
             pieces == 12 and s10 == STRING_10,
             "%d pieces (%d END-terminated + residue), [10] = %s"
             % (pieces, len(strings), s10),
             "12 pieces, [10] = %s" % STRING_10)

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

    # 17
    atlases = glyph.find_atlases(arch, blocks)
    big = [b for _, _, b in atlases if len(b) == 16128]
    if big:
        at = glyph.Atlas(big[0])
        nb = at.non_blank_count()
        latin_ok = all(not at.is_blank(s) and at.extent(s)[1] == 3 and
                       at.extent(s)[2] == 13 for s in glyph.DQ4_LATIN_SLOTS)
        rep.gate(17, "glyph atlas slots and Latin capitals",
                 at.slots == 288 and nb == 268 and latin_ok and
                 len(glyph.DQ4_LATIN_SLOTS) == 13,
                 "%d slots, %d non-blank, %d Latin"
                 % (at.slots, nb, len(glyph.DQ4_LATIN_SLOTS)),
                 "288 slots, 268 non-blank, 13 Latin")
    else:
        rep.gate(17, "glyph atlas slots and Latin capitals", False, "atlas not found",
                 "288 slots, 268 non-blank, 13 Latin")

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
    else:
        for g in (23, 24, 25, 26, 27):
            print("  SKIP gate %d  MIPS gates need SLPM_869.16" % g)

    # 22  corpus roll-up
    if args.corpus_out:
        roll, *_ = corpusmod.build(args.dq4, args.corpus_out)
        rep.gate(22, "corpus roll-up hash", roll == corpusmod.ROLLUP_EXPECTED,
                 roll[:16] + "...", corpusmod.ROLLUP_EXPECTED[:16] + "...")
    else:
        print("  SKIP gate 22  corpus roll-up hash                          "
              "pass --corpus-out <dir> to run it")

    return 0 if rep.summary() else 1


if __name__ == "__main__":
    sys.exit(main())
