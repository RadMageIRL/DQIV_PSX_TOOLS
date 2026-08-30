"""Tests for reflow-dqiv-psx.

NOT ONE OF THESE READS A SAVE FILE. Every card in here is fabricated by
`make_card` below, for the reason the sibling repository's test modules already
give: the saves the author happens to own exercise a narrow slice of the shapes
the tool claims to handle, so those saves cannot falsify the claim.

THE MUTANTS ARE THE POINT. A checksum verifier that has only ever seen good data
is not a verifier; it passes just as well when it returns True unconditionally.
Every acceptance assertion in here is paired with a mutant that the same
assertion must REJECT, and the resealer is tested by disabling it and proving the
audit then fails.

Run: python -m unittest discover -s tests -t .
"""

import importlib.util
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL = os.path.join(os.path.dirname(_HERE), "reflow-dqiv-psx.py")
_spec = importlib.util.spec_from_file_location("reflow", _TOOL)
reflow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reflow)


# --------------------------------------------------------------- fabrication

def make_frame(payload):
    """A 128-byte data frame carrying `payload`, correctly sealed."""
    body = bytes(payload) + b"\x00" * (reflow.CHUNK_DATA - len(payload))
    assert len(body) == reflow.CHUNK_DATA
    return body + reflow.crc32_bzip2(body).to_bytes(4, "little")


def make_title(place=b"", name=b""):
    """A 128-byte Title Frame with `place` at +0x28, correctly sealed."""
    fr = bytearray(b"\xFF" * reflow.FRAME_SIZE)
    fr[0:2] = b"SC"
    fr[2] = 0x11
    fr[3] = 0x01
    fr[4:0x44] = reflow.FW_SPACE * 32
    fr[0x12:0x12 + len(name)] = name
    pad = reflow.PLACE_LEN - len(place)
    fr[reflow.PLACE_OFF:reflow.PLACE_OFF + reflow.PLACE_LEN] = (
        bytes(place) + reflow.FW_SPACE * (pad // 2))
    fr[0x7F] = 0
    fr[0x7F] = reflow.title_xor(bytes(fr))
    return bytes(fr)


def make_card(blocks):
    """blocks: {block_number: {"place": bytes, "records": {i: bytes}}}."""
    data = bytearray(b"\x00" * reflow.CARD_SIZE)
    # directory frame 0
    data[0:2] = b"MC"
    data[0x7F] = 0
    for b in range(1, reflow.N_BLOCKS):
        o = b * reflow.FRAME_SIZE
        data[o] = 0xA0
        data[o + 8:o + 10] = (0xFFFF).to_bytes(2, "little")
    for bn, spec in blocks.items():
        base = bn * reflow.BLOCK_SIZE
        data[base:base + reflow.BLOCK_SIZE] = b"\xFF" * reflow.BLOCK_SIZE
        # RAM image of the save region, then cut into chunks
        ram = bytearray(b"\x00" * (reflow.CHUNK_DATA * reflow.N_CHUNKS))
        for idx, name in spec.get("records", {}).items():
            off = (reflow.RECORD_BASE + reflow.RECORD_STRIDE * idx
                   + reflow.RECORD_NAME_OFF - reflow.SAVE_RAM_BASE)
            ram[off:off + reflow.RECORD_NAME_LEN] = (
                name + b"\x00" * (reflow.RECORD_NAME_LEN - len(name)))
        chunks = sorted(spec.get("chunks", range(reflow.N_CHUNKS)))
        w0 = w1 = 0
        for c in chunks:
            if c < 32:
                w0 |= 1 << c
            else:
                w1 |= 1 << (c - 32)
        ram[0:4] = w0.to_bytes(4, "little")
        ram[4:8] = w1.to_bytes(4, "little")
        data[base:base + reflow.FRAME_SIZE] = make_title(spec.get("place", b""))
        # icon frames 1 and 2 stay 0xFF; they are not checksummed
        for c in chunks:
            payload = ram[c * reflow.CHUNK_DATA:(c + 1) * reflow.CHUNK_DATA]
            o = base + (reflow.FIRST_DATA_FRAME + c) * reflow.FRAME_SIZE
            data[o:o + reflow.FRAME_SIZE] = make_frame(payload)
        data[bn * reflow.FRAME_SIZE] = 0x51
    return reflow.Card(bytes(data))


FW = reflow.encode_fullwidth
JP_ALPHA = "アルファ".encode("shift_jis")
JP_BRAVO = "ブラボ".encode("shift_jis")


# ------------------------------------------------------------------ checksums

class TestCrc(unittest.TestCase):
    def test_known_vector(self):
        # CRC-32/BZIP2 check value, the published one for this parameter set.
        self.assertEqual(reflow.crc32_bzip2(b"123456789"), 0xFC891918)

    def test_not_the_reflected_crc(self):
        # NEGATIVE CONTROL. If someone swaps in zlib.crc32 this must fail,
        # because the two agree on nothing.
        import zlib
        self.assertNotEqual(reflow.crc32_bzip2(b"123456789"),
                            zlib.crc32(b"123456789"))

    def test_empty(self):
        self.assertEqual(reflow.crc32_bzip2(b""), 0x00000000)

    def test_every_single_bit_changes_it(self):
        base = bytes(range(124))
        v = reflow.crc32_bzip2(base)
        for i in range(124):
            for bit in range(8):
                m = bytearray(base)
                m[i] ^= 1 << bit
                self.assertNotEqual(reflow.crc32_bzip2(bytes(m)), v,
                                    "bit %d of byte %d is invisible" % (bit, i))

    def test_title_xor(self):
        fr = bytearray(128)
        fr[3] = 0xAB
        fr[9] = 0x0F
        self.assertEqual(reflow.title_xor(bytes(fr)), 0xAB ^ 0x0F)
        fr[0x7F] = 0xFF          # the byte at 0x7F must NOT be included
        self.assertEqual(reflow.title_xor(bytes(fr)), 0xAB ^ 0x0F)


# ------------------------------------------------------------------- encoding

class TestEncoding(unittest.TestCase):
    def test_round_trip(self):
        for s in ("Sixchr", "Alpha", "Charli", "Echo", "Bravo", "Foxtrt",
                  "A B", "0123456789"):
            self.assertEqual(FW(s).decode("shift_jis"), "".join(
                chr(0xFF00 + ord(c) - 0x20) if c != " " else "\u3000"
                for c in s))
            self.assertEqual(reflow.normalize_key(FW(s).decode("shift_jis")), s)

    def test_refuses_unencodable(self):
        with self.assertRaises(reflow.FieldError):
            FW("Ragn\u00e1r")
        with self.assertRaises(reflow.FieldError):
            FW("a/b")

    def test_decode_refuses_odd_length(self):
        with self.assertRaises(reflow.FieldError):
            reflow.decode_sjis_pairs(b"\x82")

    def test_decode_refuses_halfwidth(self):
        with self.assertRaises(reflow.FieldError):
            reflow.decode_sjis_pairs(b"AB")

    def test_decode_accepts_fullwidth(self):
        self.assertEqual(reflow.decode_sjis_pairs(FW("Ab")), "\uff21\uff42")


# ------------------------------------------------------------------- glossary

class TestGlossary(unittest.TestCase):
    def _write(self, text):
        p = os.path.join(_HERE, "_tmp_gloss.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, p)
        return p

    def test_columns_and_comments(self):
        p = self._write("# a comment | with a pipe\n"
                        "7F20 | AAA | Delta | Golf\n"
                        "\n"
                        "7F21 | BBB | Alpha | Alpha  # trailing note\n")
        g = reflow.parse_glossary(p, 2, 4)
        self.assertEqual(g["AAA"], "Golf")
        self.assertEqual(g["Golf"], "Golf")
        self.assertEqual(g["BBB"], "Alpha")
        self.assertNotIn("Delta", g)

    def test_conflict_refused(self):
        p = self._write("X | One\nX | Two\n")
        with self.assertRaises(reflow.FieldError):
            reflow.parse_glossary(p, 1, 2)

    def test_arg_parsing(self):
        self.assertEqual(reflow.parse_glossary_arg("a/b.txt"), ("a/b.txt", 1, 2))
        self.assertEqual(reflow.parse_glossary_arg("a/b.txt:2:4"),
                         ("a/b.txt", 2, 4))
        self.assertEqual(reflow.parse_glossary_arg(r"C:\x\b.txt:2:4"),
                         (r"C:\x\b.txt", 2, 4))
        self.assertEqual(reflow.parse_glossary_arg(r"C:\x\b.txt"),
                         (r"C:\x\b.txt", 1, 2))


# -------------------------------------------------------------------- mapping

class TestMapping(unittest.TestCase):
    def test_chunk_zero_starts_at_frame_three(self):
        self.assertEqual(reflow.ram_to_card(reflow.SAVE_RAM_BASE), (3, 0))
        self.assertEqual(reflow.ram_to_card(reflow.SAVE_RAM_BASE + 123), (3, 123))
        self.assertEqual(reflow.ram_to_card(reflow.SAVE_RAM_BASE + 124), (4, 0))

    def test_refuses_outside_the_region(self):
        with self.assertRaises(reflow.FieldError):
            reflow.ram_to_card(reflow.SAVE_RAM_BASE - 1)
        with self.assertRaises(reflow.FieldError):
            reflow.ram_to_card(reflow.SAVE_RAM_BASE
                               + reflow.CHUNK_DATA * reflow.N_CHUNKS)

    def test_span_splits_at_a_chunk_boundary(self):
        # a field starting 4 bytes before the end of chunk 0
        pieces = reflow.ram_span_to_card(reflow.SAVE_RAM_BASE + 120, 12)
        self.assertEqual(pieces, [(3 * 128 + 120, 4), (4 * 128 + 0, 8)])

    def test_record_15_is_the_straddling_one(self):
        straddlers = [i for i in range(reflow.N_RECORDS)
                      if len(reflow.record_name_site(i)[1]) > 1]
        self.assertEqual(straddlers, [15])


# ---------------------------------------------------------------- the audit

class TestAudit(unittest.TestCase):
    def test_clean_card_passes(self):
        card = make_card({1: {"place": JP_BRAVO,
                              "records": {2: JP_ALPHA},
                              "chunks": [0, 12]}})
        _rows, ok, bad = card.audit()
        self.assertEqual(bad, 0)
        self.assertGreater(ok, 0)

    def test_mutating_a_data_byte_is_caught(self):
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        off = 1 * reflow.BLOCK_SIZE + (3 + 12) * reflow.FRAME_SIZE + 5
        card.data[off] ^= 0x01
        _rows, _ok, bad = card.audit()
        self.assertEqual(bad, 1)

    def test_mutating_the_title_is_caught(self):
        card = make_card({1: {"place": JP_BRAVO, "chunks": [0]}})
        card.data[1 * reflow.BLOCK_SIZE + reflow.PLACE_OFF] ^= 0x01
        _rows, _ok, bad = card.audit()
        self.assertEqual(bad, 1)

    def test_a_frame_outside_the_present_map_is_not_audited(self):
        # A stale frame with a deliberately wrong CRC. The loader never reads it,
        # so the audit must not report it, and this is the assertion that proves
        # the audit follows the present map rather than "is it 0xFF".
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        o = 1 * reflow.BLOCK_SIZE + (3 + 20) * reflow.FRAME_SIZE
        card.data[o:o + reflow.FRAME_SIZE] = bytes(reflow.FRAME_SIZE)
        _rows, _ok, bad = card.audit()
        self.assertEqual(bad, 0)


# ------------------------------------------------------------------ planning

class TestPlan(unittest.TestCase):
    def test_japanese_name_is_reflowed_and_resealed(self):
        card = make_card({1: {"place": JP_BRAVO,
                              "records": {2: JP_ALPHA},
                              "chunks": [0, 12]}})
        gloss = {"\u30a2\u30eb\u30d5\u30a1": "Alpha",
                 "\u30d6\u30e9\u30dc": "Bravo"}
        edits, skips = reflow.build_plan(card, gloss)
        kinds = sorted(e.kind for e in edits)
        self.assertEqual(kinds, ["party", "place"])
        seals = reflow.apply_plan(card, edits)
        self.assertEqual(sorted(e.kind for e in seals), ["crc", "titlexor"])
        _rows, _ok, bad = card.audit()
        self.assertEqual(bad, 0, "resealed card must pass the audit")
        skips = [s for s in skips if s[0] == 1 and s[1] != "place"]
        off = (1 * reflow.BLOCK_SIZE
               + reflow.record_name_site(2)[1][0][0])
        self.assertEqual(bytes(card.data[off:off + 12]),
                         FW("Alpha") + b"\x00\x00")
        self.assertEqual(skips, [])

    def test_without_resealing_the_audit_fails(self):
        # MUTANT ON THE RESEALER. If reseal is skipped the audit must catch it;
        # otherwise the passing test above proves nothing.
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        gloss = {"\u30a2\u30eb\u30d5\u30a1": "Alpha"}
        edits, _skips = reflow.build_plan(card, gloss)
        for e in edits:
            for off, _old, new in e.pieces:
                card.set_bytes(off, new)
        _rows, _ok, bad = card.audit()
        self.assertGreater(bad, 0)

    def test_english_to_english_reflow(self):
        card = make_card({1: {"place": FW("Bravx"), "chunks": [0]}})
        edits, _skips = reflow.build_plan(card, {"Bravx": "Bravo"})
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].pieces[0][2],
                         FW("Bravo") + reflow.FW_SPACE * 5)

    def test_absent_chunk_is_left_alone(self):
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0]}})
        edits, skips = reflow.build_plan(card, {"\u30a2\u30eb\u30d5\u30a1": "Alpha"})
        self.assertEqual(edits, [])
        self.assertEqual([s for s in skips if s[0] == 1 and s[1] != "place"], [])

    def test_unaccountable_padding_is_skipped_not_written(self):
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        off = 1 * reflow.BLOCK_SIZE + reflow.record_name_site(2)[1][0][0]
        card.data[off + 10] = 0x41            # junk after the terminator
        edits, skips = reflow.build_plan(card, {"\u30a2\u30eb\u30d5\u30a1": "Alpha"})
        self.assertEqual(edits, [])
        self.assertTrue(any("not name-plus-zero-pad" in s[2] for s in skips))

    def test_overlong_name_is_refused(self):
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        edits, skips = reflow.build_plan(
            card, {"\u30a2\u30eb\u30d5\u30a1": "Alphamikefox"})
        self.assertEqual(edits, [])
        self.assertTrue(any("field is 12" in s[2] for s in skips))

    def test_unknown_name_is_refused(self):
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        edits, skips = reflow.build_plan(card, {"somethingelse": "X"})
        self.assertEqual(edits, [])
        self.assertTrue(any("no glossary row" in s[2] for s in skips))

    def test_straddling_record_reseals_both_frames(self):
        card = make_card({1: {"records": {15: JP_ALPHA},
                              "chunks": [0, 19, 20]}})
        edits, skips = reflow.build_plan(card, {"\u30a2\u30eb\u30d5\u30a1": "Alpha"})
        self.assertEqual(len(edits), 1)
        self.assertEqual(len(edits[0].pieces), 2)
        seals = reflow.apply_plan(card, edits)
        self.assertEqual(len({e.label for e in seals if e.kind == "crc"}), 2)
        _rows, _ok, bad = card.audit()
        self.assertEqual(bad, 0)
        self.assertEqual([s for s in skips if s[0] == 1 and s[1] != "place"], [])

    def test_a_block_with_no_title_is_skipped(self):
        card = make_card({1: {"records": {2: JP_ALPHA}, "chunks": [0, 12]}})
        card.data[1 * reflow.BLOCK_SIZE:1 * reflow.BLOCK_SIZE + 2] = b"\xFF\xFF"
        edits, skips = reflow.build_plan(card, {"\u30a2\u30eb\u30d5\u30a1": "Alpha"})
        self.assertEqual(edits, [])
        self.assertTrue(any("no SC title frame" in s[2] for s in skips))


if __name__ == "__main__":
    unittest.main()
