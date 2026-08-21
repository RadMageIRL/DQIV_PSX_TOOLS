# Dragon Quest IV (PlayStation) file format reference

This is the authoritative location for every format claim in this repository. The README
describes what the repo is. Module docstrings describe what a function does. Format facts
live here and nowhere else.

Every claim carries its evidence. **MEASURED** claims name the `verify.py` gate that proves
them, or the phase that measured it where no gate covers it. A claim with no gate is marked **INFERRED** or **UNKNOWN** in the same sentence.

Run the gates yourself:

```
python verify.py --dq4 "path/to/Dragon Quest IV (Japan).bin"
```

Target image: SLPM-86916, disc SHA-256 `100d87db9deadf8f9fa4bb891d3a5d0bb112acbf5adbcbc93c637848ed9c7531`.
MEASURED, gate 1.

---

## Acknowledgements

**Markus Schroeder** (markus-projects.net) documented this format first, and his work is the
foundation everything below is built on. The block and sub-block header layout, the six-int
text block header, the Huffman tree encoding, the sector table packing and the type 8 TIM
identification are all his. Where our measurements refine a figure of his, that is because he
gave us something precise enough to test.

One note of his deserves singling out. His disassembly observation at 0x8008F3BC, that one
register points to the start of the tree and another to the middle and that the two serve the
two sides of a branch, is exactly what the dual-base topology below turned out to be. That
observation is the reason the tree decodes at all.

**Mandy Wilkens** identified the compression as LZSS and published the control code table.
Her table was checked against the whole decoded corpus: all 37 of her codes occur, her table
is a strict subset of the 43 codes present, and every one of her fifteen name code
assignments is supported by decoded context with **zero disagreements**. MEASURED, gate 16.

**crosswire's** LZSS implementation, specifically the zero-filled ring buffer variant, is what
Mandy identified as correct, and it is.

---

## 1. Disc layout

Three files, no directories. MEASURED, gate 1.

| File | LBA | Size |
|---|---:|---:|
| `SYSTEM.CNF` | 23 | 68 |
| `SLPM_869.16` | 24 | 692,224 |
| `HBD1PS1D.Q41` | 362 | 319,436,800 |

The image is Mode 2 Form 1, 2352-byte raw sectors with 2048 user bytes at offset 24.

**The archive LBA base is 362.** This number matters in section 7.

---

## 2. Archive container

`HBD1PS1D.Q41` is 319,436,800 bytes, 155,975 sectors of 2048.

### The archive is a sector-addressed heap, not a chain

Blocks are found by scanning **every** 2048-byte sector boundary and applying the validity
filter below. Walking block to block by each block's stored sector count terminates after
1,609 blocks at file offset 0x94DA000, which is 48.86% of the file, because a different
sector format begins there (section 8). MEASURED, Phase 0; the heap scan is gate 2.

### Block header, 16 bytes at a sector boundary

| Offset | Size | Field |
|---:|---:|---|
| 0 | u32 | sub-block count |
| 4 | u32 | sector count |
| 8 | u32 | total data length |
| 12 | u32 | zero |

### Sub-block header, 16 bytes each, starting at block offset 16

| Offset | Size | Field |
|---:|---:|---|
| 0 | u32 | data length |
| 4 | u32 | uncompressed length |
| 8 | u32 | unknown |
| 12 | u16 | flags |
| 14 | u16 | type |

### The validity filter

All five conditions must hold. Together they select exactly **3,243** blocks. MEASURED, gate 2.

1. first dword is `XX 00 00 00` with `XX` nonzero
2. dword at offset 12 is zero
3. sub-block count and sector count are both nonzero
4. the sub-block data lengths sum exactly to the block total length
5. `ceil((16 + 16 * nsub + total_len) / 2048)` equals the stored sector count

### Type census

**23,828 sub-blocks.** MEASURED, gate 4.

| Type | Count | | Type | Count | | Type | Count |
|---:|---:|---|---:|---:|---|---:|---:|
| 0x01 | 6 | | 0x15 | 3317 | | 0x25 | 1033 |
| 0x06 | 1730 | | 0x16 | 72 | | 0x26 | 1377 |
| 0x07 | 1458 | | 0x17 | 44 | | 0x27 | 976 |
| 0x08 | 309 | | 0x18 | 1062 | | **0x28** | **1315** |
| 0x09 | 473 | | 0x19 | 27 | | 0x29 | 1730 |
| 0x0A | 256 | | 0x1A | 573 | | **0x2A** | **213** |
| 0x0B | 309 | | 0x1F | 1025 | | 0x2B | 24 |
| 0x0C | 309 | | 0x20 | 32 | | 0x2C | 152 |
| 0x0D | 970 | | 0x22 | 975 | | 0x2D | 140 |
| 0x0E | 44 | | 0x23 | 1576 | | 0x2E | 612 |
| 0x0F | 2 | | 0x24 | 1506 | | 0x2F | 27 |
| 0x11 | 5 | | 0x12 | 5 | | 0x13 | 141 |
| 0x14 | 3 | | | | | | |

Types 0x02 through 0x05, 0x10, 0x1B through 0x1E and 0x21 do not occur.

Type 40 (0x28) and type 42 (0x2A) are the text blocks: **1,528 sub-blocks**, 1,315 and 213.
MEASURED, gate 5.

Type 1 holds the glyph atlas (section 8). Type 8 holds TIM textures. MEASURED, Phase 4.

### Compression

A sub-block is LZSS compressed when **`flags == 0x0500`**. 5,821 sub-blocks carry that flag
and all 5,821 decompress correctly. The algorithm is LZSS with a **zero-filled** ring buffer,
not the textbook 0x20 fill: N 4096, F 18, threshold 2 so the minimum match is 3, initial write
pointer at N minus F, flag bits LSB first with 1 meaning literal, and a match packed as two
bytes where the first is the low 8 bits of the offset and the second is
`((offset >> 4) & 0xF0) | (length - 3)`. MEASURED, Phase 4.

All 5,821 flagged sub-blocks decompress. MEASURED, gate 18. The flag separates the population
exactly: of the sub-blocks whose two length fields differ, 5,820 carry the flag and decompress,
147 do not carry it and fail completely, with no overlap. MEASURED, gate 19.

The natural output length is either exactly the declared length (3,089 blocks) or exactly three
bytes past it (2,732 blocks), and nothing else. That two-valued distribution is the companion
metric for the decoder: a decompressor that padded or guessed would not produce it. MEASURED,
gate 20.

The whole archive decompresses to 373,357,942 bytes from 177,689,724 compressed. MEASURED,
Phase 4.

---

## 3. Text sub-block

Six little-endian u32 at offset 0.

| Index | Name | Meaning |
|---:|---|---|
| 0 | `a` | offset near the end; the u32 stored **at** offset `a` equals `a` |
| 1 | `id` | text id, 16 bits effective |
| 2 | `c` | Huffman code start |
| 3 | `d` | Huffman tree end; 0 means use `a` |
| 4 | `e` | Huffman code end, and the start of the 10-byte tree header |
| 5 | `f6` | **dictionary table offset**, 0 when the block has no dictionary |

The sixth int is not filler. It is the dictionary pointer, and it is 24 in exactly the 189
blocks that carry a 0x7Exx dictionary and 0 in exactly the 1,339 that do not. MEASURED,
gate 11.

### Invariants

Both hold on 1,528 of 1,528 text sub-blocks. MEASURED, gate 6.

- `c < e < d`, with `d` replaced by `a` when `d` is zero
- the u32 at offset `a` equals `a`

### Region map

Every boundary is derived from the header. The map closes with no gap. MEASURED, Phase 2.

| Range | Contents |
|---|---|
| `[0, 24)` | six u32 header |
| `[24, c)` | dictionary table and phrases; empty when `f6` is 0 |
| `[c, e)` | Huffman code stream |
| `[e, e+10)` | tree header: u32 `base`, u32 `mid`, u16 `root` |
| `[base, d)` | tree pair array, 16 bits per entry |
| `[d, a)` | record table and an undecoded region (section 10) |
| `[a, a+4)` | self pointer, value equals `a` |
| `[a+4, len)` | tail: zero, or a count plus records in 855 blocks (section 12) |

`base` equals `e + 10` in all 1,528 blocks. MEASURED, Phase 2.

The engine reads this header at 0x8008F214 and resolves it into a resident 12-slot table of
32-byte structs at 0x80100168: `lw` at `e+0` is the base offset, `lw` at `e+4` the mid offset,
`lhu` at `e+8` the root, and each offset is added to the block's RAM base. The sixth header int
is loaded at 0x8008F250, zero-checked, and resolved the same way, which is the dictionary
pointer behaving exactly as measured. At most **12 text blocks are resident at once**.
MEASURED, Phase 9.

### Text ids

Ids span 0x0020 to 0x0482. 1,106 are distinct. 181 ids carry only placeholder blocks whose
entire decoded content is the string `ダミー`, leaving **925 ids with real content**.
MEASURED, gate 15.

Note the arithmetic: 187 placeholder sub-blocks occupy only 181 distinct ids, because six ids
carry two placeholder copies each. Subtracting the block count instead of the id count gives
919 and is wrong.

---

## 4. Huffman tree

### Dual-base topology

The tree uses two base pointers rather than interleaved pairs. For node NN, one child
descriptor is at `pair[NN]` and the other at `pair[m + NN]`, where `m = (mid - base) / 2` read
per block from the 10-byte tree header. MEASURED, gates 7 through 10.

`m` is computed per block and must never be hardcoded. Measured values run from 4 to 1,132.
MEASURED, Phase 1.

Traversal starts at node number `root`, the u16 at `e + 8`. Bit 0 selects `pair[NN]`, bit 1
selects `pair[m + NN]`. Bits are read **LSB first** within each byte. MEASURED, gate 7.

**Confirmed against the machine code.** The decoder at 0x8008F3BC holds the two bases in
separate registers, loaded from a resident 32-byte struct, and selects between them on a bit
test: `beq` on the masked stream bit falls through to `addu v0,v0,a2` (base) or branches to
`addu v0,v0,v1` (mid), in both cases after `sll v0,v0,1` to scale the node number to 16-bit
entries. The node test is `sltu` against 0x7FFF, which is `value >= 0x8000` and not a high-byte
comparison. The bit position counts up from 0 to 7 before advancing the byte pointer, which is
LSB first. Leaves are offset by `ori s1,s1,-32768`, and the 0x0000 terminator is explicitly
excluded from that. MEASURED, Phase 9.

### Entry decode

Each pair is a little-endian u16 `v`:

| Condition | Meaning |
|---|---|
| `v >= 0x8000` | node; node number is `v - 0x8000` |
| high byte `0x7F` | control code, value `v` |
| high byte `0x7E` | dictionary reference, value `v` |
| `v == 0x0000` | END of string, a real symbol, not padding |
| otherwise | Shift-JIS character, value `v + 0x8000` |

### The wide node form

The node test is `v >= 0x8000`. It is **not** "high byte equals 0x80".

**252 blocks have more than 256 nodes** and require the wide form. Reading the test narrowly
collapses those trees to two leaves, and a collapsed tree **still passes a byte-exact round
trip**, because one-bit codes reproduce any bitstream. MEASURED, Phase 4 for the block count;
the collapse was caught by gates 9 and 10.

This is why gates 9 and 10 exist. During development a collapsed decoder passed the round trip
on 1,527 of 1,528 blocks. What exposed it was corpus bits per symbol: 1.06 for the collapsed
decoder against **7.81** correct, and a minimum leaf depth of 1 against a correct minimum of 2.
MEASURED, gates 9 and 10.

### Round trip

Decode and encode are mutually inverse on all 1,528 text sub-blocks, byte exact. MEASURED,
gate 8.

Encoding must **zero fill to the original region length**. 1,114 blocks end with 1 to 10
trailing bits that complete no code, and every one of those bits is zero. Without the fill,
three blocks fail on length alone with no differing bit. MEASURED, Phase 1.

### Known-good decode

Text id 0x006C decodes to 12 pieces, 11 terminated by END plus a trailing residue. Piece [10]
is:

```
どうした？　<7F1F>。<7F02>もう　降参かい？
```

MEASURED, gate 7.

---

## 5. The 0x7Exx phrase dictionary

Present in 189 of 1,528 text sub-blocks, pointed to by `f6`.

| Property | Value |
|---|---|
| location | `[24, c)`, that is, from `f6` to the code stream start |
| entry | one u16, packed `(length << 12) \| offset` |
| length | in 16-bit units |
| offset | byte offset from the start of the sub-block |
| entry count | not stored; it is `(first_entry_offset - f6) / 2` |
| code numbering | **1-based**; code 0x7E01 is table index 0 |
| phrase encoding | **raw Shift-JIS**, not Huffman coded |
| inline control codes | the two bytes `FF xx` meaning `0x7Fxx` |

The entry count is not stored anywhere. It is recovered from the first entry's offset, because
phrase data begins immediately after the table. The last phrase ends exactly at `c` in 149 of
the 189 blocks and at `c - 2` in the other 40. MEASURED, Phase 2.

### The dictionary is per block

The same code means different things in different blocks. Code 0x7E08 is `ない` in block
0x0021 and `外に　出てきてみ` in block 0x0022. MEASURED, Phase 2.

The 158 distinct codes seen across the corpus are the **union** across blocks, not a single
table. The largest single table is 158 entries, the smallest is 18.

Corpus-wide expansion resolves with **zero unresolved references**. MEASURED, gate 11.

Mean expansion in block 0x0021 is **2.33 symbols**, minimum 2, maximum 6. MEASURED, gate 12.
A mean at or below 1 across the board means the table was misread; that is what gate 12 is for.

---

## 6. Control codes

**43 distinct codes** occur across the decoded corpus. Mandy Wilkens's published table of 37
is a strict subset: every one of her codes occurs. MEASURED, gate 16.

### Verified table

| Code | Meaning | | Code | Meaning |
|---|---|---|---|---|
| 0x0000 | end of string, required terminator | | 0x7F2A | フレア |
| 0x7F02 | new line plus tab | | 0x7F2B | ホイミン |
| 0x7F04 | name decorator, starts named dialog | | 0x7F2C | オーリン |
| 0x7F0A | blinking cursor | | 0x7F2D | ホフマン, not always |
| 0x7F0B | end of line, opposite of 0x7F0A | | 0x7F2E | パノン |
| 0x7F0C | end of line, in groups of about six | | 0x7F2F | ルーシア |
| 0x7F15 | received gold | | 0x7F30 | person |
| 0x7F16 | unknown, see 0x7F18 | | 0x7F31 | ピサロ, mostly as デス{7F31} |
| 0x7F17 | unknown | | 0x7F32 | ロザリー |
| 0x7F18 | unknown | | 0x7F33 | person |
| 0x7F1A | ルーシア | | 0x7F34 | custom name |
| 0x7F1F | player name | | 0x7F42 | town name |
| 0x7F20 | ライアン | | 0x7F43 | emphasis, unconfirmed |
| 0x7F21 | アリーナ | | 0x7F44 | emphasis, sad contexts |
| 0x7F22 | クリフト | | 0x7F45 | emphasis, before デスピサロ dialog |
| 0x7F23 | ブライ | | 0x7F4B | noun |
| 0x7F24 | トルネコ | | 0x7F4C | name, possibly same as 0x7F33 |
| 0x7F25 | ミネア | | | |
| 0x7F26 | マーニャ | | | |
| 0x7F28 | スコット | | | |
| 0x7F29 | アレクス | | | |

All fifteen name codes 0x7F20 through 0x7F2F are supported by decoded context, with zero
disagreements. Two of the sharpest confirmations: `<7F04><7F29>「やや　戦士どの！<7F02>私です。アレクス`
places the literal name immediately after the code, and `<7F04><7F24>は　<7F15>Ｇを　手に入れた！`
independently confirms 0x7F15 as received gold. MEASURED, Phase 3.

### The six additional codes

Present in the data, absent from the published table. **No meanings are proposed.** MEASURED,
gate 16 for their presence; their semantics are UNKNOWN.

| Code | Occurrences | Position in string |
|---|---:|---|
| 0x7F12 | 70,488 | mid 70,264, start 224, end 0 |
| 0x7F11 | 35,729 | mid 34,652, start 1,066, end 0 |
| 0x7F05 | 664 | **end 664**, always the last symbol before END |
| 0x7F13 | 438 | mid 435 |
| 0x7F14 | 166 | mid 166, always the fourth element of an enumeration |
| 0x7F47 | 84 | mid 83, always in the string `<7F04><7F47>　<7F05>` |

Counts are after dictionary expansion, since phrases carry inline control codes.

---

## 7. Sector table

Located in `SLPM_869.16`. One little-endian u32 per level.

| Field | Bits | Meaning |
|---|---|---|
| length | `v >> 20` | 12 bits, in sectors |
| lba | `v & 0xFFFFF` | 20 bits, **absolute disc LBA** |

| Property | Value |
|---|---|
| first entry | file offset 0x935F4 |
| last entry | file offset 0x9693C |
| entry count | 3,283 |
| entry size | 4 bytes |
| table size | 13,132 bytes |

MEASURED, gate 13. Boundaries are clean: the dword before the table and the dword after it are
both `0x00000001`, which decodes to a length of zero and is not a valid entry.

### The LBA base is 362

The 20-bit field is an absolute disc LBA. **Subtract 362**, the ISO LBA of `HBD1PS1D.Q41`, to
get an archive sector.

Under that base, **3,241 of 3,283** entries land on a valid block header **and** have their
length field equal that block's stored sector count. MEASURED, gate 14. No other base comes
close: base 0 gives 79 length matches, base -1 gives 48, base +1 gives 50, base +362 gives 11.

The known probe `3A A2 D1 04` occurs exactly once, at file offset 0x93B2C. It decodes to
length 0x4D, LBA 0x1A23A. Archive sector 0x1A23A is payload; archive sector 0x1A23A minus 362
is a block header with a stored sector count of 0x4D that contains a type 40 sub-block with
text id 0x0067. MEASURED, gates 13 and 14.

**Two** valid blocks are never referenced by the table: archive sectors 123893 and 123924.
MEASURED, Phase 5.

An earlier count of ours said five, adding 105328, 105630 and 106298. That was wrong. Those
three are referenced, by entries at file offsets 0x9692C, 0x96930 and 0x96934, which are table
positions 3278, 3279 and 3280 of 3283. Each decodes to the right archive sector with a length
field matching the block's stored sector count exactly. The error came from computing coverage
over the table's contiguous strictly-valid runs rather than over its full extent; those three
entries sit in the last stretch, past the end of the second run. The three blocks in question
hold the glyph atlas, so the atlas **is** loaded by the game.

---

## 8. Glyph atlas

The type 1 sub-blocks hold a 4bpp atlas. Six sub-blocks, two distinct contents, three copies
each.

| Property | Value |
|---|---|
| pixel format | 4bpp, **low nibble first** |
| width | 256 pixels |
| cell | **8 wide by 14 tall**, origin (0, 0) |
| DQ4 atlas size | 16,128 bytes, 126 rows, 9 bands |
| slots | **288**, of which **268** are non-blank |
| Latin capitals | **13**, at slots 26 through 38 |

MEASURED, gate 17.

Geometry was derived, not assumed. Byte-equality autocorrelation peaks at a stride of 128
bytes, which is 256 pixels at 4bpp. Column ink minima land on `x mod 8 == 0` far more often
than on any other residue, 29 times against 13 for the next best. Rendering high nibble first
breaks every vertical stroke into a dotted line. MEASURED, Phase 3b.

### The drop shadow is inside the cell

The rightmost column and the bottom row of each cell carry the glyph's drop shadow, not the
letterform. Column 0 is empty on eleven of the thirteen capitals. MEASURED, Phase 3b.

For width calculations: cell advance is 8 pixels, the letterform body occupies columns 1
through 6, **effective body width is 6 of 8**, or 7 of 8 if the shadow is counted.

### What the atlas contains

The 13 Latin capitals present are Z, X, V, T, R, P, N, L, J, H, F, D and B, in a strictly
ordered run at slots 26 through 38. The other 13 capitals, all lowercase and all digits are
absent from this atlas. MEASURED, gate 17 and Phase 3b.

The remaining non-blank slots hold kana, kanji, punctuation and small forms.

**129 slots are kanji, rendered halfwidth at 8 x 14.** MEASURED, Phase 6, established two ways:
by rendering them, and by counting horizontal strokes spanning at least 5 of the 8 columns.
Those 129 average 10.8 such strokes with a minimum of 7, against a mean of 5.3 and a maximum of
8 for the 13 known Latin capitals. Dense multi-stroke glyphs at that count are kanji.

So DQ4 renders kanji at 8 x 14 from this atlas. It holds 129 of the 1,315 distinct kanji the
script uses, so it is a partial set and a larger source exists somewhere. That source has not
been located. The remaining slot classifications, kana against symbols, are still by ink
density and height **proxy**: INFERRED.

### The 60 01 01 80 band

Sectors 76,212 through 141,196 of the archive, 26,635 sectors, are **PlayStation STR/MDEC
full motion video**, not archive data. All 26,635 sector headers parse as STR video sectors:
128 by 120 pixels, 5 chunks per frame, 5,327 frames, 40 separate clips. MEASURED, gate 3 for
the sector count, gate 21 for the parse.

---

## 9. Corrections to published documentation

Stated as measurements. Every one of these refines work that was precise enough to test.

**The second block signature is `60 01 01 80`, not `0x60010108`.** All 26,635 sectors have the
same four bytes, and the fourth byte is 0x80 in every one. The sequence is the little-endian
form of the standard PlayStation STR video magic `0x80010160`, which also explains what the
band is. MEASURED, gate 3.

**The sector table holds absolute disc LBAs, not archive sectors.** Descriptions giving
`0x0001A23A` as an archive sector are off by the 362-sector file base. Archive sector 0x1A23A
is payload, not a header. MEASURED, gate 14.

**The archive is a sector-addressed heap, not a chain.** A linear walk from block to block by
sector count terminates at 48.86% of the file. MEASURED, Phase 0.

**The sub-block flags word DOES determine compression, and an earlier note of ours saying
otherwise was wrong.** The compression predicate is `flags == 0x0500`, not a mismatch between
data length and uncompressed length. The separation is exact: of the sub-blocks with a length
mismatch, all 5,820 with `flags == 0x0500` decompress correctly as LZSS and all 147 without it
fail completely, with no overlap in either direction. Types 44, 45, 46 and 47 hold those 147.

Those 147 are **MIPS overlay code**, not compressed data. Three of the four types open with
recognizable debug strings followed by a MIPS function prologue: type 47 begins
`can't get new_fmap!!(%d)(max=%d)`, type 45 begins `buki open NG`, and type 46 opens directly
with `e8 ff bd 27`, which is `addiu sp, sp, -0x18`. MEASURED, Phase 5. Their uncompressed
length field is larger than their data length by a ratio between 1.0012 and 4.38, constant
within types 46 and 47 and variable within 44 and 45; that it represents a runtime size
including uninitialized data is INFERRED and not tested.

The earlier claim came from using a length mismatch as the definition of compressed, which
made types 44, 45 and 47 look like counterexamples. They are not compressed at all.

---

### CORRECTED, Phase 12: what 0x8008F3BC is

Phase 11 described `0x8008F3BC` as "a unified character cursor, **not** the Huffman decoder".
The negation is wrong. The range `0x8008F3BC` to `0x8008F600` contains **no `jr ra` at all**; the
function's only return is at `0x8008F7A8`, so it is 253 instructions long and the dual-base walk
Phase 9 cited at `0x8008F550-0x8008F568` is inside it.

Both readings describe one function. It dispatches on the sign bit *and* walks the dual-base
tree. Phase 9's attribution was correct throughout.

The dual-base finding itself was never at risk, being proven independently by the codec at 1,528
of 1,528 blocks. Only the attribution was disputed.

**The transferable rule**, since no gate could have caught this: gate 26 checks that `jal` targets
follow a `jr ra`, and it was correctly silent, because no boundary was crossed. The error was a
claim made by negation from a partial read. **Do not state what a routine is not until you have
read it to its `jr ra`.**

### CORRECTED, Phase 12: ordinal addressing was inferred too early

Phase 11 inferred that the unreferenced strings in `0x0020` (place names), `0x0026` (person
types) and `0x022B` (a party-member family) were reached by ordinal rather than by pointer, on
the strength of their content.

**Sub-block type 44 references them** (section 14): `0x0021` completely at 1,086 of 1,086,
`0x0020` at 380 of 395, `0x0026` at 55 of 59, `0x0022` at 7 of 7. The inference is withdrawn for
the name tables. Only the `0x022B` family is still unreferenced, and one family of five lines
supports no mechanism.

No ordinal walker exists among the decoder's callers. The only counted terminator loop is
`0x8008FCAC`, which returns a **character** count for display width and stops at the first
terminator.

## 10. Unknowns

The edges are part of the map. None of these is claimed to be understood.

**`[p2, a)`.** The region after the record table. It **is LZS compressed**: it decompresses
cleanly, consuming its input exactly, at a ratio near 3.2x on the blocks sampled. MEASURED,
Phase 5. What the decompressed content is remains UNKNOWN. It is not Huffman text under the
block's own tree, and the decompressed bytes are not a glyph bank indexed by the record table
(section 11).

**The tail record table is no longer unknown** (section 12), and neither is the direct-form
referrer population (section 13). What remains unknown is how the last **4,992 non-empty
strings** are addressed. They are not reached by either measured system.

The evidence points at **ordinal addressing**, INFERRED and not confirmed: the wholly
unreferenced blocks are index tables (0x0020 place names, 0x0026 person types, both starting
with なし at index 0), and the scattered cases are families like 0x022B strings 0 to 4, five
lines identical but for the party-member code. An ordinal computed at runtime leaves no bytes
on the disc, which is consistent with every byte-level scan returning chance. The routine that
walks a block to string N has not been located; it was not found among the 11 functions that
touch the resident block table.

**The per-kanji record table at `d + 32`.** One 8-byte record per kanji leaf of the block's
tree, carrying a u32 and a 16-bit value that is 0x0D0C on almost every entry. Purpose UNKNOWN.

The u32 is **block-local**. Of 897 kanji appearing in the record tables of three or more text
ids, only 34 carry the same u32 everywhere; 863 differ, and the mean ratio of distinct values
to blocks is 0.858. It is an index into something local to the block, not a global glyph
identifier pointing at a shared payload. MEASURED, Phase 8.

That 16-bit field was once read as a glyph width and height, 0x0D0C as 12 by 13. **That reading
is withdrawn**: the atlas renders kanji at 8 pixels wide, so a 12-wide glyph dimension cannot
describe them. MEASURED, Phase 6.

That the table is kanji-related does hold up. Dragon Warrior VII has 2,122 sub-blocks with the
same six-int text header structure, and every one carries the same `[d, a)` header shape with
the record area **empty**, 36 bytes in all 2,122, leaving no room for records and no payload
region at all. A game with no kanji has the structure and none of the content. MEASURED,
Phase 6.
Note that `p1` does **not** point at these records; for text id 0x006C `p1` is `d + 28` and the
records begin at `d + 32`.

**The 60 01 01 80 band internals.** Identified as STR video (section 8). The frames themselves
are not decoded here.

**The fullwidth font.** The atlas cell is 8 by 14 and holds 129 kanji at that size. The script
uses 1,315 distinct kanji, so a larger source exists and is **not located**. A sweep of 21,418
unique sub-blocks across seven row widths and four cell heights found no second atlas, and the
console BIOS is ruled out (section 11).

**The string count gap.** Counting one block per distinct text id gives 17,234 strings.
Markus's published figure is 16,695. The difference of 539 is **reported, not closed**: what
counts as a line is a definition, and without knowing his the gap cannot be resolved honestly.
MEASURED, Phase 2.

---

## 11. Negative results

These cost real time to establish. They are here so nobody has to spend it twice.

### `[p2, a)` is not a bit-indexed glyph bank

The hypothesis was that the per-kanji record's u32 is a bit offset into `[p2, a)` and the
16-bit value is a width and height, giving 1bpp glyphs. The width and height split is real:
0x0D0C is 12 by 13, and 0x080B is 11 by 8 on the record carrying 一. Everything downstream
fails.

- Consecutive offset deltas are 57, 134, 159, 145, 142, 151, 163, 145, 160, 143, 162, 150,
  141, 154. A fixed 12 by 13 glyph is 156 bits and cannot produce a **variable** stride.
- The record for 一 sits at offset 0 and claims 88 bits, but the next offset is 57, which is
  less than 88. The entries would overlap. This contradiction exists before any rendering.
- Ink density comes out 42.9% to 69.2%, mean about 50%, against 15% to 50% for real glyphs.
- **The decisive test**: reading at a deliberately wrong offset, plus 7 bits, produces ink
  within 1.5 points of the correct offset on **every** record, and art of identical character.
  A 7-bit shift destroys real structure. It did not, because there is none.
- 2bpp is worse, 66.7% to 92.3%.

### The record bit offsets do not point at string starts

Tested directly. Of 17 records, **3** have an offset that lands on a string start in the code
stream, and those three are exactly the records whose offset is zero. Zero records land on a
symbol boundary carrying that record's own kanji.

### Type 1 blocks are not the English game's text font

Dragon Warrior VII, a shipped English game on the same engine family, has a type 1 atlas in
the identical format: same 4bpp low-nibble-first packing, same 256 pixel width, same 8 by 14
cell, same 14-row band, same drop shadow convention. Its 1,024-byte companion block is
**byte identical** to Dragon Quest IV's.

That atlas contains 13 Latin capitals: Y, W, U, S, Q, O, M, K, I, G, E, C and A. The exact
complement of Dragon Quest IV's thirteen. A shipped English game cannot render its text from
half an alphabet, so the type 1 block is not the text font in either game.

The absence was **proved, not assumed**, with a calibrated threshold:

| Comparison | Score, max 112 |
|---|---:|
| a letter against itself | **112** |
| different letters, same font, mean of all pairs | 50.8 |
| different letters, same font, **worst case** | 32 |
| different letters, same font, **best case** | **91** |
| **best cross-atlas match found, searching every pixel offset** | **82** |

Every cross-atlas best match falls below the 91 same-font ceiling, and every one lands on a
**shape neighbour**: B matches C, P matches O, N matches M, R matches Q. That is the signature
of absence, not of a font revision.

A second hypothesis, that the run turns around and the missing letters follow, was tested by
matching the next thirteen slots against the expected letters in order. Mean score 42.2
against a null of 41.1. No signal.

### LZS over `[p2, a)` is not a glyph bank either

Phase 5 tested a different encoding of the same region, since `[p2, a)` sits inside an
uncompressed sub-block and no earlier sweep had decompressed it. It **does** LZS-decompress
cleanly. The decompressed bytes are still not a glyph bank.

Record offsets were tested as both bit and byte offsets into the decompressed output, at 1, 2
and 4 bits per pixel, with width and height taken from the record's own extra field.

- As byte offsets the largest record offset exceeds the decompressed length, so several
  glyphs fall outside the buffer and render empty.
- Ink density lands at 0%, 3%, 4%, 7%, 19% and 25% across the first six records at 1bpp,
  against the 15% to 50% a real glyph occupies.
- **The offset-plus-7 control fails again.** Ink at the shifted offset matches ink at the
  correct offset to within a fraction of a point on every record: 25.0 against 25.0, 4.5
  against 4.5, 0.0 against 0.0. A seven-bit shift destroys real structure.
- Decompressed length per record is not constant: it ranges from 94.9 to 123.2 bytes, and two
  blocks with the same record count, 38, decompress to 4,344 and 4,680 bytes.

### The executables do not hold an LZS-compressed font

The LZS decompressor was slid across both executables at every 4-byte-aligned offset, 172,544
probes for one and 168,448 for the other.

**"Produces 1 KB of output before the stream fails" selects everything.** LZS as specified
here cannot fail on arbitrary input: every byte sequence decodes to something. On 25,088
probes of known STR video data, a region that is definitely not LZS, the criterion fired at
**100.0%**. It has no discriminating power and should not be used as one.

Running the atlas signature detector on the decompressed output does discriminate, and it was
measured against two baselines:

| Sweep | Probes | Atlas-signature hits | Rate |
|---|---:|---:|---:|
| STR video band, definitely not LZS | 25,088 | 0 | 0.0000% |
| SLPM_869.16 | 172,544 | 311 | 0.1802% |
| SLUSP012.06 | 168,448 | 453 | 0.2689% |
| **SLPM_869.16 byte-reversed control** | 172,544 | **401** | **0.2324%** |

The reversed control has identical byte statistics and contains no valid LZS stream at any
aligned offset, and it produces **more** hits than the real executable. The executable hit
rates are noise. The STR baseline of zero is misleading on its own, because video data is
high entropy and never yields the blank rows the detector looks for; the reversed-bytes
control is the honest comparison.

Every strong hit was rendered anyway. All are sparse scattered pixels with no glyph structure.

### The game does not read kanji from BIOS ROM

The PlayStation carries its own Shift-JIS font in console firmware, so a Japanese game drawing
kanji through it would contain no fullwidth font on disc. That would have explained every
negative in the font search. It is not what happens.

Scanning for LUI instructions loading a constant in the BIOS ROM window, immediate 0xBFC0
through 0xBFC7 or 0x9FC0 through 0x9FC7, word aligned with `rs` zero:

| Scan | Words | Hits |
|---|---:|---:|
| `SLPM_869.16` | 173,056 | **0** |
| `SLUSP012.06`, null control | 168,960 | 0 |
| STR video band, random baseline | 177,152 | 0 |
| all 147 MIPS overlay sub-blocks | 582,604 | **0** |
| all uncompressed sub-blocks | 13,279,218 | **0** |

Zero everywhere, including every place other than the main executable where code lives. A
byte-pattern search over the whole raw archive at any alignment turns up 7 matching sequences in
319 MB, five unaligned and two inside compressed data.

This tests direct addressing only. A call into a BIOS kernel routine that internally touched the
ROM would carry no LUI here, and no kanji service is part of the documented PlayStation BIOS
API, so the gap is small but real. INFERRED.

Neither BIOS image yields a font to the atlas detector either, and in both the byte-reversed
control scores higher than the real file: 15 hits against 7 for the US image, 10 against 4 for
the Japanese one. Their byte diff is 24,367 separate runs with a largest contiguous difference
of 1,781 bytes, which is a version revision rather than a resource present in one and absent
from the other.

### CORRECTED: the tail record values are bit offsets, measured from the wrong origin

Phase 8 recorded this as a negative result. It was a correct measurement of the wrong
hypothesis, and it is corrected here rather than deleted, because the failure mode is worth
keeping.

The reading tested was `value` as a bit offset **from `c`**, the start of the code stream. It
landed on a string start 0.51% of the time and on any symbol boundary 15.8% of the time against
a 15.9% random baseline, so it was rejected.

The engine measures the same field **from the block base** (section 12). Every block on this
disc has `c = 24`, so the tested frame was displaced by a constant `24 * 8 = 192` bits. A fixed
displacement into a Huffman stream lands at an arbitrary interior bit, which is exactly what a
random baseline looks like. Corrected:

| Reading | lands on a string start |
|---|---:|
| bit offset from `c` | 48 / 9,371, 0.51% |
| **bit offset from the block base** | **9,371 / 9,371, 100.00%** |
| same, +1 bit | 0 / 9,371 |
| same, -1 bit | 0 / 9,371 |

**The lesson: a null result rejects the hypothesis you tested, not the family it belongs to.**
The magnitude evidence that made the field look like an offset was right all along. Only the
zero point was wrong, and no amount of additional companion testing on the wrong frame would
have found that. The code did.

### C0 21 A0 is not a three-byte opcode

Type 39 scripts are **word-aligned u32 streams** with `0xA0` as the top byte of the command
class. Searched as a three-byte pattern, `C0 21 A0` straddles a word boundary and matches
92,681 times by chance, with near-uniform alignment residues. Word aligned, the real command
is `0xA021C000`, occurring 15,207 times across the 927 distinct script blocks.

The documented `<u16 bit offset> <u16 text id>` argument does not verify against the corpus.
Reading the following word either way gives 0.00% and 27.14%, and the 27% is an artifact:
the word's median value is 14, so its high half is zero on most commands and offset 0 is
always a valid string start.

An unbiased scan for *any* valid (offset, text id) u16 pair anywhere in the scripts, gated on
the corpus, is beaten by its own shuffled control: 220 hits in 200 real blocks against 569 in
the same blocks shuffled. There is no dense pointer encoding of that shape to find.

### The whole-executable scan for direct-form references is noise

Testing every word-aligned u32 in SLPM_869.16 as `(text id << 20) | bit offset` gives 103 hits
from 67,396 candidates, 0.15%. A shuffled control on the same bytes gives 104, 104 and 97. The
scan is worthless on its own, and only 9 distinct string pairs come out of it, dominated by a
single repeated value.

The same test restricted to the tables the **code** names lands 51/51 and 162/162. The lesson is
not that scanning fails, it is that scanning without a code-derived target fails. Phase 8 learned
this on script data; the executable behaves identically.

### A round trip cannot see a wrong-but-consistent rendering

The Phase 9 disassembler printed every I-type immediate signed. MIPS `ori`, `andi` and `xori`
zero-extend theirs, so `ori a0,a0,0xA8A7` rendered as `ori a0,a0,-22361` and reading it back
gave a constant 0xFFFF too low.

Gate 23 is a decode/reassemble round trip over all 152,367 executable words, and it passed at
100.0000% throughout, because `asm()` parsed the same signed text back to the identical
encoding. The error was invisible to the instrument by construction: both halves agreed on a
convention that was wrong.

This is the same shape as the Phase 1 collapsed Huffman tree, which round tripped 1,527 of
1,528 blocks byte-exactly while decoding at 1.06 bits per symbol. **A round trip proves two
implementations agree, never that either is right.** Gate 27 now checks the rendered text
directly, and requires that arithmetic immediates still print negative so it cannot be
satisfied by making everything unsigned.

### The MIPS false-positive trap

Searching an executable for a glyph table with a periodicity detector will find MIPS code
every time. Fixed register fields produce exactly the periodic column structure a font does.
This is the strongest hit from one such search, at 0x09FD00 of a PlayStation executable,
rendered 16 pixels wide at 1bpp:

```
 .##.#.##....#.##  #...###.....#.##  #.##........#.##  ##.#..#.....#.##
 ..##.##.....#.##  ...#...#....#.##  ###.##.#....#.#.  ##..#.......#.#.
 .##.####....#.##  #..#..#.....#.##  #.##.#.#....#.##  ##.#.###....#.##
 ..##...#....#.##  ....##.#....#.#.  ###.#.......#.#.  ##....##....#.#.
 .###.#......#.##  #..#.###....#.##  #.###..#....#.##  ##.##.##....#.##
```

The fixed `....#.##` and `....#.#.` right column is a register field, not a glyph edge. Two
independent detectors, vertical stroke continuity and a fixed-cell glyph-table scan, both
ranked this region top. Neither ink density nor row correlation distinguishes MIPS from a
font. Render before believing.

---

## 11b. The bit budget

MEASURED, Phase 13, gate 35.

A string's encoded length is the span from its start offset to the next END inclusive. Summed
spans plus trailing residue account for the code stream exactly, on all 1,528 sub-blocks:
`66,521,504 region = 66,502,078 consumed + 19,426 residue`, 0 failures.

Over the 1,106 distinct ids: region 4,891,456 bits, consumed 99.6965%, residue 0.3035%. Residue
per block is min 0, median 13, max 32 bits. **This is a different measurement from Phase 1's
pad count**, which counted bits after the last decodable symbol rather than after the last END;
708 blocks have 10 residue bits or fewer on this definition, not 1,114.

Bits per non-empty string: min 9, median 272, p90 573, max 5,331. Bits per displayed character:
median 7.39.

### English does not fit this budget

Phase 13 modeled a Latin-charset tree per block: 72 character symbols plus the block's expanded
control codes plus END, 73 to 93 leaves, pair array 145 to 185 against the 2,265 already on the
disc, so **realizable with a wide margin**.

| | median bits per displayed character |
|---|---:|
| existing Japanese trees | 7.256 |
| modeled English | 4.762 |

The 1.52x charset advantage does not cover the character growth. **Break-even is an expansion
ratio of 1.366**; it sits below 1.52 because the 89,511 control codes and the string terminators
are the same symbols in either language and do not shrink. At a 2.0 ratio 51 of 15,318 strings
fit and **no block** has every string fitting; at 2.5, none fit at all.

The 0x7Exx dictionary does not change this. Held at its measured 48.95% character coverage with
entries of comparable length it buys 0.28% at ratio 2.0 and nothing at 2.5, and its own bytes
exceed the whole block in 99% of blocks: the median block is 1,631 bits and a maximum-size
dictionary is 34,680.

**Consequence: offsets must move, so referrer completeness is required.** Preserving encoded
length is not an available strategy.

## 12. The tail record table and the lookup routine

MEASURED, Phase 10. 855 of 1,528 text sub-blocks carry a tail table. Deduplicated by text id
that is **9,371 records across 813 text ids**; the 12,870 figure counts duplicate copies of the
same id.

### Layout

Starting at `a` rounded up to a multiple of 4:

| Offset | Size | Meaning |
|---|---|---|
| `round_up_4(a)` | 4 | self pointer, must equal `a`, used as a validity check |
| `+4` | 4 | record count |
| `+8` | 8 each | the records |

### Record fields

| Field | Packing | Verified on |
|---|---|---|
| first u32 | `0xFFF00000 \| key` | 9,371 of 9,371 |
| second u32 | `(own text id << 20) \| value` | 9,371 of 9,371 |

`value` is a **bit offset from the block base**, not from `c`. Byte address is
`block + (value >> 3)`; the bit within that byte is `value & 7`. Expressed in the code stream's
own frame the offset is `value - c * 8`.

Gated against the corpus, every record resolves to the first bit of an END-terminated string:

| Reading | lands on a string start |
|---|---:|
| **bit offset from the block base** | **9,371 / 9,371, 100.00%** |
| same, +1 bit (companion) | 0 / 9,371 |
| same, -1 bit (companion) | 0 / 9,371 |
| bit offset from `c` (the Phase 8 reading, section 11) | 48 / 9,371, 0.51% |

All 9,371 land inside `[c, e)`. Out of bounds rate is 0.0000%.

### The key is a slot identifier

The key is a global name for a *role* in the script, not for a string. It repeats across
blocks, and where it repeats the blocks almost always agree on the text:

| Metric | Value |
|---|---:|
| distinct keys | 5,722 |
| keys used by more than one text id | 858 |
| records under a shared key | 4,507 |
| shared keys where every block decodes the same string | **853** |
| shared keys where the blocks disagree | 5 |

The five exceptions are the slots whose content is meant to vary per block: item appraisal
(`01652`, 163 blocks, 162 distinct strings), tarot readings (`01659`, 48 and 48), equip
reactions (`01649`, 83 and 17), and two two-way variants (`01648`, `01654`).

The "keys increment by 1" statistic from Phase 8 is **ordering-dependent and should not be
relied on**. Counting non-incrementing transitions over the same 9,371 records:

| Record order | non-incrementing |
|---|---:|
| natural scan order | 1,150 |
| sorted by (text id, record index) | 949 |
| sorted by key | 3,649 |

Phase 8 published 1,365, which none of these reproduces. The figure is not load bearing for
anything and is superseded: the key is a global slot identifier, so adjacency within one
block's table is not the frame the numbering lives in. In natural scan order 597 of the 1,150
non-incrementing transitions are the first record of a new block; the rest are blocks skipping
slots they do not use.

### The lookup routine at 0x8008F280

Two entry forms sharing one exit.

| `a0 >> 20` | Meaning |
|---|---|
| `0xFFF` | `a0 & 0xFFFFF` is a key. Locate the resident block, walk its tail table, linear scan for a record whose first u32 equals `a0`. On a match load the second u32 into `a0` and fall through. On no match return 0. |
| anything else | `a0` is already a resolved reference, `(text id << 20) \| value`. |

The resolver finds the block by linear scan over the struct table at `0x80100168`, comparing
`block+4` against the text id, then branches on `e` at `block+16`:

* `e != 0`, the Huffman case: returns `[bitpos:4][slot:4][addr:24]` where `addr` is
  `(block + (value >> 3)) & 0x00FFFFFF` and `bitpos` is `value & 7`. This is the exact form the
  decoder at `0x8008F3BC` consumes.
* `e == 0`: returns `block + value` as a plain byte address.

20 call sites reach the routine. 9 load `a0` from memory, 5 copy it from another register, 5
pass a compile-time constant and 1 takes it from a branch comparison. **Read the delay slot**:
the instruction after the `jal` executes before the call and frequently overwrites `a0`.

Because 15 of 20 sites build the key at runtime, the single `C021A0 <FFF0> <key>` occurrence
found in script data is consistent with this design rather than evidence of a missed encoding.

### Coverage

Each of the 9,371 records names exactly one string, and no string is named twice.

| Basis | Total | Referenced |
|---|---:|---:|
| all corpus strings | 17,234 | 9,371, 54.38% |
| **non-empty strings** | **15,318** | **9,371, 61.18%** |

0 records point at trailing residue. 293 text ids have no referenced string at all, and 5,947
non-empty strings have no referrer from this or any other measured system. The largest
unreferenced concentrations are text ids 0x0021 (1,086), 0x0023 (576), 0x0020 (382), 0x0024
(147) and 0x0124 (109).

---

## 13. The second referrer system, and the text-reference word

MEASURED, Phase 11.

### One resolver, two entry forms, one address word

Every text path in the executable converges on `0x8008F280` (section 12). Only that routine and
its own fall-through at `0x8008F354` treat the top 12 bits of a word as a text id; the other 67
`srl rd,rs,20` sites in the image mask `0x000F` or `0x03FF` for unrelated fields. There is no
second decoder and no second address format.

A **text reference** is one 32-bit word, and its sign decides everything:

| Sign | Meaning |
|---|---|
| negative (`0x8xxxxxxx`) | a raw Shift-JIS pointer into RAM |
| non-negative, top 12 bits `0xFFF` | `0xFFF00000 \| key`, resolved through a block's tail table |
| non-negative, otherwise | `(text id << 20) \| bit offset from the block base` |

The dispatch is exact rather than heuristic. The packed result puts `bitpos` (0 to 7) in bits 28
to 31, so bit 31 is always clear, while every PSX RAM pointer has it set. `0x8008F3BC` dispatches
on it: `bgez t1` selects the Shift-JIS path, otherwise the packed path.

`0x8008F3BC` is **one function of 253 instructions**, `0x8008F3BC` to its only `jr ra` at
`0x8008F7A8`. It is both the cursor and the Huffman decoder; the dual-base walk is at
`0x8008F550-0x8008F568` inside it (section 4). Do not describe it as a cursor *instead of* a
decoder.

### Where direct-form words live

| Source | Population | Verified |
|---|---|---|
| **type 26 sub-blocks** | 573 sub-blocks, 454 distinct by content, 60 to 2,820 bytes | 1,313 / 3,022 land on a string start, 43.45% (gate 30) |
| static executable tables | e.g. `0x800A9FA0` stride 48 fields +20/+24; `0x80019CE4` stride 16 field +8 | 51/51 and 162/162, 100.00% (gates 28, 29) |
| compile-time immediates | 5 resolver call sites, `lui`+`ori` | reference block 0x48C |

Type 26 layout is a bare array of 32-bit words, **4-byte field, 4-byte aligned, no header and no
count**. The caller supplies the index and the stride belongs to whatever record it is walking.
References spread across 271 distinct text ids.

Gate and companions for type 26:

| Test | Result |
|---|---:|
| on a string start | **1,313 / 3,022, 43.45%** |
| plus 1 bit | 0 / 3,022, 0.00% |
| minus 1 bit | 0 / 3,022, 0.00% |
| landing region | 100.00% in `[c, e)` |
| out of bounds | 0.0000% |
| shuffled control, 3 trials | 0.49%, 0.29%, 0.25% |

### Text blocks embedded in the executable

Two text blocks live in SLPM_869.16 rather than the archive, which is why their ids are absent
from the archive-derived corpus:

| VA | a | id | c | e | strings |
|---|---:|---|---:|---:|---:|
| `0x800AF1C8` | 6796 | 0x48C | 24 | 5464 | 779 |
| `0x800B0C5C` | 192 | 0x48D | 24 | 0 | 0 |

They parse with the ordinary six-int header and decode with the ordinary dual-base tree. 1,202
words in the executable reference block 0x48C, covering 591 of its 779 strings. Find them by
scanning the image for a six-int header with `c == 24`; exactly two match.

### The dialogue entry point

`0x8008687C(type, reference, flags)` is the central dialogue routine. It holds the reference in
`s4`, resolves it, and stores the packed result into the window struct:

```
0x80086A8C  jal   0x8008F280
0x80086A90  addu  a0,s4,zero      ; delay slot
0x80086A94  sw    v0,88(s0)       ; s0 = 0x800F4DE8, so this is 0x800F4E40
```

`0x8008EB80` is the thin NPC wrapper over it (`a0` forwarded as `a1`, window type 72), and
`0x8008FD78` is `copy_text_ref_to_buffer(dest, ref)`.

### Coverage and the per-block consequence

| System | strings referenced |
|---|---:|
| tail record tables (section 12) | 9,371 |
| type 26 sub-blocks | 955 |
| overlap | **0** |
| union | **10,326** of 15,318 non-empty, 67.41% |

Because bit offsets are absolute from the block base, changing one string's encoded length
shifts every later string in its block. A block is therefore only accountable if **every** string
in it has a known referrer:

| Basis | Blocks | All referenced | At least one missing |
|---|---:|---:|---:|
| all strings, excluding 181 dummy blocks | 925 | 254 | 671 |
| **non-empty only, excluding dummy blocks** | **925** | **264** | **661** |

**264 of 925** is the operative figure, against a per-string 67.41%. Measuring coverage per
string overstates the position by more than a factor of two, because the unreferenced strings are
spread thinly across many blocks rather than concentrated in a few.

---

## 14. The three referrer systems, and record extents

MEASURED, Phase 12. All three carry the same 32-bit word,
`(text id << 20) | bit offset from the block base` (section 13). They differ only in where the
word sits.

| System | Location | References | Discriminator |
|---|---|---:|---|
| 1 | tail record tables in type 40/42 blocks | 9,371 | 100.00% on a string start |
| 2 | **type 26**, word 0 of each 60-byte record | 955 | 98.28% trimmed |
| 3 | **type 44**, roster tables at an 8-byte stride | 1,539 | concentration, 13 ids vs 63 to 68 shuffled |

Mutual overlap is 1 reference in total. Union **11,864**, of which 11,856 are non-empty:
**77.40% of the 15,318 non-empty strings**.

The corpus carries this per string as a status field (`LOOKUP`, `TABLE`, `ROSTER`,
`UNRESOLVED`, `EMPTY`, `DUMMY`) together with the referrer's address, and per block as a
`CLEAN` or `BLOCKED` verdict in `meta/blockindex.txt`. There is deliberately no `ORDINAL`
status: none was established, so `UNRESOLVED` covers both possibilities.

### Extent matters more than the reading

Sweeping a whole sub-block and rating the words whose top 12 bits happen to be a valid text id
**understates the hit rate and does not change coverage**. For type 26 the whole-sub-block rate is
43.45% and the correctly-scoped rate is 98.28%; both yield the same 955 references.

**Find the record stride before quoting a rate.** For type 26 the stride is confirmed without
touching the corpus: all 454 distinct sub-blocks are an exact multiple of 60 bytes, and word
residues 3 through 11 never hold a valid text id in any of the 2,425 records.

| type 26 residue | hit | miss | invalid id | rate |
|---:|---:|---:|---:|---:|
| **0** | 1,261 | 12 | 1,152 | **99.06%** |
| 1 | 44 | 10 | 2,371 | 81.48% |
| 2 | 8 | 1 | 2,416 | 88.89% |
| 3 to 11 | 0 | 0 | 2,425 each | - |
| 12 to 14 | 0 | 1,686 | - | 0.00% |

Residues 1 and 2 carry a reference in only 54 and 9 records but hit at 81% and 89% when they do,
so they are genuine and sparse.

### When the absolute rate is not the discriminator

Type 44 sub-blocks are large (up to 340 KB) and mostly other data, so its references rate only
1.71% against a shuffled 0.15%. The rate is not what settles it. **Concentration is**: the real
data names 13 text ids, a shuffled control of the same bytes names 63 to 68. Noise spreads across
the id space, a pointer table does not.

Its plus and minus one bit companions fall to 0.01%, a hundredfold collapse, and 98.0% of hits
land in `[c, e)`.

Type 44 references, resolved: id `0x0021` 1,086 of 1,086 strings, `0x0022` 7 of 7, `0x0020` 380
of 395, `0x0026` 55 of 59. The dominant sub-block holds an 8-byte-stride roster whose consecutive
records resolve to consecutive string indices, `なし`, `ラスタ`, `ゴルエイ`, `セシル`.

### Coverage, and why the per-block figure is the operative one

Bit offsets are absolute from the block base, so changing one string's encoded length shifts every
later string in its block. A block is accountable only if **every** string in it is accounted for.

| Basis, non-empty strings | Blocks | Complete | At least one unaccounted |
|---|---:|---:|---:|
| all blocks | 1,106 | 268 | 838 |
| **excluding 181 dummy blocks** | **925** | **266** | **659** |
| excluding dummy and 285 wholly-unreferenced ids | 819 | 266 | 553 |

**266 of 925.** Per-string coverage rose from 67.41% to 77.40% between Phase 11 and Phase 12 and
the per-block count moved from 264 to 266. **The two measures are close to independent**, because
new references tend to land in blocks that are already complete or already empty. Quote the
per-block figure when the question is what can be edited.

3,462 non-empty strings remain unaccounted: 1,330 in the 285 wholly-unreferenced ids, and 2,132
scattered inside otherwise-referenced blocks. Scattered misses are the signature of a system not
yet found, and three such systems have now been found the same way, by locating a record stride.
