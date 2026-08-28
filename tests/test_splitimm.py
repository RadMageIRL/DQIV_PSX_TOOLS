"""Tests for dq4.splitimm, the split-immediate reference recognizer.

Every test here builds its own instruction words. NONE of them reads a disc, by
design and not by convenience: rule 44 of docs/CODEX.md says a fixed-width
assumption cannot be found by testing with the data the author had, and the same
argument applies to a recognizer. The shipped game exercises a narrow slice of
the forms this module claims to handle, so the shipped game cannot falsify the
claim. Fabricated input can.

The negative controls in here are load-bearing. A test that asserts a scanner
returns zero on unrelated bytes passes just as well when the scanner is broken
and returns zero on everything, so each one is paired with a planted site that
the same assertions must find.

Run: python -m unittest discover -s tests -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dq4 import splitimm                                        # noqa: E402
from dq4.splitimm import ADDIU, ORI, ORPHAN, SPLIT              # noqa: E402


# ------------------------------------------------------------ word assembly

def lui(rt, imm):
    return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)


def ori(rt, rs, imm):
    return (0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def addiu(rt, rs, imm):
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def lw(rt, rs, off=0):
    return (0x23 << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def addu(rd, rs, rt):
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21


def jal(target=0x100):
    return (0x03 << 26) | (target >> 2)


def jr(rs=31):
    return (rs << 21) | 0x08


def sw(rt, rs, off=0):
    return (0x2B << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)


NOP = 0


def image(words):
    import struct
    return struct.pack("<%dI" % len(words), *[w & 0xFFFFFFFF for w in words])


# A value that is a plausible packed reference: id 0x048C, bit offset 0xA88F.
TID = 0x048C
OFFSET = 0xA88F
VALUE = (TID << 20) | OFFSET
STARTS = frozenset((OFFSET, 0x0000, 0x1234))


def scan(words, **kw):
    return splitimm.find_word_refs(image(words), TID, STARTS, **kw)


# ------------------------------------------------------------------- compose

class TestCompose(unittest.TestCase):

    def test_ori_zero_extends(self):
        self.assertEqual(splitimm.compose(0x048C, 0xA88F, ORI), 0x048CA88F)

    def test_addiu_sign_extends_when_bit_15_set(self):
        # THE DEFECT THE WIDENED FORM EXISTS TO FIX. Reading this pair with the
        # ori rule gives 0x048CA88F. The machine computes 0x048B, one less in
        # the high half, because 0xA88F sign-extends negative.
        self.assertEqual(splitimm.compose(0x048C, 0xA88F, ADDIU), 0x048BA88F)
        self.assertNotEqual(splitimm.compose(0x048C, 0xA88F, ADDIU),
                            splitimm.compose(0x048C, 0xA88F, ORI))

    def test_addiu_matches_ori_when_bit_15_clear(self):
        # And this is why an ori-only recognizer looks correct for a long time.
        for lo in (0x0000, 0x0001, 0x1234, 0x7FFF):
            self.assertEqual(splitimm.compose(0x048C, lo, ADDIU),
                             splitimm.compose(0x048C, lo, ORI))

    def test_bad_opcode_raises(self):
        with self.assertRaises(ValueError):
            splitimm.compose(0, 0, 0x0C)     # andi is not a low half
        with self.assertRaises(ValueError):
            splitimm.halves(0, 0x0C)


class TestHalvesRoundTrip(unittest.TestCase):
    """compose(*halves(v, op), op) == v, for both opcodes, over the boundaries.

    A property test over the value, not an example test over the values this
    project happens to use. The addiu carry only shows up when bit 15 is set, so
    an example set drawn from the shipped corpus would very likely miss it.
    """

    def _sweep(self):
        vals = []
        for hi in (0x0000, 0x0001, 0x048B, 0x048C, 0x7FFF, 0x8000, 0xFFFF):
            for lo in (0x0000, 0x0001, 0x7FFE, 0x7FFF, 0x8000, 0x8001,
                       0xA88F, 0xFFFE, 0xFFFF):
                vals.append((hi << 16) | lo)
        return vals

    def test_round_trip_ori(self):
        for v in self._sweep():
            hi, lo = splitimm.halves(v, ORI)
            self.assertEqual(splitimm.compose(hi, lo, ORI), v, hex(v))

    def test_round_trip_addiu(self):
        for v in self._sweep():
            hi, lo = splitimm.halves(v, ADDIU)
            self.assertEqual(splitimm.compose(hi, lo, ADDIU), v, hex(v))

    def test_addiu_high_half_carries(self):
        # halves() for addiu must NOT be `value >> 16`. If it were, this value
        # would be stored as 0x048C/0xA88F and would read back as 0x048BA88F.
        hi, lo = splitimm.halves(0x048CA88F, ADDIU)
        self.assertEqual((hi, lo), (0x048D, 0xA88F))
        self.assertNotEqual(hi, 0x048CA88F >> 16)

    def test_ori_and_addiu_disagree_on_what_to_store(self):
        self.assertNotEqual(splitimm.halves(0x048CA88F, ORI),
                            splitimm.halves(0x048CA88F, ADDIU))


# ------------------------------------------------------------------- writes

class TestWritesModel(unittest.TestCase):

    def test_control_transfer_writes_nothing_except_jal(self):
        self.assertIsNone(splitimm.writes(jr(31)))
        self.assertEqual(splitimm.writes(jal()), 31)

    def test_nop_writes_register_zero_and_that_is_the_honest_answer(self):
        # `nop` IS `sll zero,zero,0`, so the model reports a write to $zero
        # rather than no write at all. Reporting None here would be a nicer
        # looking answer and a less true one. It costs nothing: $zero is
        # hardwired, so no pending `lui` can ever be sitting in it.
        self.assertEqual(splitimm.writes(NOP), 0)

    def test_a_run_of_nops_does_not_end_a_pending_pair(self):
        # The consequence of the line above, measured rather than argued.
        hi, lo = splitimm.halves(VALUE, ORI)
        self.assertEqual(len(scan([lui(16, hi)] + [NOP] * 20
                                  + [ori(16, 16, lo)])), 1)

    def test_stores_write_nothing(self):
        self.assertIsNone(splitimm.writes(sw(16, 4)))

    def test_loads_and_arithmetic_write_rt_and_rd(self):
        self.assertEqual(splitimm.writes(lw(16, 4)), 16)
        self.assertEqual(splitimm.writes(ori(9, 8, 1)), 9)
        self.assertEqual(splitimm.writes(lui(9, 1)), 9)
        self.assertEqual(splitimm.writes(addu(16, 2, 0)), 16)

    def test_branches_write_nothing_but_the_linking_forms_write_ra(self):
        beq = (0x04 << 26) | (4 << 21) | (5 << 16) | 3
        self.assertIsNone(splitimm.writes(beq))
        bgezal = (0x01 << 26) | (4 << 21) | (0x11 << 16) | 3
        self.assertEqual(splitimm.writes(bgezal), 31)


# ------------------------------------------------------------- the SPLIT form

class TestSplitForm(unittest.TestCase):

    def test_finds_adjacent_lui_ori(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        got = scan([lui(16, hi), ori(16, 16, lo)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].form, SPLIT)
        self.assertEqual(got[0].value, VALUE)
        self.assertEqual(got[0].lo_op, ORI)
        self.assertEqual(got[0].hi_off, 0)
        self.assertEqual(got[0].lo_off, 4)
        self.assertEqual(got[0].reg, 16)

    def test_finds_adjacent_lui_addiu(self):
        # THE FORM AN ori-ONLY RECOGNIZER CANNOT SEE. Same composed value, and
        # the stored high half differs, which is why it cannot be found by
        # looking for the ori pair's bytes either.
        hi, lo = splitimm.halves(VALUE, ADDIU)
        got = scan([lui(16, hi), addiu(16, 16, lo)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].value, VALUE)
        self.assertEqual(got[0].lo_op, ADDIU)

    def test_negative_control_the_ori_reading_of_an_addiu_pair_is_rejected(self):
        # Plant an addiu pair whose halves were computed with the ORI rule. The
        # machine composes 0x10000 less, which is not a valid reference, so this
        # must NOT be reported. If it is, compose() is not opcode aware.
        hi, lo = splitimm.halves(VALUE, ORI)
        self.assertEqual(scan([lui(16, hi), addiu(16, 16, lo)]), [])
        # And the control can fail: with the right halves the same shape is found.
        hi, lo = splitimm.halves(VALUE, ADDIU)
        self.assertEqual(len(scan([lui(16, hi), addiu(16, 16, lo)])), 1)

    def test_survives_unrelated_instructions_between_the_halves(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi)] + [addu(8, 2, 3)] * 10 + [ori(16, 16, lo)]
        self.assertEqual(len(scan(words)), 1)

    def test_low_half_must_use_the_same_register_for_source_and_target(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        # ori s0, s1, lo builds a value in s0 from s1, not from the lui's s0.
        self.assertEqual(scan([lui(16, hi), ori(16, 17, lo)]), [])

    def test_offsets_are_shifted_by_base(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        got = scan([lui(16, hi), ori(16, 16, lo)], base=0x8000)
        self.assertEqual((got[0].hi_off, got[0].lo_off), (0x8000, 0x8004))


class TestClobberModel(unittest.TestCase):
    """The fifteen invented pairs, in miniature.

    An earlier scanner paired a `lui` with an `ori` across a register clobber and
    across a jump. The composed value it recorded is not the value the code
    computes. These are the two disassembled shapes that defeated it.
    """

    def test_rejects_a_pair_crossing_a_write_to_the_register(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi), addu(16, 2, 0)] + [NOP] * 5 + [ori(16, 16, lo)]
        self.assertEqual(scan(words), [])

    def test_rejects_a_pair_crossing_a_load_into_the_register(self):
        # lui s0,hi ; lw s0,0(a0) ; ... ; ori s0,s0,lo
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi), lw(16, 4)] + [NOP] * 5 + [ori(16, 16, lo)]
        got = scan(words)
        self.assertTrue(all(s.form != SPLIT for s in got), got)

    def test_rejects_a_pair_crossing_a_jal(self):
        # lui a0,hi ; jal ... ; addu a0,v0,zero ; ... ; ori a0,a0,lo
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(4, hi), jal(), addu(4, 2, 0)] + [NOP] * 8 \
            + [ori(4, 4, lo)]
        self.assertEqual(scan(words), [])

    def test_the_clobber_control_can_fail(self):
        # Same distance, same shape, WITHOUT the clobber. If this did not find
        # the site, the three tests above would be passing for the wrong reason.
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(4, hi), jal(), NOP] + [NOP] * 8 + [ori(4, 4, lo)]
        self.assertEqual(len(scan(words)), 1)

    def test_a_second_lui_supersedes_the_first(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, 0x0BAD), lui(16, hi), ori(16, 16, lo)]
        got = scan(words)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].hi_off, 4)


class TestWindow(unittest.TestCase):

    def test_found_at_exactly_the_window_distance(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi)] + [NOP] * (splitimm.WINDOW - 1) \
            + [ori(16, 16, lo)]
        self.assertEqual(len(scan(words)), 1)

    def test_missed_one_instruction_beyond_the_window(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi)] + [NOP] * splitimm.WINDOW + [ori(16, 16, lo)]
        self.assertEqual(scan(words), [])

    def test_a_window_of_eight_misses_what_thirty_two_finds(self):
        # The 6,905-of-8,818 result, reproduced as a unit test. The misses sat
        # 12 and 15 instructions after their lui.
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi)] + [NOP] * 11 + [ori(16, 16, lo)]
        self.assertEqual(len(scan(words, window=32)), 1)
        self.assertEqual(scan(words, window=8), [])


# ------------------------------------------------------------ the ORPHAN form

class TestOrphanForm(unittest.TestCase):

    def test_finds_ori_after_a_load(self):
        # lw s0,0(a0) ; ori s0,s0,0xA88F. The id comes from memory and the
        # string offset IS the immediate.
        got = scan([lw(16, 4), ori(16, 16, OFFSET)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].form, ORPHAN)
        self.assertIsNone(got[0].hi_off)
        self.assertEqual(got[0].value, OFFSET)

    def test_requires_a_load_not_any_write(self):
        self.assertEqual(scan([addu(16, 2, 3), ori(16, 16, OFFSET)]), [])

    def test_requires_the_immediate_to_be_a_known_string_start(self):
        self.assertEqual(scan([lw(16, 4), ori(16, 16, 0x5555)]), [])

    def test_a_split_pair_is_not_also_counted_as_an_orphan(self):
        # The low half of a real pair must be claimed once. Double counting here
        # would inflate every population this scanner reports.
        hi, lo = splitimm.halves(VALUE, ORI)
        got = scan([lui(16, hi), ori(16, 16, lo)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].form, SPLIT)

    def test_a_clobbered_lui_does_not_become_an_orphan(self):
        # lui s0,hi ; lw s0,0(a0) ; ori s0,s0,OFFSET. The lui is dead, the load
        # is live, so this IS an orphan and must be reported as one. What must
        # not happen is it being reported as a SPLIT carrying the dead high half.
        hi = splitimm.halves(VALUE, ORI)[0]
        got = scan([lui(16, hi), lw(16, 4), ori(16, 16, OFFSET)])
        self.assertEqual([s.form for s in got], [ORPHAN])

    def test_a_missed_lui_is_not_laundered_into_an_orphan(self):
        # lui out of window, then ori with a valid low half. Reporting this as an
        # ORPHAN would convert a MISS into a finding and hide the miss.
        hi = splitimm.halves(VALUE, ORI)[0]
        words = [lui(16, hi)] + [NOP] * splitimm.WINDOW \
            + [ori(16, 16, OFFSET)]
        self.assertEqual(scan(words), [])

    def test_orphan_form_is_off_when_no_low_half_oracle_is_given(self):
        buf = image([lw(16, 4), ori(16, 16, OFFSET)])
        self.assertEqual(splitimm.find(buf, lambda v: True, None), [])
        # and the control can fail
        self.assertEqual(
            len(splitimm.find(buf, lambda v: True, lambda i: i in STARTS)), 1)


# ------------------------------------------------------- controls and scoring

class TestNegativeControlCanFail(unittest.TestCase):
    """Rule 1, in test form. A detector that returns zero has said nothing until
    it has been seen to return non-zero on the same harness."""

    NOISE = [addu(8, 9, 10), sw(8, 4), lw(9, 5), jr(31), NOP,
             ori(8, 9, 0x1111), lui(8, 0x2222), addu(3, 4, 5)] * 4

    def test_returns_zero_on_unrelated_code(self):
        self.assertEqual(scan(self.NOISE), [])

    def test_returns_non_zero_on_the_same_noise_with_one_site_planted(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = list(self.NOISE)
        words[10:10] = [lui(16, hi), ori(16, 16, lo)]
        got = scan(words)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].value, VALUE)


class TestPositiveControl(unittest.TestCase):

    def test_reports_a_fraction_and_the_missing_offsets(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        words = [lui(16, hi), ori(16, 16, lo), NOP,
                 lui(17, hi), ori(17, 17, lo)]
        buf = image(words)
        found, expected, missing = splitimm.positive_control(
            buf, TID, STARTS, known=(4, 16))
        self.assertEqual((found, expected, missing), (2, 2, []))

    def test_a_known_reference_the_scan_misses_is_named_not_hidden(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        buf = image([lui(16, hi), ori(16, 16, lo)])
        found, expected, missing = splitimm.positive_control(
            buf, TID, STARTS, known=(4, 0x400))
        self.assertEqual((found, expected), (1, 2))
        self.assertEqual(missing, [0x400])

    def test_an_empty_known_set_scores_zero_of_zero_and_not_pass(self):
        # The case a boolean conceals: a harness that handed the scanner nothing
        # looks identical to a scanner that recovered everything.
        buf = image([NOP])
        self.assertEqual(splitimm.positive_control(buf, TID, STARTS, known=()),
                         (0, 0, []))


class TestBufferEdges(unittest.TestCase):

    def test_trailing_bytes_that_do_not_fill_a_word_are_ignored(self):
        hi, lo = splitimm.halves(VALUE, ORI)
        buf = image([lui(16, hi), ori(16, 16, lo)]) + b"\xff\xff\xff"
        self.assertEqual(len(splitimm.find_word_refs(buf, TID, STARTS)), 1)

    def test_empty_buffer(self):
        self.assertEqual(splitimm.find_word_refs(b"", TID, STARTS), [])


if __name__ == "__main__":
    unittest.main()
