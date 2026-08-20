# DQIV_PSX_TOOLS

A read-only Python library for reading Dragon Quest IV on the PlayStation
(SLPM-86916): its archive container, its compressed text, its Huffman trees, its
phrase dictionaries, its sector table and its glyph atlas.

stdlib only. No dependencies. Nothing here writes to a disc image.

**No game data ships here.** You supply your own disc image.

## What this is for

Reading the format, and proving that the reading is right. Every claim the library
relies on is checked by a gate that runs against a real disc and prints the measured
value next to the expected one.

If you want to know how the format works, read **[FORMAT.md](FORMAT.md)**. It is the
single authoritative place for that, and every claim in it carries either the gate
number that proves it or an explicit INFERRED or UNKNOWN label. This README does not
repeat any of it.

## Layout

```
dq4/
  iso.py          raw disc image access
  hbd.py          archive block and sub-block access
  textblock.py    text sub-block header parsing
  huffman.py      Huffman decode and encode
  dictionary.py   phrase dictionary parse and expansion
  sectortable.py  level sector table access
  glyph.py        glyph atlas rendering
  codes.py        control code table and census
verify.py         the gate suite
docs/             phase reports, kept as supporting evidence
FORMAT.md         the format reference
```

`docs/` holds the working reports the library was derived from. They are evidence for
FORMAT.md, not a second reference; where a report and FORMAT.md disagree, FORMAT.md is
current and the report is a snapshot.

## Running the gates

```
python verify.py --dq4 "path/to/Dragon Quest IV (Japan).bin"
```

Takes a couple of minutes, because it decodes and re-encodes every text sub-block on
the disc. Output is one line per gate with the measured value and the expected one.

Seventeen gates cover the disc hash, the block scan, the sub-block census, the text
header invariants, a known-good decode, a byte-exact round trip, the dictionary, the
sector table, the control code census and the atlas geometry.

Two of them, gates 9 and 10, exist because of a specific failure. A decoder that had
collapsed to a two-leaf tree passed the byte-exact round trip on 1,527 of 1,528 blocks,
because a degenerate tree round-trips any bitstream perfectly. Only the corpus bits per
symbol figure exposed it. **Any gate that can pass degenerately carries a companion, or
it does not ship.**

## Using it

```python
import sys; sys.path.insert(0, "path/to/DQIV_PSX_TOOLS")
from dq4 import iso, hbd, textblock, huffman, dictionary

with iso.RawISO("Dragon Quest IV (Japan).bin") as disc:
    lba, size = disc.find("HBD1PS1D.Q41")
    archive = disc.extract(lba, size)

blocks = hbd.scan_blocks(archive)
for sector, sub in hbd.text_sub_blocks(blocks):
    raw = hbd.sub_bytes(archive, sub)
    tb = textblock.TextBlock(raw)
    tree = huffman.HuffmanTree(tb)
    symbols = tree.decode()
    phrases = dictionary.parse(raw, tb)
    expanded, unresolved = dictionary.expand(symbols, phrases)
    print(hex(tb.id), huffman.render(expanded)[:80])
```

## Credit

This is built on **Markus Schroeder's** documentation at markus-projects.net and on
**Mandy Wilkens's** control code table and compression identification. FORMAT.md opens
with a fuller acknowledgement, including which specific observation of Markus's made
the tree decodable at all.

## License

See `LICENSE`. Not yet chosen.
