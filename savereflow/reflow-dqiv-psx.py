#!/usr/bin/env python3
"""reflow-dqiv-psx - reflow the text fields of a Dragon Quest IV (PSX) save.

WHAT IT IS FOR
--------------
A translation patch renames things. A save written before a rename keeps the old
words, so a player carrying a save across builds sees a mix of old and new text
with no way to reconcile it. This tool rewrites the text fields that a DQ4 save
actually stores, using glossary files you supply, and recomputes the checksums
the game validates on load.

You supply the memory card and the glossaries. Nothing about any particular
translation is built into this file.

WHAT IT WRITES
--------------
Two kinds of field, and only these two:

  * the 12-byte party-record NAME field, 6 fullwidth characters, zero padded,
    for each of the 24 party records the save holds;
  * the 20-byte PLACE field in the save's Title Frame, 10 fullwidth characters,
    padded with the fullwidth space 0x8140, which is what the slot list shows.

WHAT IT CANNOT DO
-----------------
It cannot fix a field the game does not populate from the save. A save holds the
name field verbatim; the game copies it out of the card and displays it, so
rewriting it works. Anything the game materializes from the disc at run time is
out of reach of a save editor by construction and is not attempted here.

ZEROING IS NOT A SUBSTITUTE FOR WRITING. The game's record initializer skips its
name copy when the field is already non-empty, which invites the idea that
blanking a field makes the game refill it from its own character table. On this
engine the initializer is only reached when a record is ALLOCATED, and allocation
only picks a record whose character id is zero. A record restored from a save has
a non-zero id, so nothing re-runs the initializer over it and a blanked field
stays blank. The tool therefore writes names; it does not blank them.

CHECKSUMS
---------
The save block is checked in two independent places and this tool maintains both:

  * Title Frame, block+0x00..0x7F: byte 0x7F is the 8-bit XOR of bytes
    0x00..0x7E. The game compares it and, on mismatch, replaces the whole title
    with its own "broken log" string.
  * Data frames, block+0x180 onward in 128-byte steps: the trailing u32 at
    frame+0x7C, little endian, is CRC-32/BZIP2 over frame+0x00..0x7B - that is
    polynomial 0x04C11DB7, MSB first, init 0xFFFFFFFF, xorout 0xFFFFFFFF, input
    and output NOT reflected. The loader checks every frame the block's present
    map marks as present and refuses the save on the first mismatch.

SAFETY POSTURE
--------------
Dry run by default. --apply backs up first, verifies the backup by hash, writes,
then re-reads the written file and re-runs the whole checksum audit over it
before reporting success. --restore puts the backup back and proves it by hash.
Any field whose current contents the tool cannot account for is skipped and
named, never guessed at.
"""

import argparse
import hashlib
import os
import shutil
import sys

# ------------------------------------------------------------------ constants

BLOCK_SIZE = 0x2000
FRAME_SIZE = 0x80
CARD_SIZE = 16 * BLOCK_SIZE
N_BLOCKS = 16              # block 0 is the directory, blocks 1..15 hold saves

# The save body is an image of a fixed RAM region, cut into 124-byte chunks with
# a 4-byte CRC appended to each. Chunk i lives in frame 3+i of the block.
CHUNK_DATA = 124
FIRST_DATA_FRAME = 3
N_CHUNKS = 40
SAVE_RAM_BASE = 0x80010000

# Party records, as laid out inside that RAM region.
RECORD_BASE = 0x80010550
RECORD_STRIDE = 0x48
RECORD_NAME_OFF = 0x24
RECORD_NAME_LEN = 12
N_RECORDS = 24

# Title Frame.
TITLE_MAGIC = b"SC"
TITLE_XOR_OFF = 0x7F
PLACE_OFF = 0x28
PLACE_LEN = 20

# Directory frame block-allocation states that mean "this block holds a save the
# game will list". 0x51 is an in-use first block. 0xA1 is a deleted first block:
# its bytes survive and are worth reflowing, but the game does not show it.
STATE_IN_USE = 0x51
STATE_DELETED = 0xA1

FW_SPACE = b"\x81\x40"

# ------------------------------------------------------------------- checksums

_CRC_TABLE = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ (0x04C11DB7 if _c & 0x80000000 else 0)) & 0xFFFFFFFF
    _CRC_TABLE.append(_c)


def crc32_bzip2(data):
    """CRC-32/BZIP2 over data. This is the algorithm the game's loader uses."""
    c = 0xFFFFFFFF
    for b in data:
        c = ((c << 8) ^ _CRC_TABLE[((c >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return c ^ 0xFFFFFFFF


def title_xor(frame):
    """8-bit XOR over the first 127 bytes of a Title Frame."""
    v = 0
    for b in frame[:TITLE_XOR_OFF]:
        v ^= b
    return v


# ------------------------------------------------------- fullwidth Shift-JIS

def _fw_tables():
    enc = {}
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        enc[ch] = 0x8260 + i
    for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
        enc[ch] = 0x8281 + i
    for i, ch in enumerate("0123456789"):
        enc[ch] = 0x824F + i
    enc[" "] = 0x8140
    enc["."] = 0x8144
    enc[","] = 0x8143
    enc["'"] = 0x8166
    return enc


FW_ENC = _fw_tables()
FW_TO_ASCII = {}
for _ch, _code in FW_ENC.items():
    FW_TO_ASCII[bytes(_code.to_bytes(2, "big")).decode("shift_jis")] = _ch


def normalize_key(text):
    """Fold fullwidth Latin back to ASCII, for glossary lookup only.

    A save that already carries a previous build's English carries it in
    FULLWIDTH, because that is the only form the game's field holds. A glossary
    writes its English column in ASCII. Without this fold the English-to-English
    leg of a reflow never matches and every already-translated field is reported
    as unaccounted for, which is a false refusal, not a safe one.
    """
    return "".join(FW_TO_ASCII.get(c, c) for c in text)


class FieldError(Exception):
    """Raised when a field's bytes cannot be accounted for. Never suppressed."""


def encode_fullwidth(text):
    """ASCII text to fullwidth Shift-JIS. Raises on anything not in the table."""
    out = bytearray()
    for ch in text:
        if ch not in FW_ENC:
            raise FieldError("no fullwidth form for %r in %r" % (ch, text))
        out += FW_ENC[ch].to_bytes(2, "big")
    return bytes(out)


def decode_sjis_pairs(raw):
    """Decode a field of whole 2-byte Shift-JIS characters.

    Raises FieldError rather than returning something plausible. A field that is
    not made of whole two-byte characters is a field this tool does not
    understand, and the caller must skip it.
    """
    if len(raw) % 2:
        raise FieldError("odd length %d" % len(raw))
    for i in range(0, len(raw), 2):
        hi = raw[i]
        if not (0x81 <= hi <= 0x9F or 0xE0 <= hi <= 0xEF):
            raise FieldError("byte 0x%02X at +%d is not a Shift-JIS lead byte"
                             % (hi, i))
    try:
        return raw.decode("shift_jis")
    except UnicodeDecodeError as exc:
        raise FieldError("not decodable as Shift-JIS: %s" % exc)


# ------------------------------------------------------------------- glossary

def parse_glossary(path, jp_col=1, en_col=2):
    """Read a `field | field | ...` glossary. Returns {source_text: english}.

    Columns are 1-based and are named by the caller, because real glossaries put
    the two columns in different places. Comments run from '#' to end of line.
    Both the Japanese column AND the English column become keys, so a field that
    already holds a previous build's English is recognized and can be reflowed
    to the current one.
    """
    out = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.split("#", 1)[0]
            if "|" not in line:
                continue
            cols = [c.strip() for c in line.split("|")]
            if len(cols) < max(jp_col, en_col):
                continue
            jp = cols[jp_col - 1]
            en = cols[en_col - 1]
            if not jp or not en:
                continue
            for key in (jp, en):
                prev = out.get(key)
                if prev is not None and prev != en:
                    raise FieldError(
                        "%s:%d: %r maps to both %r and %r"
                        % (path, lineno, key, prev, en))
                out[key] = en
    return out


def parse_glossary_arg(arg):
    """PATH, PATH:JPCOL:ENCOL, or PATH:JPCOL:ENCOL on a Windows path."""
    parts = arg.rsplit(":", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return parts[0], int(parts[1]), int(parts[2])
    return arg, 1, 2


# ------------------------------------------------------------- card structure

def ram_to_card(addr):
    """RAM address inside the save region to (frame, offset_in_frame)."""
    off = addr - SAVE_RAM_BASE
    if off < 0:
        raise FieldError("0x%08X is below the save region" % addr)
    chunk, j = divmod(off, CHUNK_DATA)
    if chunk >= N_CHUNKS:
        raise FieldError("0x%08X is past the save region" % addr)
    return FIRST_DATA_FRAME + chunk, j


def ram_span_to_card(addr, length):
    """A RAM run to the list of (card_offset, nbytes) pieces that carry it.

    124 is not a multiple of the field widths, so a field CAN straddle a chunk
    boundary and land in two frames. That is not a corner case to refuse, it is
    a case to carry: both frames then need resealing.
    """
    pieces = []
    remaining = length
    while remaining:
        frame, j = ram_to_card(addr)
        take = min(remaining, CHUNK_DATA - j)
        pieces.append((frame * FRAME_SIZE + j, take))
        addr += take
        remaining -= take
    return pieces


def record_name_site(index):
    """(chunks, pieces, length) for party record `index`'s name field."""
    addr = RECORD_BASE + RECORD_STRIDE * index + RECORD_NAME_OFF
    pieces = ram_span_to_card(addr, RECORD_NAME_LEN)
    chunks = [off // FRAME_SIZE - FIRST_DATA_FRAME for off, _ in pieces]
    return chunks, pieces, RECORD_NAME_LEN


class Card(object):
    def __init__(self, data, path=None):
        if len(data) != CARD_SIZE:
            raise FieldError("expected %d bytes, got %d" % (CARD_SIZE, len(data)))
        self.data = bytearray(data)
        self.path = path

    @classmethod
    def read(cls, path):
        with open(path, "rb") as fh:
            return cls(fh.read(), path)

    def block(self, n):
        return self.data[n * BLOCK_SIZE:(n + 1) * BLOCK_SIZE]

    def dir_state(self, n):
        return self.data[n * FRAME_SIZE]

    def dir_name(self, n):
        raw = self.data[n * FRAME_SIZE + 10:n * FRAME_SIZE + 30]
        return bytes(raw).split(b"\x00")[0].decode("ascii", "replace")

    def frame_off(self, block, frame):
        return block * BLOCK_SIZE + frame * FRAME_SIZE

    def frame(self, block, frame):
        o = self.frame_off(block, frame)
        return bytes(self.data[o:o + FRAME_SIZE])

    def has_title(self, block):
        return self.frame(block, 0)[:2] == TITLE_MAGIC

    def present_map(self, block):
        """The 40-bit present-chunk map the loader keys on, from chunk 0."""
        o = self.frame_off(block, FIRST_DATA_FRAME)
        w0 = int.from_bytes(self.data[o:o + 4], "little")
        w1 = int.from_bytes(self.data[o + 4:o + 8], "little")
        return [i for i in range(N_CHUNKS)
                if ((w0, w1)[i // 32] >> (i % 32)) & 1]

    # ---------------------------------------------------------------- auditing

    def audit(self):
        """Every checksum in the card. Returns (rows, n_ok, n_bad)."""
        rows = []
        ok = bad = 0
        for b in range(1, N_BLOCKS):
            if not self.has_title(b):
                rows.append((b, "title", "absent", None, None))
                continue
            tf = self.frame(b, 0)
            good = title_xor(tf) == tf[TITLE_XOR_OFF]
            rows.append((b, "title", "ok" if good else "MISMATCH",
                         tf[TITLE_XOR_OFF], title_xor(tf)))
            ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
            for chunk in self.present_map(b):
                f = FIRST_DATA_FRAME + chunk
                fr = self.frame(b, f)
                stored = int.from_bytes(fr[CHUNK_DATA:], "little")
                calc = crc32_bzip2(fr[:CHUNK_DATA])
                good = stored == calc
                rows.append((b, "frame %d" % f,
                             "ok" if good else "MISMATCH", stored, calc))
                ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
        return rows, ok, bad

    # ---------------------------------------------------------------- writing

    def set_bytes(self, offset, new):
        self.data[offset:offset + len(new)] = new

    def reseal_frame(self, block, frame):
        o = self.frame_off(block, frame)
        crc = crc32_bzip2(bytes(self.data[o:o + CHUNK_DATA]))
        self.data[o + CHUNK_DATA:o + FRAME_SIZE] = crc.to_bytes(4, "little")
        return crc

    def reseal_title(self, block):
        o = self.frame_off(block, 0)
        v = title_xor(bytes(self.data[o:o + FRAME_SIZE]))
        self.data[o + TITLE_XOR_OFF] = v
        return v


# ------------------------------------------------------------------- planning

class Edit(object):
    """One field change, as one or more contiguous card writes.

    A field can straddle a 124-byte chunk boundary and land in two frames, so a
    single logical edit is carried as a list of (offset, old, new) pieces.
    """

    def __init__(self, block, kind, label, pieces):
        self.block = block
        self.kind = kind          # "party" | "place" | "crc" | "titlexor"
        self.label = label
        self.pieces = pieces

    def lines(self):
        out = []
        for n, (off, old, new) in enumerate(self.pieces):
            tag = self.label if n == 0 else self.label + " (cont)"
            out.append("block %2d  %-8s %-22s 0x%05X  %-42s -> %s"
                       % (self.block, self.kind, tag, off, old.hex(), new.hex()))
        return out

    def frames(self):
        return {(off % BLOCK_SIZE) // FRAME_SIZE for off, _, _ in self.pieces}


def _lookup(gloss, text):
    hit = gloss.get(text)
    if hit is None:
        hit = gloss.get(normalize_key(text))
    return hit


def plan_block(card, block, gloss, do_party=True, do_place=True):
    """Return (edits, skips) for one block. Never writes."""
    edits = []
    skips = []
    if not card.has_title(block):
        skips.append((block, "block", "no SC title frame, not a save"))
        return edits, skips
    present = set(card.present_map(block))

    if do_place:
        off = block * BLOCK_SIZE + PLACE_OFF
        raw = bytes(card.data[off:off + PLACE_LEN])
        try:
            text = decode_sjis_pairs(raw)
        except FieldError as exc:
            skips.append((block, "place", str(exc)))
        else:
            cur = text.rstrip("　")
            if not cur:
                skips.append((block, "place", "empty"))
            else:
                want = _lookup(gloss, cur)
                if want is None:
                    skips.append((block, "place",
                                  "no glossary row for %r" % cur))
                else:
                    try:
                        enc = encode_fullwidth(want)
                    except FieldError as exc:
                        skips.append((block, "place", str(exc)))
                        enc = None
                    if enc is not None:
                        if len(enc) > PLACE_LEN:
                            skips.append((block, "place",
                                          "%r needs %d bytes, field is %d"
                                          % (want, len(enc), PLACE_LEN)))
                        else:
                            new = enc + FW_SPACE * ((PLACE_LEN - len(enc)) // 2)
                            if new != raw:
                                edits.append(Edit(block, "place", cur,
                                                  [(off, raw, new)]))

    if do_party:
        for i in range(N_RECORDS):
            try:
                chunks, pieces, ln = record_name_site(i)
            except FieldError as exc:
                skips.append((block, "record %d" % i, str(exc)))
                continue
            if any(c not in present for c in chunks):
                continue                     # the save does not carry this chunk
            base = block * BLOCK_SIZE
            raw = b"".join(bytes(card.data[base + o:base + o + n])
                           for o, n in pieces)
            if raw[0] == 0:
                continue                     # empty record, nothing to reflow
            term = raw.find(b"\x00")
            if term < 0:
                body, pad = raw, b""
            else:
                body, pad = raw[:term], raw[term:]
            if pad and set(pad) != {0}:
                skips.append((block, "record %d" % i,
                              "field is not name-plus-zero-pad: %s" % raw.hex()))
                continue
            try:
                cur = decode_sjis_pairs(body)
            except FieldError as exc:
                skips.append((block, "record %d" % i, str(exc)))
                continue
            want = _lookup(gloss, cur)
            if want is None:
                skips.append((block, "record %d" % i,
                              "no glossary row for %r" % cur))
                continue
            try:
                enc = encode_fullwidth(want)
            except FieldError as exc:
                skips.append((block, "record %d" % i, str(exc)))
                continue
            if len(enc) > ln:
                skips.append((block, "record %d" % i,
                              "%r needs %d bytes, field is %d"
                              % (want, len(enc), ln)))
                continue
            new = enc + b"\x00" * (ln - len(enc))
            if new != raw:
                out = []
                pos = 0
                for o, n in pieces:
                    out.append((base + o, raw[pos:pos + n], new[pos:pos + n]))
                    pos += n
                edits.append(Edit(block, "party", cur, out))

    return edits, skips


def build_plan(card, gloss, do_party=True, do_place=True):
    all_edits = []
    all_skips = []
    for b in range(1, N_BLOCKS):
        e, s = plan_block(card, b, gloss, do_party, do_place)
        all_edits.extend(e)
        all_skips.extend(s)
    return all_edits, all_skips


def apply_plan(card, edits):
    """Apply data edits, then reseal every affected frame and title. In place."""
    frames = set()
    titles = set()
    for e in edits:
        for off, _old, new in e.pieces:
            card.set_bytes(off, new)
        if e.kind == "place":
            titles.add(e.block)
        else:
            for f in e.frames():
                frames.add((e.block, f))
    seals = []
    for block, frame in sorted(frames):
        o = card.frame_off(block, frame)
        old = bytes(card.data[o + CHUNK_DATA:o + FRAME_SIZE])
        crc = card.reseal_frame(block, frame)
        seals.append(Edit(block, "crc", "frame %d" % frame,
                          [(o + CHUNK_DATA, old, crc.to_bytes(4, "little"))]))
    for block in sorted(titles):
        o = card.frame_off(block, 0)
        old = bytes(card.data[o + TITLE_XOR_OFF:o + TITLE_XOR_OFF + 1])
        v = card.reseal_title(block)
        seals.append(Edit(block, "titlexor", "title",
                          [(o + TITLE_XOR_OFF, old, bytes([v]))]))
    return seals


# ----------------------------------------------------------------------- CLI

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def default_backup(card_path):
    return card_path + ".reflow-backup"


def do_restore(args):
    backup = args.backup or default_backup(args.card)
    if not os.path.exists(backup):
        print("no backup at %s" % backup)
        return 2
    before = sha256_file(backup)
    print("backup   %s\n  sha256 %s" % (backup, before))
    shutil.copyfile(backup, args.card)
    after = sha256_file(args.card)
    print("restored %s\n  sha256 %s" % (args.card, after))
    if after != before:
        print("RESTORE FAILED: hashes differ")
        return 1
    print("restore verified: card is byte-identical to the backup")
    return 0


def do_verify(card):
    rows, ok, bad = card.audit()
    for b, what, status, stored, calc in rows:
        if status != "ok":
            if stored is None:
                print("  block %2d %-10s %s" % (b, what, status))
            else:
                print("  block %2d %-10s %s stored=0x%08X computed=0x%08X"
                      % (b, what, status, stored, calc))
    print("checksums reproduced: %d   failures: %d" % (ok, bad))
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="reflow-dqiv-psx",
        description="Reflow the text fields of a Dragon Quest IV (PSX) memory "
                    "card save and recompute its checksums.")
    p.add_argument("card", help="path to a 128 KB .mcd memory card image")
    p.add_argument("--glossary", action="append", default=[], metavar="SPEC",
                   help="glossary file, PATH or PATH:JPCOL:ENCOL "
                        "(1-based columns, default 1 and 2). Repeatable.")
    p.add_argument("--rename", action="append", default=[], metavar="OLD=NEW",
                   help="explicit remap for a value no glossary row accounts "
                        "for. Repeatable.")
    p.add_argument("--apply", action="store_true",
                   help="write the plan. Without it the tool only prints it.")
    p.add_argument("--restore", action="store_true",
                   help="put the backup back and verify it by hash")
    p.add_argument("--verify", action="store_true",
                   help="audit the card's checksums and stop")
    p.add_argument("--backup", metavar="PATH",
                   help="backup path (default: CARD.reflow-backup)")
    p.add_argument("--force-backup", action="store_true",
                   help="allow overwriting an existing backup")
    p.add_argument("--no-party", action="store_true",
                   help="leave party-record name fields alone")
    p.add_argument("--no-place", action="store_true",
                   help="leave Title Frame place fields alone")
    args = p.parse_args(argv)

    if args.restore:
        return do_restore(args)

    print("card     %s" % args.card)
    print("  sha256 %s" % sha256_file(args.card))
    card = Card.read(args.card)

    print("\n=== checksum audit, before ===")
    bad = do_verify(card)
    if args.verify:
        return 1 if bad else 0
    if bad:
        print("\nREFUSING: the card does not validate as it stands. Reflowing a "
              "card whose checksums already fail would hide the real problem.")
        return 1

    gloss = {}
    for spec in args.glossary:
        path, jc, ec = parse_glossary_arg(spec)
        g = parse_glossary(path, jc, ec)
        print("\nglossary %s (jp col %d, en col %d): %d keys"
              % (path, jc, ec, len(g)))
        for k, v in g.items():
            if k in gloss and gloss[k] != v:
                print("  CONFLICT: %r -> %r and %r; refusing" % (k, gloss[k], v))
                return 1
            gloss[k] = v
    for r in args.rename:
        if "=" not in r:
            print("bad --rename %r, expected OLD=NEW" % r)
            return 1
        k, v = r.split("=", 1)
        gloss[k.strip()] = v.strip()
    if not gloss:
        print("\nno glossary supplied: nothing to reflow. Pass --glossary.")
        return 1

    edits, skips = build_plan(card, gloss,
                              do_party=not args.no_party,
                              do_place=not args.no_place)

    print("\n=== plan: %d field edits ===" % len(edits))
    for e in edits:
        for line in e.lines():
            print("  " + line)

    work = Card(bytes(card.data), card.path)
    seals = apply_plan(work, edits)
    print("\n=== plan: %d checksum rewrites ===" % len(seals))
    for e in seals:
        for line in e.lines():
            print("  " + line)

    print("\n=== skipped, %d ===" % len(skips))
    for b, what, why in skips:
        print("  block %2d %-12s %s" % (b, what, why))

    if not args.apply:
        print("\nDRY RUN. Nothing was written. Pass --apply to write.")
        return 0

    if not edits:
        print("\nnothing to write.")
        return 0

    backup = args.backup or default_backup(args.card)
    if os.path.exists(backup) and not args.force_backup:
        print("\nREFUSING: backup already exists at %s. Move it, or pass "
              "--force-backup." % backup)
        return 1
    src = sha256_file(args.card)
    shutil.copyfile(args.card, backup)
    dst = sha256_file(backup)
    print("\nbackup   %s\n  sha256 %s" % (backup, dst))
    if src != dst:
        print("BACKUP FAILED: hashes differ. Nothing written.")
        return 1
    print("backup verified.")

    with open(args.card, "wb") as fh:
        fh.write(bytes(work.data))
    print("wrote    %s\n  sha256 %s" % (args.card, sha256_file(args.card)))

    reread = Card.read(args.card)
    if bytes(reread.data) != bytes(work.data):
        print("READ-BACK FAILED: the file on disk is not what was written.")
        return 1
    print("\n=== checksum audit, after ===")
    bad = do_verify(reread)
    if bad:
        print("\nTHE WRITTEN CARD DOES NOT VALIDATE. Restore it with --restore.")
        return 1
    print("\nOK. %d fields reflowed, %d checksums rewritten, and the written "
          "file passes the same audit the game's loader performs."
          % (len(edits), len(seals)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
