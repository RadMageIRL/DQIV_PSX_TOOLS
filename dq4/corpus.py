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
from . import mips, referrers

# Baseline roll-up. Stored in the LIBRARY, not in the corpus, so the corpus
# cannot silently update its own expectation. If a library change moves this,
# diff the corpus and review before accepting a new value.
ROLLUP_EXPECTED = "dad99a93d87b200855e924cdf9295e2871d6d1f3fe0f88344375f3647b3a223a"
EXE_ROLLUP_EXPECTED = "fea89bdaa08b339cf381cbc3afbfb1ca3411381d76d4ea8a5a0a369833b443d2"

DUMMY_MARK = "ダミー"          # katakana damii
DUMMY, EMPTY, UNRESOLVED = "DUMMY", "EMPTY", "UNRESOLVED"

# Phase 12 did not establish ordinal addressing for any string, so there is no
# ORDINAL status. Everything with no measured referrer is UNRESOLVED, which
# covers both "reached by position" and "referrer not yet found" without
# guessing the split.
STATUS_ORDER = (referrers.LOOKUP, referrers.TABLE, referrers.ROSTER,
                UNRESOLVED, EMPTY, DUMMY)


def string_status(refs, tid, i, nchar, is_dummy):
    """(status, ' (where)') for one string."""
    if is_dummy:
        return DUMMY, ""
    if not nchar:
        return EMPTY, ""
    got = refs.get((tid, i))
    if not got:
        return UNRESOLVED, ""
    for system in (referrers.LOOKUP, referrers.TABLE, referrers.ROSTER):
        here = [w for sysname, w in got if sysname == system]
        if here:
            extra = "" if len(got) == 1 else ", %d refs" % len(got)
            return system, " (%s%s)" % (here[0], extra)
    return UNRESOLVED, ""

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
    index = referrers.block_index(arch, blocks)
    refs = referrers.build(arch, blocks, index)

    variants = []
    dup_by_name = {}
    side_rows = []
    block_rows = []
    placeholders = []
    ph_cross = collections.Counter()
    chars_clean = [0]
    chars_blocked = [0]
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

            exp_lines = [raw_lines[0], raw_lines[1]]
            rendered = []
            for i, st in enumerate(b.exp_strings):
                text = render(st)
                exp_lines.append("[%02d] %s" % (i, text))
                nchar = sum(1 for k, v in st if k == huffman.SJIS)
                total_chars += nchar
                str_lengths.append(nchar)
                rendered.append((i, st, text, nchar))
            if b.exp_tail:
                exp_lines.append("[tail] %s" % render(b.exp_tail))
            write(os.path.join(out_dir, "expanded", name + ".txt"), exp_lines)

            # A block is DUMMY when every non-empty string carries the ダミー
            # marker. That rule selects 181 ids with no false positives, which
            # is the set the phase reports use.
            body = [t for _i, _st, t, n in rendered if n]
            is_dummy = bool(body) and all(DUMMY_MARK in t for t in body)

            # Bit budget. A string's encoded length is the span from its start
            # offset to the next END inclusive. Offsets are absolute from the
            # block base, so this span is exactly the room a re-encoding has.
            offs = huffman.string_offsets(b.tb)
            region_bits = (b.tb.e - b.tb.c) * 8
            consumed_bits = offs[-1]
            residue_bits = region_bits - consumed_bits
            strbits = [offs[n + 1] - offs[n] for n in range(len(offs) - 1)]
            if sum(strbits) + residue_bits != region_bits:
                raise SystemExit("bit budget arithmetic failed for id %04X" % tid)

            counts = collections.Counter()
            rows = []
            for i, st, text, nchar in rendered:
                status, where = string_status(refs, tid, i, nchar, is_dummy)
                counts[status] += 1
                rows.append((i, text, nchar, status, where, st,
                             strbits[i] if i < len(strbits) else 0))
            blocked = any(st == UNRESOLVED for _i, _t, n, st, _w, _s, _b in rows if n)
            edit = "BLOCKED" if blocked else "CLEAN"
            # "wholly unreferenced" means the block HAS non-empty strings and none
            # of them is referenced. A block with nothing but empty strings is a
            # different case and is not counted here, which is the definition the
            # phase reports use.
            # Read this off the referrer map, not the status column: DUMMY takes
            # precedence in the status field, so a dummy block that does contain a
            # referenced string would otherwise be misreported as wholly
            # unreferenced. Two blocks are in exactly that position.
            ne_rows = [r for r in rows if r[2]]
            wholly = bool(ne_rows) and not any(refs.get((tid, r[0])) for r in ne_rows)
            block_rows.append((tid, suffix, sector, sub, b, counts, edit,
                               wholly, is_dummy, region_bits, consumed_bits,
                               residue_bits))

            for i, text, nchar, status, where, st, nbits in rows:
                head = ("[id %04X / str %02d / sector %d / sub %d]"
                        % (tid, i, sector, sub["idx"]))
                side_rows.append((0 if edit == "CLEAN" else 1, tid, i, [
                    head,
                    "STATUS: %s%s  BLOCK: %s" % (status, where, edit),
                    "BITS: %d%s" % (nbits, ""
                                    if not nchar else
                                    "  (%.2f per displayed character)" % (nbits / nchar)),
                    "JP: %s" % text, "EN:", "NOTE:", ""]))
                if edit == "CLEAN":
                    chars_clean[0] += nchar
                else:
                    chars_blocked[0] += nchar
                if any(k == huffman.CTRL and v in CTRL_RANGE_SUB for k, v in st):
                    placeholders.append(head)
                    placeholders.append("STATUS: %s  BLOCK: %s" % (status, edit))
                    placeholders.append(text)
                    placeholders.append("")
                    ph_cross[edit] += 1

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
            dup_by_name[name] = dups

    index_lines = [
        "# per-block editability. A block is CLEAN when every non-empty string has a",
        "# measured referrer, BLOCKED when at least one is UNRESOLVED.",
        "#",
        "# Bit offsets are absolute from the block base, so changing one string's",
        "# encoded length shifts every later string in the same block. That is why the",
        "# unit of safety is the block and not the string.",
        "#",
        "#",
        "# Bit budget: region bits is (e - c) * 8, the whole code stream. consumed is",
        "# the span to the last END. residue is what follows it, trailing symbols plus",
        "# pad. sum of per-string bits + residue == region, exactly, for every block.",
        "#",
        "# text id | sector | sub | type | dlen | symbols | strings | non-empty"
        " | LOOKUP | TABLE | ROSTER | UNRESOLVED | EMPTY | DUMMY"
        " | region bits | consumed bits | residue bits | editability"
        " | wholly unreferenced | duplicate sectors",
    ]
    for (tid, suffix, sector, sub, b, counts, edit, wholly, is_dummy,
         region_bits, consumed_bits, residue_bits) in block_rows:
        name = "%04X%s" % (tid, suffix)
        ne = sum(v for k, v in counts.items() if k not in (EMPTY,))
        index_lines.append(
            "%04X%s | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d"
            " | %d | %d | %d | %s | %s | %s"
            % (tid, suffix, sector, sub["idx"], sub["type"], sub["dlen"],
               len(b.symbols), len(b.raw_strings), ne,
               counts.get(referrers.LOOKUP, 0), counts.get(referrers.TABLE, 0),
               counts.get(referrers.ROSTER, 0), counts.get(UNRESOLVED, 0),
               counts.get(EMPTY, 0), counts.get(DUMMY, 0),
               region_bits, consumed_bits, residue_bits,
               edit, "yes" if wholly else "no", dup_by_name.get(name, "-")))
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

    side = ["# CLEAN blocks first, then text id, then string index, so the safely",
            "# editable material comes first. STATUS is the measured referrer for this",
            "# string; BLOCK is whether its block can be re-encoded at all.",
            "#",
            "# UNRESOLVED means no referrer was found. Phase 12 did not establish",
            "# ordinal addressing for any string, so there is no ORDINAL status and",
            "# UNRESOLVED covers both possibilities without guessing the split.",
            ""]
    for _rank, _tid, _i, lines in sorted(side_rows, key=lambda r: (r[0], r[1], r[2])):
        side.extend(lines)
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

    # ------------------------------------------------------------------ exe
    # Kept in its own subtree so the two source media never mix silently. The
    # archive roll-up keeps exactly the meaning it had; the executable gets a
    # second figure of its own.
    exe_stats = {"blocks": 0, "strings": 0, "chars": 0, "referenced": 0}
    exe_index_lines = [
        "# text blocks embedded in SLPM_869.16, located by the six-u32 header",
        "# signature (c == 24, plausible a, e zero or inside a).",
        "#",
        "# These are NOT in the archive and are NOT covered by the archive roll-up.",
        "#",
        "# va | text id | a | c | d | e | f6 | symbols | strings | referenced"
        " | dictionary | records",
    ]
    if exe:
        load, _entry, tsize, toff = mips.exe_mapping(exe)
        eblocks = referrers.exe_blocks(exe, load, toff, tsize)
        eindex = {}
        for va, tb in eblocks:
            offs = huffman.string_offsets(tb)
            eindex[tb.id] = (tb, offs, {o: i for i, o in enumerate(offs)})
        erefs = referrers.exe_refs(exe, load, toff, tsize, eindex)
        for va, tb in eblocks:
            tree = huffman.HuffmanTree(tb)
            syms = tree.decode()
            entries = dictionary.parse(tb.raw, tb)
            expanded, _unres = dictionary.expand(syms, entries)
            rstr, rtail = huffman.split_strings(syms)
            estr, etail = huffman.split_strings(expanded)
            nm = "%04X" % tb.id
            head = ["# exe text block id %04X at va 0x%08X" % (tb.id, va),
                    "# symbols %d strings %d" % (len(syms), len(rstr))]
            rl = list(head)
            for i2, stx in enumerate(rstr):
                rl.append("[%02d] %s" % (i2, render(stx)))
            if rtail:
                rl.append("[tail] %s" % render(rtail))
            write(os.path.join(out_dir, "exe", "raw", nm + ".txt"), rl)
            el = list(head)
            nch = 0
            for i2, stx in enumerate(estr):
                el.append("[%02d] %s" % (i2, render(stx)))
                nch += sum(1 for k, _v in stx if k == huffman.SJIS)
            if etail:
                el.append("[tail] %s" % render(etail))
            write(os.path.join(out_dir, "exe", "expanded", nm + ".txt"), el)
            nref = sum(1 for (t, _i) in erefs if t == tb.id)
            exe_stats["blocks"] += 1
            exe_stats["strings"] += len(rstr)
            exe_stats["chars"] += nch
            exe_stats["referenced"] += nref
            exe_index_lines.append(
                "0x%08X | %04X | %d | %d | %d | %d | %d | %d | %d | %d | %s | %s"
                % (va, tb.id, tb.a, tb.c, tb.d, tb.e, tb.f6, len(syms), len(rstr),
                   nref, "yes" if tb.f6 else "no", "yes" if tb.d else "no"))
    write(os.path.join(out_dir, "exe", "blockindex.txt"), exe_index_lines)

    status_totals = collections.Counter()
    for row in block_rows:
        counts = row[5]
        status_totals.update(counts)
    clean = sum(1 for r in block_rows if r[6] == "CLEAN")
    clean_nd = sum(1 for r in block_rows if r[6] == "CLEAN" and not r[8])
    total_nd = sum(1 for r in block_rows if not r[8])

    rollup, exe_rollup, nfiles = manifest(out_dir, len(by_id), total_chars, str_lengths, variants,
                              status_totals, clean, clean_nd, total_nd,
                              chars_clean[0], chars_blocked[0], ph_cross, exe_stats)
    return dict(rollup=rollup, exe_rollup=exe_rollup, nfiles=nfiles, nids=len(by_id), chars=total_chars,
                lengths=str_lengths, variants=variants,
                records=len(side_rows), placeholders=len(placeholders) // 4,
                status=status_totals, clean=clean, clean_nd=clean_nd,
                total_nd=total_nd, chars_clean=chars_clean[0],
                chars_blocked=chars_blocked[0], ph_cross=ph_cross, exe=exe_stats,
                blocks=block_rows)


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
        "",
        "## 4. String offsets are absolute within a block",
        "constraint: a string is addressed by its BIT OFFSET from the block base,",
        "            not by its index. Changing any string's encoded length shifts",
        "            every later string in the same block, and every referrer to",
        "            them must be rewritten. A block may only be re-encoded if all",
        "            of its non-empty strings have a known referrer: that is the",
        "            CLEAN flag in meta/blockindex.txt.",
        "evidence:   the resolver at 0x8008F280 computes byte = block + (value >> 3)",
        "            and bit = value & 7. Gated at 9371 of 9371 tail records on a",
        "            string start, with plus and minus one bit at 0.00 percent.",
        "reference:  FORMAT.md sections 12 to 14, gates 30 to 32.",
        "status:     OPEN",
        "",
        "## Not added: the ordinal constraint",
        "",
        "A constraint was proposed reading: ordinal-addressed strings are selected by",
        "position, so their index and count must be preserved exactly.",
        "",
        "It is NOT recorded here, because its precondition failed. Phase 12 searched",
        "for an ordinal walker and did not find one, and the content evidence that",
        "suggested ordinal addressing (place names in 0x0020, person types in 0x0026)",
        "turned out to be referenced by type 44 pointer tables after all. No string on",
        "this disc is established as ordinal-addressed.",
        "",
        "Constraint 4 above is the stronger and measured statement, and it already",
        "forbids reordering in any block that is not CLEAN. If ordinal addressing is",
        "ever established, this section is where the constraint goes.",
    ]


def manifest(out_dir, nids, total_chars, str_lengths, variants,
             status, clean, clean_nd, total_nd, chars_clean, chars_blocked,
             ph_cross, exe_stats):
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

    # Two roll-ups, deliberately. The archive roll-up must keep exactly the
    # meaning it had, so exe/ is excluded from it: a moved archive hash then
    # still means "the archive decode changed" and nothing else.
    def _roll(rows):
        joined = "\n".join("%s  %s" % (h, rel) for rel, h in rows)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    arch_files = [r for r in files if not r[0].startswith("exe/")]
    exe_files = [r for r in files if r[0].startswith("exe/")]
    roll = _roll(arch_files)
    exe_roll = _roll(exe_files) if exe_files else ""
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
        "SHA-256 over the sorted per-file hashes in MANIFEST.sha256, EXCLUDING",
        "exe/. If this value moves, the archive decode changed. Diff before accepting",
        "a new one; never accept a moved hash by regenerating the expectation.",
        "",
        "The executable-resident blocks carry their own roll-up, so that the two",
        "source media never mix into one number:",
        "",
        "    %s" % exe_roll,
        "",
        "SHA-256 over the exe/ rows of MANIFEST.sha256 alone.",
        "",
        "## Totals",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| files | %d |" % len(files),
        "| files under exe/ | %d |" % len(exe_files),
        "| distinct text ids | %d |" % nids,
        "| stored blocks | %d |" % (nids + len(variants)),
        "| strings | %d |" % len(str_lengths),
        "| displayed characters | %d |" % total_chars,
        "| characters per string, min | %d |" % (sl[0] if sl else 0),
        "| characters per string, median | %d |" % (sl[len(sl) // 2] if sl else 0),
        "| characters per string, mean | %.1f |" % (sum(sl) / len(sl) if sl else 0),
        "| characters per string, max | %d |" % (sl[-1] if sl else 0),
        "| text ids with differing copies | %d |" % len(set(v[0] for v in variants)),
        "",
        "## Referrer status, per string",
        "",
        "Measured only. Every LOOKUP, TABLE and ROSTER entry was gated: the reference",
        "must land exactly on a string start, and a one-bit shift in either direction",
        "must destroy the match.",
        "",
        "**There is no ORDINAL status.** Phase 12 looked for an ordinal walker and did",
        "not find one, and the content evidence that suggested ordinal addressing turned",
        "out to be type 44 pointers. So UNRESOLVED covers both \"reached by position\"",
        "and \"referrer not yet found\", and the split is not guessed.",
        "",
        "| Status | Strings | Meaning |",
        "|---|---:|---|",
        "| LOOKUP | %d | tail record table, Phase 10 |" % status.get("LOOKUP", 0),
        "| TABLE | %d | type 26 record field, Phase 11 and 12 |" % status.get("TABLE", 0),
        "| ROSTER | %d | type 44 roster table, Phase 12 |" % status.get("ROSTER", 0),
        "| UNRESOLVED | %d | no measured referrer |" % status.get(UNRESOLVED, 0),
        "| EMPTY | %d | zero displayed characters |" % status.get(EMPTY, 0),
        "| DUMMY | %d | in a block whose every non-empty string is a dummy |"
        % status.get(DUMMY, 0),
        "",
        "## Editability, per block",
        "",
        "Bit offsets are absolute from the block base, so changing one string's encoded",
        "length shifts every later string in the same block. The unit of safety is the",
        "block, not the string.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| blocks CLEAN, all blocks | %d |" % clean,
        "| **blocks CLEAN, excluding dummy blocks** | **%d of %d** |" % (clean_nd, total_nd),
        "| displayed characters in CLEAN blocks | **%d** |" % chars_clean,
        "| displayed characters in BLOCKED blocks | %d |" % chars_blocked,
        "| substitution-bearing strings in CLEAN blocks | %d |" % ph_cross.get("CLEAN", 0),
        "| substitution-bearing strings in BLOCKED blocks | %d |" % ph_cross.get("BLOCKED", 0),
        "",
        "## Executable-resident blocks",
        "",
        "Held in `exe/`, deliberately outside the archive subtree and outside the",
        "roll-up above, so a moved archive hash keeps exactly one meaning.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| blocks | %d |" % exe_stats["blocks"],
        "| strings | %d |" % exe_stats["strings"],
        "| displayed characters | %d |" % exe_stats["chars"],
        "| strings with a measured referrer | %d |" % exe_stats["referenced"],
        "",
        "Combined with the archive: %d strings, %d displayed characters."
        % (len(str_lengths) + exe_stats["strings"], total_chars + exe_stats["chars"]),
    ]
    write(os.path.join(out_dir, "MANIFEST.md"), md)
    return roll, exe_roll, len(files)


def main(argv=None):
    ap = argparse.ArgumentParser(description="regenerate the DQ4 decoded corpus")
    ap.add_argument("--disc", required=True, help="path to the DQ4 (Japan) .bin disc image")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)
    r = build(args.disc, args.out)
    sl = sorted(r["lengths"])
    print("corpus written to %s" % args.out)
    print("  files                 %d" % r["nfiles"])
    print("  distinct text ids     %d" % r["nids"])
    print("  strings               %d" % len(sl))
    print("  displayed characters  %d" % r["chars"])
    print("  chars per string      min=%d median=%d mean=%.1f max=%d"
          % (sl[0], sl[len(sl) // 2], sum(sl) / len(sl), sl[-1]))
    print("  side-by-side records  %d" % r["records"])
    print("  placeholder strings   %d" % r["placeholders"])
    print("  ids with differing copies %d" % len(set(v[0] for v in r["variants"])))
    for tid, vi, sector, idx, dg in r["variants"][:10]:
        print("     FINDING id %04X variant %d at sector %d sub %d (%s)"
              % (tid, vi, sector, idx, dg))
    print("  status  " + "  ".join("%s=%d" % (k, r["status"].get(k, 0))
                                   for k in STATUS_ORDER))
    print("  blocks CLEAN          %d of %d non-dummy" % (r["clean_nd"], r["total_nd"]))
    print("  characters CLEAN      %d   BLOCKED %d"
          % (r["chars_clean"], r["chars_blocked"]))
    print("  exe blocks            %d, %d strings, %d characters, %d referenced"
          % (r["exe"]["blocks"], r["exe"]["strings"], r["exe"]["chars"],
             r["exe"]["referenced"]))
    print("")
    print("  ROLL-UP     %s" % r["rollup"])
    print("  EXE ROLL-UP %s" % r["exe_rollup"])
    if EXE_ROLLUP_EXPECTED and r["exe_rollup"] != EXE_ROLLUP_EXPECTED:
        print("  exe roll-up does not match the value stored in the library.")
    if r["rollup"] != ROLLUP_EXPECTED:
        print("  expected %s" % ROLLUP_EXPECTED)
        print("  roll-up does not match the value stored in the library.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
