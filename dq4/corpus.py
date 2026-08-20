"""Corpus generator.

Regenerates the whole decoded corpus from a disc image in one command:

    python -m dq4.corpus --disc <path to .bin> --out <dir>

Everything under the output directory is derived. Nothing is hand edited, and
the tree is reproducible byte for byte from the same disc and the same library,
which is what makes the roll-up hash in MANIFEST.md meaningful.

The output is a complete decoded script of a copyrighted game. It does not
belong in any repository. See the README.
"""

import argparse
import collections
import hashlib
import os
import struct
import sys

from . import iso as isomod
from . import hbd, textblock, huffman, dictionary, sectortable, codes

# Baseline roll-up. Stored in the LIBRARY, not in the corpus, so the corpus
# cannot silently update its own expectation. If a library change moves this,
# diff the corpus and review before accepting a new value.
ROLLUP_EXPECTED = "64c83f32f00daa0c6cc60fff795dbbebdc5f5a57c92234ea79605535fe39cc64"

CTRL_RANGE_SUB = set(range(0x7F11, 0x7F15)) | {0x7F1F, 0x7F42, 0x7F4B, 0x7F4C} \
    | set(range(0x7F20, 0x7F35))


def sym_text(kind, value):
    """Corpus rendering: control codes {7Fxx}, dictionary refs {7Exx}."""
    if kind in (huffman.CTRL, huffman.DICT):
        return "{%04X}" % value
    if kind == huffman.END:
        return ""
    try:
        return bytes([value >> 8, value & 0xFF]).decode("shift_jis")
    except Exception:
        return "{!%04X}" % value


def render(symbols):
    return "".join(sym_text(k, v) for k, v in symbols)


def write(path, lines):
    """Deterministic write: LF endings, no trailing whitespace, no timestamps."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        for ln in lines:
            f.write((ln.rstrip() + "\n").encode("utf-8"))


class Block:
    """One decoded text sub-block."""

    def __init__(self, arch, sector, sub):
        self.sector = sector
        self.sub = sub
        self.raw = hbd.sub_bytes(arch, sub)
        self.tb = textblock.TextBlock(self.raw)
        self.tree = huffman.HuffmanTree(self.tb)
        self.leaves, _, _ = self.tree.walk()
        self.symbols = self.tree.decode()
        self.entries = dictionary.parse(self.raw, self.tb)
        self.expanded, self.unresolved = dictionary.expand(self.symbols, self.entries)
        self.raw_strings, self.raw_tail = huffman.split_strings(self.symbols)
        self.exp_strings, self.exp_tail = huffman.split_strings(self.expanded)

    @property
    def id(self):
        return self.tb.id

    def records(self):
        """[(index, u32, char, extra)] from the table at d + 32."""
        tb = self.tb
        if tb.a - tb.tree_end < 48:
            return []
        try:
            _, _, p2 = struct.unpack_from("<3I", self.raw, tb.tree_end)
        except Exception:
            return []
        start = tb.tree_end + 32
        if not (start < p2 <= tb.a):
            return []
        out = []
        for i in range((p2 - start) // 8):
            o = start + 8 * i
            if o + 8 > len(self.raw):
                break
            v, w = struct.unpack_from("<2I", self.raw, o)
            out.append((i, v, w & 0xFFFF, w >> 16))
        return out


def build(disc_path, out_dir):
    with isomod.RawISO(disc_path) as disc:
        found = disc.find("HBD1PS1D.Q41")
        if not found:
            raise SystemExit("HBD1PS1D.Q41 not found in %s" % disc_path)
        arch = disc.extract(*found)
        exe_at = disc.find("SLPM_869.16")
        exe = disc.extract(*exe_at) if exe_at else b""

    blocks = hbd.scan_blocks(arch)
    texts = hbd.text_sub_blocks(blocks)

    by_id = collections.defaultdict(list)
    for sector, sub in texts:
        by_id[textblock.TextBlock(hbd.sub_bytes(arch, sub)).id].append((sector, sub))

    ctrl = collections.Counter()       # one block per distinct text id
    ctrl_all = collections.Counter()   # every sub-block, duplicates included
    for sector, sub in texts:
        b = Block(arch, sector, sub)
        for k, v in b.expanded:
            if k == huffman.CTRL:
                ctrl_all[v] += 1
    index_lines = ["# text id | sector | sub | type | dlen | symbols | strings | duplicate sectors"]
    variants = []
    side = []
    placeholders = []
    total_chars = 0
    str_lengths = []

    for tid in sorted(by_id):
        group = by_id[tid]
        # group byte-identical copies
        seen = {}
        for sector, sub in group:
            digest = hashlib.sha256(hbd.sub_bytes(arch, sub)).hexdigest()
            seen.setdefault(digest, []).append((sector, sub))
        for vi, digest in enumerate(sorted(seen)):
            members = sorted(seen[digest])
            sector, sub = members[0]
            b = Block(arch, sector, sub)
            suffix = "" if len(seen) == 1 else "_v%d" % vi
            name = "%04X%s" % (tid, suffix)
            if len(seen) > 1:
                variants.append((tid, vi, sector, sub["idx"], digest[:16]))

            raw_lines = ["# id %04X sector %d sub %d type %d dlen %d"
                         % (tid, sector, sub["idx"], sub["type"], sub["dlen"]),
                         "# symbols %d strings %d unresolved %d"
                         % (len(b.symbols), len(b.raw_strings), b.unresolved)]
            for i, st in enumerate(b.raw_strings):
                raw_lines.append("[%02d] %s" % (i, render(st)))
            if b.raw_tail:
                raw_lines.append("[tail] %s" % render(b.raw_tail))
            write(os.path.join(out_dir, "raw", name + ".txt"), raw_lines)

            exp_lines = raw_lines[:2]
            exp_lines = [exp_lines[0], exp_lines[1]]
            for i, st in enumerate(b.exp_strings):
                text = render(st)
                exp_lines.append("[%02d] %s" % (i, text))
                nchar = sum(1 for k, v in st if k == huffman.SJIS)
                total_chars += nchar
                str_lengths.append(nchar)
                side.append("[id %04X / str %02d / sector %d / sub %d]"
                            % (tid, i, sector, sub["idx"]))
                side.append("JP: %s" % text)
                side.append("EN:")
                side.append("NOTE:")
                side.append("")
                if any(k == huffman.CTRL and v in CTRL_RANGE_SUB for k, v in st):
                    placeholders.append("[id %04X / str %02d / sector %d / sub %d]"
                                        % (tid, i, sector, sub["idx"]))
                    placeholders.append(text)
                    placeholders.append("")
            if b.exp_tail:
                exp_lines.append("[tail] %s" % render(b.exp_tail))
            write(os.path.join(out_dir, "expanded", name + ".txt"), exp_lines)

            for k, v in b.expanded:
                if k == huffman.CTRL:
                    ctrl[v] += 1

            bits = (b.tb.e - b.tb.c) * 8
            kraft = sum(2.0 ** -d for d, _, _, _, _ in b.leaves)
            tree_lines = [
                "# id %04X sector %d sub %d" % (tid, sector, sub["idx"]),
                "pairs           %d" % b.tree.n,
                "m               %d" % b.tree.m,
                "root            %d" % b.tree.root,
                "leaves          %d" % len(b.leaves),
                "kraft_sum       %.12f" % kraft,
                "code_bits       %d" % bits,
                "symbols         %d" % len(b.symbols),
                "bits_per_symbol %.4f" % (bits / len(b.symbols) if b.symbols else 0.0),
                "min_leaf_depth  %d" % min(d for d, _, _, _, _ in b.leaves),
            ]
            write(os.path.join(out_dir, "trees", name + ".txt"), tree_lines)

            if b.entries:
                dl = ["# id %04X  %d entries  table at %d" % (tid, len(b.entries), b.tb.f6)]
                for i, seq in enumerate(b.entries):
                    w = struct.unpack_from("<H", b.raw, b.tb.f6 + 2 * i)[0]
                    dl.append("{7E%02X} len=%d off=%d  %s"
                              % (i + 1, (w >> 12) & 0xF, w & 0x0FFF,
                                 "".join(sym_text(huffman.CTRL if k == "CTRL" else huffman.SJIS, v)
                                         for k, v in seq)))
                write(os.path.join(out_dir, "dictionaries", name + ".txt"), dl)

            recs = b.records()
            if recs:
                rl = ["# id %04X  %d records at d+32" % (tid, len(recs)),
                      "# index | u32 | char | extra"]
                for i, v, ch, ex in recs:
                    rl.append("%3d  %10d  %04X  %04X" % (i, v, ch, ex))
                write(os.path.join(out_dir, "records", name + ".txt"), rl)

            dups = ",".join(str(s) for s, _ in members[1:]) or "-"
            index_lines.append("%04X%s | %d | %d | %d | %d | %d | %d | %s"
                               % (tid, suffix, sector, sub["idx"], sub["type"],
                                  sub["dlen"], len(b.symbols), len(b.raw_strings), dups))

    write(os.path.join(out_dir, "meta", "blockindex.txt"), index_lines)

    cl = ["# control code census, dictionary expanded",
          "#",
          "# two bases, and they are not interchangeable:",
          "#   per_id   counts one block per distinct text id (%d blocks)" % len(by_id),
          "#   all      counts every text sub-block on the disc (%d blocks)" % len(texts),
          "# published phase figures use the 'all' basis.",
          "#",
          "# code | per_id | all | meaning"]
    for v in sorted(set(ctrl) | set(ctrl_all)):
        cl.append("%04X | %d | %d | %s" % (v, ctrl.get(v, 0), ctrl_all.get(v, 0),
                                           codes.describe(v)))
    write(os.path.join(out_dir, "meta", "controlcodes.txt"), cl)

    st = ["# sector table from SLPM_869.16, %d entries" % 0]
    if exe:
        rows = sectortable.entries(exe)
        st = ["# sector table from SLPM_869.16, %d entries" % len(rows),
              "# offset | raw | length | disc lba | archive sector | resolves"]
        for off, v, length, lba, sec in rows:
            blk = blocks.get(sec)
            ok = "yes" if blk is not None and blk["nsec"] == length else "no"
            st.append("%06X | %08X | %d | %d | %d | %s" % (off, v, length, lba, sec, ok))
    write(os.path.join(out_dir, "meta", "sectortable.txt"), st)

    write(os.path.join(out_dir, "dq4-side-by-side.txt"), side)
    write(os.path.join(out_dir, "dq4-placeholder-extract.txt"), placeholders)

    gl = ["# name and substitution codes. English column intentionally empty.",
          "#",
          "# per_id counts one block per distinct text id; all counts every sub-block.",
          "# published phase figures use the 'all' basis.",
          "#",
          "# code | japanese | per_id | all | english"]
    for v in codes.NAME_CODES:
        if v not in codes.MANDY and not ctrl_all.get(v):
            gl.append("%04X | not present in data | 0 | 0 |" % v)
            continue
        gl.append("%04X | %s | %d | %d |" % (v, codes.MANDY.get(v, "?"),
                                             ctrl.get(v, 0), ctrl_all.get(v, 0)))
    gl.append("")
    gl.append("# codes present in the data and absent from the published table.")
    gl.append("# no meanings are proposed.")
    for v in codes.EXTRA:
        gl.append("%04X | unknown | %d | %d |" % (v, ctrl.get(v, 0), ctrl_all.get(v, 0)))
    write(os.path.join(out_dir, "dq4-name-glossary.txt"), gl)

    write(os.path.join(out_dir, "dq4-voice-sheet.txt"), voice_sheet(ctrl_all))

    rollup, nfiles = manifest(out_dir, len(by_id), total_chars, str_lengths, variants)
    return rollup, nfiles, len(by_id), total_chars, str_lengths, variants, len(side) // 5, \
        len(placeholders) // 3


def voice_sheet(ctrl):
    return [
        "# DQ4 voice sheet: engine constraints only.",
        "# Each entry: constraint, measured evidence, reference, status.",
        "# Nothing is RULE until it is decided and verified. All three start OPEN.",
        "",
        "## 1. Enumeration slots",
        "constraint: 0x7F11 through 0x7F14 appear as a comma separated list.",
        "evidence:   {7F04}　　{7F11}、{7F12}、{7F13}、{7F14}。{7F05}",
        "            in the 0x039E block family, alongside",
        "            {7F24}「これを装備できるのは{7F05}.",
        "            Japanese enumerates with 、 and closes with 。. English needs a",
        "            conjunction before the final element, which requires knowing the",
        "            element count at render time.",
        "reference:  Phase 2 control code census; Phase 6 for the code counts.",
        "status:     OPEN",
        "",
        "## 2. Name slot in running text",
        "constraint: 0x7F12 substitutes a name inside running prose.",
        "evidence:   %d occurrences after dictionary expansion, counting every" % ctrl.get(0x7F12, 0),
        "            sub-block on the disc.",
        "            preceded by 　 31360 / {7F02} 16307 / の 11631",
        "            followed by で 14131 / 。 12002 / だ 9634",
        "            Genitive and copula constructions that do not survive a",
        "            word for word rendering.",
        "reference:  Phase 2 section E.",
        "status:     OPEN",
        "",
        "## 3. Line metrics",
        "constraint: glyph cell advance is 8 px, body 6 px, column 7 is drop shadow.",
        "evidence:   Phase 3b per column intensity across the 13 known capitals.",
        "            Column 0 empty on 11 of 13. Column 7 carries the shadow of",
        "            column 6. Bottom row is the shadow of the row above.",
        "            The per line character budget is UNKNOWN until the renderer",
        "            is understood.",
        "reference:  FORMAT.md section 8, gate 17.",
        "status:     OPEN",
    ]


def manifest(out_dir, nids, total_chars, str_lengths, variants):
    files = []
    for root, _, names in os.walk(out_dir):
        for n in sorted(names):
            if n.startswith("MANIFEST"):
                continue
            p = os.path.join(root, n)
            rel = os.path.relpath(p, out_dir).replace("\\", "/")
            with open(p, "rb") as f:
                files.append((rel, hashlib.sha256(f.read()).hexdigest()))
    files.sort()
    write(os.path.join(out_dir, "MANIFEST.sha256"),
          ["%s  %s" % (h, rel) for rel, h in files])
    roll = hashlib.sha256("\n".join("%s  %s" % (h, rel) for rel, h in files)
                          .encode("utf-8")).hexdigest()
    sl = sorted(str_lengths)
    md = [
        "# DQ4 corpus manifest",
        "",
        "Regenerate with:",
        "",
        "    python -m dq4.corpus --disc <path to .bin> --out <dir>",
        "",
        "## Roll-up hash",
        "",
        "    %s" % roll,
        "",
        "SHA-256 over the sorted per-file hashes in MANIFEST.sha256. If this value",
        "moves, the decoder changed. Diff before accepting a new one; never accept a",
        "moved hash by regenerating the expectation.",
        "",
        "## Totals",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| files | %d |" % len(files),
        "| distinct text ids | %d |" % nids,
        "| stored blocks | %d |" % (nids + len(variants)),
        "| strings | %d |" % len(str_lengths),
        "| displayed characters | %d |" % total_chars,
        "| characters per string, min | %d |" % (sl[0] if sl else 0),
        "| characters per string, median | %d |" % (sl[len(sl) // 2] if sl else 0),
        "| characters per string, mean | %.1f |" % (sum(sl) / len(sl) if sl else 0),
        "| characters per string, max | %d |" % (sl[-1] if sl else 0),
        "| text ids with differing copies | %d |" % len(set(v[0] for v in variants)),
    ]
    write(os.path.join(out_dir, "MANIFEST.md"), md)
    return roll, len(files)


def main(argv=None):
    ap = argparse.ArgumentParser(description="regenerate the DQ4 decoded corpus")
    ap.add_argument("--disc", required=True, help="path to the DQ4 (Japan) .bin disc image")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)
    roll, nfiles, nids, chars, sl, variants, nside, nph = build(args.disc, args.out)
    sl = sorted(sl)
    print("corpus written to %s" % args.out)
    print("  files                 %d" % nfiles)
    print("  distinct text ids     %d" % nids)
    print("  strings               %d" % len(sl))
    print("  displayed characters  %d" % chars)
    print("  chars per string      min=%d median=%d mean=%.1f max=%d"
          % (sl[0], sl[len(sl) // 2], sum(sl) / len(sl), sl[-1]))
    print("  side-by-side records  %d" % nside)
    print("  placeholder strings   %d" % nph)
    print("  ids with differing copies %d" % len(set(v[0] for v in variants)))
    for tid, vi, sector, idx, dg in variants[:10]:
        print("     FINDING id %04X variant %d at sector %d sub %d (%s)"
              % (tid, vi, sector, idx, dg))
    print("\n  ROLL-UP %s" % roll)
    if roll != ROLLUP_EXPECTED:
        print("  expected %s" % ROLLUP_EXPECTED)
        print("  roll-up does not match the value stored in the library.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
