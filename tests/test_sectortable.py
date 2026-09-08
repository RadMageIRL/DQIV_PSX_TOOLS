"""Tests for dq4.sectortable, the level sector table and its build invariant.

Every test here builds its own table and its own block map. NONE of them reads
a disc, for the same reason test_splitimm.py does not: the shipped game sets the
flag on two of 3,283 entries and relocates nothing, so the shipped game cannot
falsify a claim about writing. Fabricated tables can.

WHAT THIS FILE IS REALLY GUARDING. The module decoded the length as twelve bits
until 2026-08-29. Reads were unaffected, because on every entry that names a
block the flag is clear and the two decodes agree. A WRITE was not safe. So the
tests that matter most are not the ones asserting a good table passes; they are
the five mutants, each of which corrupts a table in one specific way and must be
refused, and the two pairs at the bottom that reproduce holes the mutants found
in check_table itself.

Those last two pairs are the point of the file. A gate that has only ever seen
good data is not a gate, and both holes were found by a mutant rather than by
review:

  * check_table() handed one executable as both base and build cannot notice a
    flag missing from BOTH sides. `expect_flagged` closes it.
  * check 5 without `base_blocks` cannot notice a relocation whose table entry
    was never rewritten. The entry looks non-live on both sides and slips
    through.

Run: python -m unittest discover -s tests -t .
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dq4 import sectortable as st                               # noqa: E402


# ------------------------------------------------------------ the fixture

EXE_LEN = 0x200
START = 0x100
COUNT = 6
END = START + 4 * (COUNT - 1)
BASE = 100                    # a fabricated archive LBA base, not DQ4's

# sector -> nsec. Three real blocks, deliberately not adjacent.
BLOCK_NSEC = {0: 4, 10: 2, 20: 8}

# index -> (sector, nsec) for the entries that name a block. Index 3 and 4 point
# into a band with no block header, and index 5 carries the flag and is not a
# sector pointer at all.
LIVE = {0: (0, 4), 1: (10, 2), 2: (20, 8)}
NO_BLOCK_SECTOR = 900
FLAGGED_INDEX = 5


def blocks(nsec_by_sector=None, text_at=(0, 10, 20)):
    """A block map shaped like hbd.scan_blocks() output.

    Each block carries one text sub-block sitting 16 bytes into its first
    sector, which is inside every extent that declares the block's own length.
    """
    nsec_by_sector = BLOCK_NSEC if nsec_by_sector is None else nsec_by_sector
    out = {}
    for sec, nsec in nsec_by_sector.items():
        subs = []
        if sec in text_at:
            subs.append({"idx": 0, "type": 40, "off": sec * 2048 + 16,
                         "dlen": 64})
        out[sec] = {"nsec": nsec, "subs": subs}
    return out


def exe(words=None):
    """A buffer with the table at START and a distinct word on each boundary."""
    buf = bytearray(EXE_LEN)
    struct.pack_into("<I", buf, START - 4, 0xDEADBEEF)
    struct.pack_into("<I", buf, END + 4, 0xFEEDFACE)
    for i, v in enumerate(clean_words() if words is None else words):
        struct.pack_into("<I", buf, START + 4 * i, v)
    return bytes(buf)


def clean_words():
    out = []
    for i in range(COUNT):
        if i in LIVE:
            sec, nsec = LIVE[i]
            out.append(st.pack(nsec, sec + BASE))
        elif i == FLAGGED_INDEX:
            out.append(st.FLAG_BIT | 0x00102448)
        else:
            out.append(st.pack(1, NO_BLOCK_SECTOR + BASE))
    return out


def mutate(index, word):
    w = clean_words()
    w[index] = word
    return exe(w)


def check(built, built_blocks=None, base=None, **kw):
    kw.setdefault("start", START)
    kw.setdefault("end", END)
    kw.setdefault("base", BASE)
    return st.check_table(exe() if base is None else base, built,
                          blocks() if built_blocks is None else built_blocks,
                          **kw)


def failed(report):
    return set(c.name for c in report.failures)


# ------------------------------------------------------------ field layout

class TestPackUnpack(unittest.TestCase):

    def test_round_trip_without_the_flag(self):
        v = st.pack(4, 100)
        self.assertEqual(st.unpack(v), (4, 100))
        self.assertEqual(st.flag(v), 0)

    def test_round_trip_with_the_flag(self):
        v = st.pack(4, 100, 1)
        self.assertEqual(st.unpack(v), (4, 100))
        self.assertEqual(st.flag(v), 1)

    def test_the_flag_is_not_folded_into_the_length(self):
        """The whole defect in one assertion."""
        self.assertEqual(st.unpack(st.pack(4, 100, 1))[0],
                         st.unpack(st.pack(4, 100, 0))[0])

    def test_pack_raises_rather_than_truncating(self):
        self.assertRaises(ValueError, st.pack, st.LEN_MASK + 1, 100)
        self.assertRaises(ValueError, st.pack, 4, st.LBA_MASK + 1)
        self.assertRaises(ValueError, st.pack, 4, 100, 2)

    def test_the_fields_tile_thirty_two_bits(self):
        span = st.LEN_MASK << st.LEN_SHIFT
        self.assertEqual(span & st.LBA_MASK, 0)
        self.assertEqual(span & st.FLAG_BIT, 0)
        self.assertEqual(span | st.LBA_MASK | st.FLAG_BIT, 0xFFFFFFFF)


class TestRepack(unittest.TestCase):
    """repack() exists to carry the flag across a rewrite. Prove that it does."""

    def test_identity_on_an_unflagged_word(self):
        v = st.pack(4, 100)
        self.assertEqual(st.repack(v), v)

    def test_identity_on_a_flagged_word(self):
        v = st.pack(4, 100, 1)
        self.assertEqual(st.repack(v), v)

    def test_relocating_a_flagged_word_keeps_the_flag(self):
        v = st.pack(4, 100, 1)
        moved = st.repack(v, lba=700)
        self.assertEqual(st.unpack(moved), (4, 700))
        self.assertEqual(st.flag(moved), 1)

    def test_the_hand_assembled_form_is_the_bug(self):
        """`length << 20 | lba` is what a caller writes when it does not know
        about bit 31. It is wrong on exactly the flagged words, which is why it
        survived every read this library ever did."""
        v = st.pack(4, 100, 1)
        hand = (4 << st.LEN_SHIFT) | 700
        self.assertNotEqual(hand, st.repack(v, lba=700))
        self.assertEqual(st.flag(hand), 0)


class TestTwelveBitDecodeDisagreement(unittest.TestCase):
    """The old decode and the new one differ on precisely the flagged words.

    This is the reason no measurement taken under the twelve-bit form was
    retracted, and it is worth a test rather than a sentence in a docstring.
    """

    def old_length(self, v):
        return (v >> st.LEN_SHIFT) & 0xFFF

    def test_they_agree_when_the_flag_is_clear(self):
        for length in (0, 1, 4, 0x7FF):
            v = st.pack(length, 100)
            self.assertEqual(self.old_length(v), st.unpack(v)[0])

    def test_they_disagree_by_exactly_the_flag_when_it_is_set(self):
        for length in (0, 1, 4, 0x7FF):
            v = st.pack(length, 100, 1)
            self.assertEqual(self.old_length(v), st.unpack(v)[0] + 0x800)


# ------------------------------------------------------------ the reader

class TestLiveEntries(unittest.TestCase):

    def test_a_flagged_word_is_not_a_sector_pointer(self):
        offs = [e.offset
                for e in st.live_entries(exe(), blocks(), START, END, BASE)]
        self.assertNotIn(START + 4 * FLAGGED_INDEX, offs)

    def test_an_entry_naming_no_block_is_not_live(self):
        live = st.live_entries(exe(), blocks(), START, END, BASE)
        self.assertEqual(len(live), len(LIVE))
        self.assertEqual(sorted(e.archive_sector for e in live),
                         sorted(sec for sec, _ in LIVE.values()))

    def test_entries_still_unpack_five_ways(self):
        """Existing callers destructure positionally. That must keep working."""
        row = st.entries(exe(), START, END, BASE)[0]
        offset, raw, length, lba, sector = row
        self.assertEqual((length, lba, sector), (4, BASE, 0))
        self.assertEqual(raw, struct.unpack_from("<I", exe(), offset)[0])
        self.assertEqual(row.flag, 0)


# ------------------------------------------------------------ the mutants

class TestCheckTableMutants(unittest.TestCase):
    """One positive control and five negative controls.

    The positive control is load-bearing. A suite asserting that five broken
    tables are refused passes just as well when check_table refuses everything.
    """

    def test_p0_the_clean_table_passes(self):
        rep = check(exe())
        self.assertTrue(rep.ok, "\n".join(rep.lines()))
        self.assertEqual(len(rep.checks), 5)

    def test_m1_a_dropped_flag_is_refused(self):
        """Bit 31 cleared exactly the way the twelve-bit encoder cleared it."""
        w = clean_words()
        rep = check(mutate(FLAGGED_INDEX, w[FLAGGED_INDEX] & ~st.FLAG_BIT))
        self.assertFalse(rep.ok)
        self.assertIn("2 flag preservation", failed(rep))

    def test_m2_a_truncated_length_is_refused(self):
        sec, nsec = LIVE[2]
        rep = check(mutate(2, st.pack(nsec - 1, sec + BASE)))
        self.assertFalse(rep.ok)
        self.assertIn("4 text reach", failed(rep))

    def test_m3_an_overlapping_extent_is_refused(self):
        """Entry 0 stretched from four sectors to twelve runs into sector 10."""
        sec, _ = LIVE[0]
        rep = check(mutate(0, st.pack(12, sec + BASE)))
        self.assertFalse(rep.ok)
        self.assertIn("3 no overlap", failed(rep))

    def test_m4_a_regressed_decoder_is_refused(self):
        """The mutation is in the MODULE, not the data. A round trip through a
        broken decoder is the identity, so a data-only check 1 would pass on
        any table forever."""
        saved = st.LEN_MASK
        try:
            st.LEN_MASK = 0xFFF
            rep = check(exe())
            self.assertFalse(rep.ok)
            self.assertIn("1 round trip", failed(rep))
        finally:
            st.LEN_MASK = saved
        self.assertTrue(check(exe()).ok, "the module was left mutated")

    def test_m5_an_entry_pointed_at_no_block_is_refused(self):
        rep = check(mutate(2, st.pack(8, NO_BLOCK_SECTOR + BASE)))
        self.assertFalse(rep.ok)
        self.assertIn("5 entry count", failed(rep))

    def test_a_changed_boundary_word_is_refused(self):
        buf = bytearray(exe())
        struct.pack_into("<I", buf, END + 4, 0x0BADF00D)
        rep = check(bytes(buf))
        self.assertFalse(rep.ok)
        self.assertIn("5 entry count", failed(rep))


# ------------------------------------------------------------ the two holes

class TestTheHolesTheMutantsFound(unittest.TestCase):
    """Both of these passed a self-consistent gate and should not have.

    Neither was caught by reading check_table. Each was caught by a mutant that
    the gate was supposed to refuse and did not. The pair of tests for each hole
    is deliberate: the first reproduces the hole, the second proves the argument
    that closes it actually closes it.
    """

    def test_a_flag_dropped_from_both_sides_slips_past_a_self_comparison(self):
        """THE HOLE. verify.py is handed ONE image and uses it as base and
        build, so check 2 compares the flag against itself and can never see it
        missing from both."""
        w = clean_words()
        broken = mutate(FLAGGED_INDEX, w[FLAGGED_INDEX] & ~st.FLAG_BIT)
        rep = st.check_table(broken, broken, blocks(),
                             start=START, end=END, base=BASE)
        self.assertNotIn("2 flag preservation", failed(rep),
                         "the hole is supposed to be reproducible here")

    def test_expect_flagged_closes_it(self):
        """THE FIX. Hand check 2 the shipped game's own figure instead of the
        image's, and the same input is refused."""
        w = clean_words()
        broken = mutate(FLAGGED_INDEX, w[FLAGGED_INDEX] & ~st.FLAG_BIT)
        rep = st.check_table(broken, broken, blocks(),
                             start=START, end=END, base=BASE,
                             expect_flagged=(FLAGGED_INDEX,))
        self.assertFalse(rep.ok)
        self.assertIn("2 flag preservation", failed(rep))

    def moved_archive(self):
        """A block relocated from sector 20 to sector 30, with the entry that
        names it never rewritten. The archive is right and the table is stale."""
        return blocks({0: 4, 10: 2, 30: 8}, text_at=(0, 10))

    def test_a_missed_relocation_slips_past_check_5_without_base_blocks(self):
        """THE SECOND HOLE. Check 5 resolves the BASE entries against the BUILT
        archive, so the stale entry looks non-live on both sides."""
        rep = st.check_table(exe(), exe(), self.moved_archive(),
                             start=START, end=END, base=BASE,
                             expect_flagged=(FLAGGED_INDEX,))
        self.assertNotIn("5 entry count", failed(rep),
                         "the hole is supposed to be reproducible here")

    def test_base_blocks_closes_it(self):
        """THE FIX. Resolve the base entries against the archive the build
        STARTED from. The entry named a block before and names none now."""
        rep = st.check_table(exe(), exe(), self.moved_archive(),
                             start=START, end=END, base=BASE,
                             expect_flagged=(FLAGGED_INDEX,),
                             base_blocks=blocks())
        self.assertFalse(rep.ok)
        self.assertIn("5 entry count", failed(rep))


if __name__ == "__main__":
    unittest.main()
