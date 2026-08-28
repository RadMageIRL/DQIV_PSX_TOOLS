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
| 8 | u32 | destination, or zero; the meaning depends on type, see below |
| 12 | u16 | flags |
| 14 | u16 | type |

### CORRECTED, Phase 45: the field at +8 is polymorphic

Phase 28 recorded this field as follows, and the claim is kept here in full because part of it is
still right:

> The field at +8 was carried as unknown until Phase 28. It is a **destination address in main
> RAM**: 21 distinct values, all in the 0x8001xxxx to 0x801Exxxx range, nonzero on **965 of
> 23,828** sub-blocks and zero on the rest.

**The count is 20 distinct values, not 21, and they are not all RAM addresses.** MEASURED across
all 23,828 sub-blocks:

| reading | values | which |
| --- | --- | --- |
| **main RAM address** | 11 | all in `0x80011F08` to `0x80210000`, types 44, 45, 46, 47 |
| **too small to be an address** | 7 | the values 1 to 7, every one of them type 32 |
| **neither** | 2 | `0x04000380` on the three atlases and `0x01034380` on the three CLUTs, both type 1 |

So the field is a destination whose **interpretation depends on the sub-block type**, and reading
it as a RAM address unconditionally is what hid the type 1 case.

**On the two type 1 values, INFERRED and not measured.** Under the usual PlayStation packing of
`(y << 10) | x`, `0x04000380` gives x = 896, y = 0 and `0x01034380` gives x = 896, y = 208. The
atlas is 256 pixels wide at 4bpp, which is 64 VRAM halfwords, and its 16,128 bytes are 8,064
halfwords, which is exactly 64 by 126, its own row count. The CLUT block's 512 halfwords are
exactly 16 by 32. Both land at x = 896, and the font 2 glyph cache observed at `0x800874A0` uploads
to x = 896 + (s1 >> 2), y = 154 + s6, between them.

**The companion for that reading fails and the reading is therefore not established.** Under the
same packing the genuine RAM addresses also decode to plausible coordinates, `0x80011F08` giving
(776, 71). The packing alone discriminates nothing; only the value range does. No code that
consumes the field for a type 1 sub-block has been read.

**Alignment.** Sub-block start offsets are not stored anywhere; they are implied by accumulating
`dlen` from the sub-block table, and condition 4 of the validity filter requires the lengths to
sum exactly to the block total. There is therefore no way to express a gap or a pad between
sub-blocks.

**Every sub-block in the shipped archive has a `dlen` that is a multiple of 4 and starts 4-byte
aligned: 23,828 of 23,828, zero exceptions.** MEASURED, gate 39. This is load-bearing, not
decorative. The engine reads the text block header with `lw`, and on an R3000 an unaligned `lw`
raises an Address Error. Any tool that rewrites a sub-block must land on a multiple of 4 or it
will misalign every sub-block after it. See section 16 for what this cost.

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
| 0x7F02 | new line; see below | | 0x7F2B | ホイミン |
| 0x7F04 | name decorator, starts named dialog; see 15c | | 0x7F2C | オーリン |
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

### 0x7F01 and 0x7F02, the two new lines

**0x7F01 was absent from both tables above.** It is a plain new line, and it is
what the executable's own text block uses.

Read from the decoder rather than inferred from position. The handler at
`0x80088A48`:

```
lw    v1, [0x800FFA40]     ; pen y
lw    a0, [0x800E95B0]     ; line height
addiu v0, zero, 8
sw    v0, -1476(s3)        ; pen x = 8
addu  v1, v1, a0           ; y = y + line height
sw    v1, [0x800FFA40]
```

**The pen resets to x = 8, not 0.** That is the 8-unit left inset a window
carries on each side, and it is worth noting because the same number can be
reached from window arithmetic alone; here it is visible directly in the code.

**CORRECTED: 0x7F02 is not "new line plus tab".** The width routine at
`0x800886D8` tests a RANGE, `0xFF01 <= code <= 0xFF02`, and treats both
identically: same reset to x = 8, same advance by one line height. Nothing in
either path adds a tab or a different indent. `0xFF02` is compared exactly once
in the whole executable, in that range test, so the executable's own dispatch
never special-cases it.

**The two differ by which renderer consumes the string, not by what they mean.**
Measured across the whole disc:

| where the string lives | 0x7F01 | 0x7F02 |
|---|---:|---:|
| archive scene blocks, 1,528 of them | **0** | **166,134** |
| the executable's UI block | **144** | 1 |

So scene dialogue uses one and the interface uses the other, essentially without
exception. An authored string should follow the convention of the block it is
going into; both will break a line.

**0x7F0A remains as the table above states.** Its handler was not read, and the
"blinking cursor" reading is not contradicted by anything measured here.

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
| length | `(v >> 20) & 0x7FF` | **11 bits**, in sectors. **Max expressible `nsec` is 2047** |
| flag | `v >> 31` | **1 bit. PRESERVE IT; it is not part of the length** |
| lba | `v & 0xFFFFF` | 20 bits, **absolute disc LBA** |

> **CORRECTED IN PLACE, 2026-08-27, AND NO FIGURE BELOW CHANGES.** This table read
> `length = v >> 20`, 12 bits, with no flag row. **MEASURED Phase 113, from the reader at
> `0x800592CC`, which does `srl 20` then `andi 0x07FF`: the length field is ELEVEN bits and bit 31
> is a separate flag.** Every count in this section was taken over well-formed shipped entries,
> where bit 31 is clear and the two decodes agree, **so nothing measured under the old form is
> retracted.** What the old form would break is a WRITE: **an entry rebuilt as `length << 20 | lba`
> drops bit 31**, and Phase 113 lists that among the corrections that would have corrupted a build.

### Relocation: what rewriting one of these entries is proven to do

**A block is relocated by rewriting its table entry. Four bytes. That is the whole mechanism**, and
`docs/CODEX.md` is not where this belongs because it is a format fact.

> **THE LABEL, and it is to be carried in these words: the loader honors a changed `lba` --
> MEASURED, for the blocks tested, with a failing companion. That EVERY entry does -- INFERRED from
> format uniformity.**

**MEASURED on hardware:** one block relocated with its entry updated plays; the same block with the
entry left stale hangs at the chapter card; a 16-copy group with all 16 entries updated plays; the
same group with one entry stale plays normally, **predicted in advance**; and 23 blocks relocated on
a real build with the table invariant at 3,241 and zero unmapped entries.

**INFERRED: that all 3,241 entries behave identically.** Four blocks and one group were exercised.

**AND THE WARNING THAT COMES OUT OF THE SAME PILOT: BOOTING CANNOT DETECT A PARTIAL RELOCATION.**
Fifteen good copies mask one bad one, and **71 of 72 byte-identical block groups hold no drawable
text at all**, so for those a missed copy is invisible to any amount of play testing. **The defense
is the build-time invariant over the whole table, not a play test.**

**Two further consequences for anyone writing an entry**, both MEASURED Phase 113: **`nsec` is
stored TWICE**, in the table entry and in the block header at `+4`, and both move for every copy;
and **the table holds 3,281 usable entries, not 3,283** -- the last two words are overlay load
addresses and writing them corrupts the build.

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

### 7b. Slack belongs to the SECTOR, not to the sub-block

MEASURED on sector 34871. This dissolved a blocker that had stood since Phase 108, and the
reasoning generalizes further than the one sector does, so it is recorded rather than the
outcome alone.

> **A tight sub-block with a compressible neighbor is not a tight sector.**

A sector holds several sub-blocks and the cap applies to their TOTAL. Reading slack per
sub-block therefore reports a blocker that may not exist:

| | measured | read per sub-block | read per sector |
| --- | --- | --- | --- |
| sub 15, the carrier being edited | **+8** against **4 bytes** of slack | **BLOCKED**, and no `max_chain` rescues it | still +8, and it does not matter |
| sub 3, an untouched neighbor | repacks losslessly at **-108** | irrelevant, nobody is editing it | **pays for sub 15 nine times over** |
| the sector | **325,240** against a cap of **325,344** | | **FITS** |

The +8 is real and a wider chain depth does not remove it. What removes the blocker is
recompressing a neighbor that had no reason to be touched.

**THE CONSTRAINT, and it is why this is not a general license.** It requires a neighbor that
repacks **losslessly**, and that must be **verified per sector rather than assumed**. Not every
neighbor has room and some make it worse: in this same sector **sub 4 would overflow it at
+464**, and nothing required touching sub 4. A neighbor is a lever only after its own identity
repack has been measured.

So before declaring a sector blocked: sum the sector, not the sub-block, and check whether any
untouched neighbor repacks smaller. INFERRED from per-sub-block measurement; not built.

---

## 8. Glyph atlas

**Font and text rendering detail lives in `docs/FONTS.md`, which is the authoritative
location for it.** It is not duplicated here.

The atlas is a 4bpp image carried in the archive's type 1 sub-blocks. Its geometry, cell
layout, the two-glyphs-per-cell packing and the contents inventory are in `docs/FONTS.md`.

What belongs in this section is the one type 1 finding that is not about fonts.

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

## 9b. Raw sector format, EDC and ECC

MEASURED, Phase 16. Verified by regenerating and comparing against the original mastering.

The disc is 156,487 raw sectors of 2352 bytes, all Mode 2. **Exactly 4 are Form 2**, at LBA 12 to
15 in the system area; everything else including the whole archive (LBA 362 to 156,336) is Form 1.

| Range | Mode 2 Form 1 | Mode 2 Form 2 |
|---|---|---|
| `0..12` | sync | sync |
| `12..16` | header: min, sec, frame, mode | same |
| `16..24` | subheader, 4 bytes twice | same |
| `24..` | 2048 bytes user data | 2324 bytes user data |
| EDC | `[2072, 2076)`, over `[16, 2072)` | `[2348, 2352)`, over `[16, 2348)`, **optional** |
| P parity | `[2076, 2248)`, 172 bytes | none |
| Q parity | `[2248, 2352)`, 104 bytes | none |

EDC is a CRC-32, polynomial `0x8001801B` reflected, init 0, no final xor. ECC is Reed-Solomon over
GF(2^8) with primitive polynomial `0x11D`, computed with **the 4 header bytes treated as zero**,
which is what makes Mode 2 ECC independent of sector address.

Two details that are easy to get wrong and were:

* **P must be in place before Q is computed.** The Q pass indexes up to `52 * 43 = 2236` bytes from
  `sector+12`, which runs past the 2064 bytes of data into the P parity at 2076. Computing Q over a
  2064-byte buffer is an out-of-range read, not a subtly wrong answer.
* **A zero Form 2 EDC means disabled and must be left alone.** Rewriting it changes bytes the
  mastering deliberately left clear.

`dq4/edcecc.py` reproduces the original mastering **byte for byte on every sector tested**: 2,993
sampled Form 1, all 4 Form 2, and all 155,975 archive sectors during the Phase 16 null build. So
regenerating EDC/ECC over unchanged data is a no-op on this disc, and any byte difference after a
rebuild is a real content difference rather than a parity artifact.

`dq4/discbuild.py` writes a file back into a copy of the image, same size and in place only. The
source is opened read-only and never written.

**Gate 1 fails on any intentionally modified disc, by construction**, because it pins the
source image's SHA-256. That is the gate working, not a build defect. When verifying a build,
expect gate 1 to fail and every other gate to pass; gate 22, which rebuilds the whole corpus
from the output disc, is the one that proves the content survived.

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

**RESOLVED, Phase 26: the per-kanji record table at `d + 32`.** It is the block's own **font 2
glyph table**. Full description in section 15. Every observation recorded here while it was
unknown turns out to be correct and is now explained:

- "One 8-byte record per kanji leaf" is a chain entry: u32 descriptor, u16 character code at
  +4, u8 width at +6, u8 height at +7. For text id 0x006C the first entry sits at exactly
  `d + 32` and there are 15 of them.
- "The u32 is block-local, 863 of 897 differ" is right, and now obvious: it is an **offset into
  the block's own glyph payload**, whose position is named by the font record at `d + 4`. Being
  block-local is the whole point.
- **The withdrawn width and height reading was correct and is reinstated.** 0x0D0C really is 12
  wide by 13 high, and 0x080B really is 11 by 8 on the record carrying 一, both confirmed
  directly. The withdrawal reasoned that "the atlas renders kanji at 8 pixels wide, so a
  12-wide glyph dimension cannot describe them". True of font 1, and irrelevant: these are
  **font 2** glyphs, which are proportional and up to 16 x 16. MEASURED, Phase 26.

That the table is kanji-related does hold up. Dragon Warrior VII has 2,122 sub-blocks with the
same six-int text header structure, and every one carries the same `[d, a)` header shape with
the record area **empty**, 36 bytes in all 2,122, leaving no room for records and no payload
region at all. A game with no kanji has the structure and none of the content. MEASURED,
Phase 6.
Note that `p1` does **not** point at these records; for text id 0x006C `p1` is `d + 28` and the
records begin at `d + 32`.

**The 60 01 01 80 band internals.** Identified as STR video (section 8). The frames themselves
are not decoded here.

**RESOLVED, Phases 21 to 26: the fullwidth font.** There is a second font, and the reason no
sweep of the archive ever found it is that **it is not in the archive**. Font 2 is registered
from a fixed address inside `SLPM_869.16`, and each map text block ships its own supplement.
Section 15. The sweep was sound; it was looking in the wrong file.

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

### RETRACTED: "Type 1 blocks are not the English game's text font"

**This negative result is wrong and is withdrawn in full.** It is kept visible because a
published negative result that is wrong is worse than none at all: it tells the next person not
to look. What it said:

> "That atlas contains 13 Latin capitals: Y, W, U, S, Q, O, M, K, I, G, E, C and A. The exact
> complement of Dragon Quest IV's thirteen. A shipped English game cannot render its text from
> half an alphabet, so the type 1 block is not the text font in either game.
>
> The absence was **proved, not assumed**, with a calibrated threshold:
>
> | Comparison | Score, max 112 |
> |---|---:|
> | a letter against itself | **112** |
> | different letters, same font, mean of all pairs | 50.8 |
> | different letters, same font, **worst case** | 32 |
> | different letters, same font, **best case** | **91** |
> | **best cross-atlas match found, searching every pixel offset** | **82** |
>
> Every cross-atlas best match falls below the 91 same-font ceiling, and every one lands on a
> **shape neighbor**: B matches C, P matches O, N matches M, R matches Q. That is the signature
> of absence, not of a font revision.
>
> A second hypothesis, that the run turns around and the missing letters follow, was tested by
> matching the next thirteen slots against the expected letters in order. Mean score 42.2
> against a null of 41.1. No signal."

**What was actually measured.** The letters were never absent. Every cell of the atlas holds
**two glyphs, one in each 2-bit plane of the 4bpp pixel**, selected by bit 0 of the font
descriptor. Every comparison above was run against the superposition of two letters. DQ4's
atlas carries all 26 capitals, all 26 lowercase and all 10 digits, and English text has since
been rendered in-game from it (section 15, and the screenshots in `docs/images/`).

The observation that DW7's atlas holds "the exact complement" is the same error seen from the
other side: that read resolved the opposite plane. INFERRED, not re-measured: DW7 almost
certainly carries all 26 too. The observation that both games share a layout convention stands;
only the conclusion drawn from it was wrong.

**Why the method produced a confident wrong answer.** The calibration was sound and the
arithmetic was correct. Every number in that table is reproducible. The fault is that the
whole comparison ran on a decoding of the image that was wrong, and no amount of calibration
inside a wrong decoding can detect that. Worse, the calibration made the result feel earned:
a self-112 / ceiling-91 / best-82 spread looks like exactly the kind of evidence that should
settle a question.

The shape-neighbor pattern that read as "the signature of absence" was the real tell and was
misread. B scoring against C, P against O, N against M, R against Q is what you get when each
cell contains **both** letters of an adjacent pair: B and C share cell 38, and the superposition
resembles either one. That pattern was evidence of superposition and was interpreted as
evidence of absence.

The lesson is in section 16. A measurement can be correct, calibrated, reproducible and still
answer a question you are not asking, if the representation it runs on is wrong.

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

### RETRACTED: "C0 21 A0 is not a three-byte opcode"

**This negative result was wrong and is withdrawn.** It is left here rather than deleted so the
mistake stays visible, but nothing in it should be relied on. The correct account is in section 14
and gate 37.

What Phase 12 recorded, and what was wrong with it:

> Type 39 scripts are word-aligned u32 streams with `0xA0` as the top byte of the command class.
> Searched as a three-byte pattern, `C0 21 A0` straddles a word boundary and matches 92,681 times
> by chance. Word aligned, the real command is `0xA021C000`, occurring 15,207 times.

15,207 is not the population. It is the quarter of the occurrences that happen to sit at offset 0
mod 4; the same byte pattern occurs 15,207 / 6,737 / 4,515 / 10,735 times at offsets 0/1/2/3, a
total of 37,194. The stream is byte-aligned, so forcing word alignment reads a quarter of it and
classifies the remaining three quarters as noise.

**`C0 21 A0` is a three-byte command, exactly as Mandy Wilkens published it.** Her documentation
was correct as written; the error was entirely in this project's reading of it, and the earlier
text should not be read as a correction to her work.

The companion claim, that the argument is a `<u16 bit offset> <u16 text id>` pair, was also
tested against the wrong shape. The argument is a single packed u32,
`(text id << 20) | bit offset`, which is the same word the resolver at `0x8008F280` already
accepts. Section 14 carries the gate.

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

### Building a tree, not just reading one

MEASURED, Phase 17. `dq4/treebuild.py` emits a tree in the engine's form; the library's own
decoder walks every array it produces (1,528 of 1,528), and build-encode-decode returns the corpus
text on every text sub-block (1,528 of 1,528).

Three layout facts hold on **all 1,106 distinct blocks** and must be reproduced by any emitter:

| Invariant | Holds |
|---|---:|
| `root == m - 1`, internal nodes numbered in creation order so the root is last | 1,106 / 1,106 |
| `base == e + 10`, the pair array follows the 10-byte tree header | 1,106 / 1,106 |
| `npairs == 2m + 1`, m internal nodes, 2m children, one pad pair | 1,106 / 1,106 |

Internal node `nn` owns slots `pair[nn]` and `pair[m + nn]`, so with numbers 0..m-1 every slot
below 2m is exactly one node's child.

**Heart Beat's builder never emits a depth-1 code.** Their minimum leaf depth is 2 to 5 on every
block; an ordinary optimal Huffman produces a 1-bit code in 181 of them. Those 181 are *exactly*
the blocks where an optimal tree beats theirs, by exactly 9 bits each, with zero exceptions in
either direction. Corpus-wide their coding is within **0.034%** of optimal (4,876,608 bits against
4,874,947), so this is the only systematic difference.

Constraining every leaf to depth 2 or more is the same problem as packing the symbols under a
root with **four** slots, since sum 2^-(L-2) = 4. So the constrained optimum is reached by
running ordinary Huffman merges until exactly four items remain and hanging those at depth 2.
That is what `treebuild.build(freqs, min_depth=2)` does.

**An equally optimal tree usually moves string offsets.** Total encoded length matches theirs on
916 of 1,106 blocks, but every string start survives on only **142 of 1,106**: the same total is
redistributed between symbols. To re-encode a block while freezing its offsets, build from the
original's code **lengths** (`build_from_lengths`) rather than from frequencies.

**`build_from_lengths` does not reproduce their pair arrays.** It matches the code **lengths**,
which is what freezes the offsets, but the emitted array is byte-identical to the original on
**0 of 1,528** text blocks. A claim that it matched 1,097 of 1,106 has circulated in this
project's own notes; that figure was about length totals, not arrays. MEASURED, Phase 27.

**Arrangement is not load-bearing.** Both builders satisfy every structural convention the
originals do, checked field by field: `root == m - 1`, the highest node value referenced is
`m - 2`, no child's node number is greater than or equal to its parent's, every node number
below the root is referenced exactly once, the pad pair at index `2m` is 0x0000, and leaf values
sit below 0x8000 with nodes at or above. A tree built from frequencies decodes correctly under
the engine's own walk, transcribed instruction for instruction, and every referrer in the block
terminates on END. MEASURED, Phase 27. If a rebuilt block misbehaves, the tree is not the first
place to look; see section 16.

Bits per symbol over all 1,528 sub-blocks: originals **7.8061**, built trees **7.8055**. Phase 1's
collapsed tree measured 1.06 on this basis, so it remains the degeneracy check.

### The suffix rule: which strings can be re-encoded

MEASURED by computation, Phase 14, gate 36.

Offsets are absolute from the block base, so lengthening string i shifts strings i+1 through
N-1 and **nothing before i**. String i itself does not move, so its own referrer is never
invalidated. Therefore:

> **A string is editable if and only if no unresolved string appears after it in its block.**

If a block's unresolved strings sit at indices `{u1 < ... < uk}`, every string from `uk` onward
is editable, `uk` included, and everything before `uk` is frozen. The operative question is where
the maximum sits, not whether the set is empty.

| Basis | editable strings | editable characters |
|---|---:|---:|
| whole-block rule (Phase 12) | 3,112 | 139,192 |
| **suffix rule (Phase 14)** | **11,437 of 15,243** | **488,490 of 667,904, 73.14%** |

**A zero-symbol string is never a barrier**: it encodes nothing, so it cannot grow. A
control-only string is a barrier in principle, because its codes are real encoded symbols; the
two on this disc (13 and 15 bits) never set a cutoff, so both bases give identical totals.

Unresolved strings **cluster at low indices**, which is why the rule pays. 67.1% of the 659
affected blocks have `uk` in the bottom three tenths against 23.7% for a shuffled control that
keeps each block's unresolved count; 9.6% in the top three tenths against 43.3% shuffled.

| Population | Blocks | Characters | Editable within |
|---|---:|---:|---:|
| fully resolved | 266 | 139,192 | 100.0% |
| **cutoff** | **531** | **444,615** | **77.5%** |
| tail-only, `uk = N-1` | 128 | 84,097 | 5.6% |

`meta/blockindex.txt` carries `uk`, `resolution` and `editable strings` per block; the
side-by-side carries `EDITABLE` per string. **This does not soften section 11b**: English still
does not fit the original bit budget, so an edited string does move everything after it. The rule
identifies where that movement is harmless because nothing measured points into the region that
moves.

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

### 11c. The alphabet cost model, as an equation

MEASURED on `0x0485`, both relations exact. This is the size rule stated arithmetically rather
than as a caution, and it is what forces a tight block's dictionary to be emptied.

A block's header carries the payload start `d` and the block end `a`. For a tree over `L`
distinct symbols:

```
npairs = 2L - 1                  a Huffman tree over L leaves has 2L - 1 nodes
d      = e + 10 + 2*npairs       so d grows by 4 for every distinct symbol added
```

**`d` CANNOT SIMPLY MOVE.** The records in `[d, a)` hold **block-relative offsets**, so shifting
`d` invalidates every one of them. `e` is therefore not free either: it is pinned by the same
constraint from the other side. What absorbs the change is the code stream, and the general form
is:

```
code stream bytes = (a - d) - c        with d = e + 10 + 2*(2L - 1)
                  = (a - e - 10 - 2*(2L - 1)) - c
```

so, holding `e` and `a` fixed and letting `L` vary:

> **EVERY DISTINCT SYMBOL COSTS FOUR BYTES OF CODE STREAM**, before it has encoded a single
> character.

`4L` is the rule and it is general. Any constant that appears when this is written out for one
block (an `848` for `0x0485`, where `a = 1048` and `d = 856`) is that block's `a` and `e`
arithmetic and does not transfer.

**The consequence for authoring is the whole of it.** A shorter line built from rarer characters
is bigger than a longer line built from characters the block already carries, because the rare
character pays 4 bytes of tree before it pays anything for itself. Reduce the ALPHABET before
shortening the text, and empty a phrase dictionary before trimming prose.

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

## 12b. The per-block font records, and reclamation

MEASURED, Phase 51. The region `[d, a)` of a text sub-block holds a font record and the table it
names. 1,337 of the 1,528 text sub-blocks have one; 191 have `d == 0` and none at all.

### Layout, identical in DQ4 and in DW7's Japanese and English builds

| Offset from `d` | Size | Field | Measured |
|---|---|---|---|
| `+0` | 4 | record count | 1 in 1,337 of 1,337 |
| `+4` | 4 | buckets, **block-relative** | `d + 28` in 1,337 of 1,337 |
| `+8` | 4 | glyphs, **block-relative** | `buckets + 2 * modulus` |
| `+12` | 2 | modulus | 8 distinct values, `{2: 1001, 23: 79, 31: 68, 3: 59, 5: 58, 11: 42, ...}` |
| `+14` | 2 | font id | **2 in 1,337 of 1,337.** No archive block registers font 1 |
| `+16` | 2 | | 2 |
| `+18` | 2 | entry count | 108 distinct values |
| `+20`, `+22` | 2, 2 | | 16, 16 |
| `+24`, `+26` | 2, 2 | cell_w, cell_h | **0 and 0 in 1,337 of 1,337**, which selects the 8-byte chain stride |
| `+28` | `2 * modulus` | the bucket array, self-relative halfword heads | |
| then | | chains at stride 8, then the glyph bitmaps, up to `a` | |

The two block-relative offsets are why this region is fragile: **they are measured from the block
base, so anything that moves `d` must move them too.**

### The lookup, read to its `jr $ra`

`0x8008F7B0`. Twelve registration slots of 32 bytes at `0x80100168`; per slot, `+0` is the block
base, `+4` the record array and `+20` the record count. For each record it compares `+10` against
the requested font id, divides the character code by the modulus at `+8`, doubles the remainder and
indexes the bucket array at `base + [record+0]`. **A zero bucket halfword is a miss**, taken without
dereferencing anything; a zero code halfword inside a chain ends it the same way. On total failure
the routine returns 0.

### Reclamation

Reducing the region to a stub is what Heart Beat did on the English build of DW7: **all 877 of its
English text blocks carry a records region of exactly 36 bytes, one distinct size.** The 36 is
`32 + 2 * modulus` with the modulus at 2, so:

* the 24-byte record header survives,
* the two block-relative offsets move with `d`,
* the entry count at `+18` goes to 0, so the u32 at `+16` reads 2,
* **the bucket array is present and zeroed, not removed**, and
* the glyph area is emptied to 4 bytes.

**The modulus must never be zeroed.** `divu` by it is executed unconditionally and guarded by an
explicit `break 0x1C00` two instructions later, so a zero modulus traps rather than missing.
**DW7 forces the modulus to 2 on all 877 blocks, including the 22 where the Japanese carried 3 or
5**, which is a measured precedent for changing it and is what makes the size fixed rather than
proportional.

Reclaiming removes the block's own glyphs permanently, so **a reclaimed block cannot be left partly
Japanese.** DQ4's 0x0186 uses 100 codes with no entry in the global font 1 table; its English needs
none of them.

Reproduced on DQ4 and proven on hardware, Phase 51.

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
| 4 | **type 39**, the 3-byte command `C0 21 A0` | 3,202 | 89.9% of valid-id arguments, +/-1 bit at 0 |

Mutual overlap is 1 reference in total. Union **11,864**, of which 11,856 are non-empty:
**77.40% of the 15,318 non-empty strings**.

The corpus carries this per string as a status field (`LOOKUP`, `TABLE`, `ROSTER`,
`UNRESOLVED`, `EMPTY`, `DUMMY`) together with the referrer's address, and per block as a
`CLEAN` or `BLOCKED` verdict in `meta/blockindex.txt`. There is deliberately no `ORDINAL`
status: none was established, so `UNRESOLVED` covers both possibilities.

### System 4: the cutscene command in type 39 scripts

MEASURED, Phase 15, gate 37.

**`C0 21 A0` is a THREE-BYTE command on a BYTE-ALIGNED stream**, followed by a four-byte packed
`(text id << 20) | bit offset`, the same word the resolver at `0x8008F280` takes in its
non-sentinel form.

```
+0x100E  C0 21 A0        command
+0x1011  91 0F C0 06     LE u32 = 0x06C00F91 = (0x06C << 20) | 0xF91
```

| Test | Result |
|---|---:|
| `C0 21 A0` occurrences over 927 distinct scripts | 85,152 |
| argument names a real text id | 3,769 |
| **landing on a string start** | **3,388, 89.9% of valid-id arguments** |
| plus 1 bit / minus 1 bit | **0 / 0** |
| out of bounds | 0.45% |
| shuffled control | 2 hits of 509 commands |

**CORRECTED, Phase 15.** Phase 12 recorded that `C0 21 A0` is not a three-byte opcode and that the
real unit is the word-aligned `0xA021C000` with 15,207 occurrences. That is one alignment of four:
the same byte pattern occurs 15,207 / 6,737 / 4,515 / 10,735 times at offsets 0/1/2/3 mod 4, total
37,194. Forcing word alignment reads a quarter of the stream and classifies the rest as noise.
Mandy's three-byte form was correct.

Binding: a script addresses **exactly one** text block, and the script and its text block always
ship in the **same archive block** (463 of 463). The text id is an operand in every command, not a
script-level constant.

`0x80102448` is the **end of BSS**, referenced once at `0x80091900` in the BSS-clear loop before
the entry point. Script data loaded there is a heap allocation, so the script pointer is dynamic
and has no static reference to trace.

### The instrument defect this phase uncovered

`lzs.decompress(src)` takes one argument. Three call sites passed two, inside
`except Exception: continue`, so every compressed sub-block raised TypeError and was skipped in
silence: **922 of 976 type 39 sub-blocks went unmeasured for three phases.** Types 26, 40 and 42
have no compressed sub-blocks, so the corpus and the system 1 to 3 totals were unaffected and
re-measure byte-identical. What the bug invalidated was the type 39 negative result.

**A `try/except Exception` around a measurement turns "my code is wrong" into "the data contains
nothing", and reports them identically.** The silent skip is removed rather than fixed in place.

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

---

## 15. Rendering

**Font and text rendering detail lives in `docs/FONTS.md`, which is the authoritative
location for it.** It is not duplicated here.

Both font tables, the chained hash lookup, descriptors, the atlas path, the run length
payload, the per-block font supplement and the leaf space wall are in `docs/FONTS.md`.

What remains here is the one subsection that is about compression rather than rendering.

### 15.8 Recompression and alignment

`lzs_comp.compress` takes a `max_chain` bound on its hash chain walk. Varying it from 1 to 64
produces **35 distinct output lengths** for the same input, every one round-tripping byte
identically and every one preserving the +3 overrun. Alignment (section 2) is therefore reached
by **choosing a search depth**, not by padding.

Padding does not work: appending one byte lands on an odd length, and two or three move the
overrun from +3 to +6 or +21, which gate 20 rejects.

#### Zero padding is not inert, and this is the sharpest edge in the whole build path

**Read this before writing anything that fills a sector.**

A sub-block that recompresses SMALLER than the bytes it replaces leaves its sector short. The
obvious repair is to append zero bytes to the largest edited sub-block until the sector is full
again. **That repair corrupts the block, and it does so silently.**

> **The padding lands inside the compressed stream, so the decompressor READS IT AS FURTHER LZS
> COMMANDS.** A run of zero bytes is a valid sequence of flag bytes, so the decoder emits real
> output past the declared length. **MEASURED: two sub-blocks reached +51 and then +108 bytes of
> overrun this way**, against a shipped-disc maximum of +3.

Nothing about a padded block looks wrong. It is the right length, it is 4-byte aligned, it
decompresses without raising, and its declared length is untouched. **The only thing that catches it
is the overrun distribution, gate 20**, which is one of the checks derived from a statistic the
shipped game exhibits rather than from our own model of the format. Section 16.

**THE REMEDY IS TO ASK FOR A BIGGER ENCODING, NOT TO PAD A SMALL ONE.** The paragraph above is what
makes that possible: `max_chain` yields 35 distinct output lengths for the same input, all of them
correct. So rather than compressing to the smallest output and padding the difference, compress with
a **size floor** and take the smallest admissible encoding **at or above** it. The sector arrives
full because the encoding fills it, and there is no padding to be misread.

Three constraints on using it, and they are the difference between a remedy and a new defect:

- **A size floor is a remedy for ONE constrained sector, not an encoding policy.** Applied by
  default it inflates every block on the disc for no reason.
- **The default path must stay "smallest admissible encoding", as its own branch.** Keeping the
  floor case separate is what makes "absent a floor, this returns exactly what it returned before"
  structural rather than an argument.
- **An unsatisfiable floor must RAISE, never fall back to padding.** Falling back reintroduces the
  exact defect the floor exists to prevent, at the one moment nobody is watching. Every candidate
  encoding is still checked for a byte-exact round trip, an unchanged overrun and a length divisible
  by 4 before the floor is even consulted.

---

## 15b. What the corpus does NOT contain

The corpus decodes every Huffman text block on the disc. That is not the whole script, and the
claim that it is has been overstated. MEASURED, Phases 32 and 33:

| population | characters | in the corpus |
|---|---:|---|
| Huffman text blocks, types 40 and 42 | 668,447 | yes |
| type 46 string pools: arena, shops, church, memory card | 110,646 | **no** |
| types 6, 44, 8 and others | 24,561 | **no** |
| loose Shift-JIS in `SLPM_869.16` | 573 | **no** |
| block 0x048D, raw Shift-JIS with `e == 0` | 80 | **yes, since Phase 33** |
| the global monster bestiary | unknown | **not located** |

**At least 20.2 percent more text exists outside the text blocks than inside them.** The figure
is a floor: it counts only runs of valid two-byte Shift-JIS whose kana density is 0.6 or higher.
Without that filter the same sweep returns 1.26 million characters, because compressed graphics
and audio produce valid Shift-JIS byte pairs by chance.

**A text block with `e == 0` carries no Huffman tree.** Its body is raw NULL-terminated
Shift-JIS. Exactly one exists, 0x048D at VA `0x800B0C5C`, holding the fullwidth Latin alphabets
and the digit and hex sets, and it read as empty for thirty-two phases because the generator
only knew how to walk a tree.

**The monster bestiary is not on this disc as Shift-JIS.** MEASURED three ways: eleven of twelve
common monster names appear nowhere as Shift-JIS bytes in the executable, the raw archive, or any
of 5,821 decompressed LZS sub-blocks; the six-u32 structural test over all 23,828 sub-blocks
finds no text block outside types 40 and 42; and the names are not stored as font descriptors
either, with `スライム` as the control that confirms the search works. What remains untried is a
non-LZS compression, a Huffman tree inside a type 46 overlay, and the 26,635-sector STR band.

---

## 15c. The message box, and what 0x7F04 does to it

### Three lines, and the shipped script never exceeds it

**A message box displays three lines. A fourth scrolls the first off the top, silently.**
MEASURED on hardware 2026-08-21: a scene rebuilt with every box at three lines or fewer rendered
all 29 boxes whole, and an earlier build of the same scene with eight boxes at four or five lines
lost the first line of every one of them.

**MEASURED across the shipped script: 100.00% of 24,169 boxes are three lines or fewer, with
zero exceptions.**

| lines | boxes | share |
|---|---|---|
| 1 | 3,750 | 15.52% |
| 2 | 6,384 | 26.41% |
| 3 | 14,035 | 58.07% |
| 4 or more | **0** | |

Counting this correctly needs one detail. A box ends at `0x7F0A` or `0x7F0B`, and the usual
continuation sequence is `0x7F0A 0x7F02 0x7F04`. **The `0x7F02` in that sequence belongs to the
terminator, not to the box that follows it**; counting it as a line break inflates every continued
box by one and produces a small phantom population of four-line boxes. 8,152 of 8,157 continuation
boxes carry exactly that one leading `0x7F02` and **no box in the game carries a second one**, so
discounting it hides nothing.

### 0x7F04 suppresses a prefix the data does not contain

A box whose opening run of control codes does **not** contain `0x7F04` is drawn with a leading
two-cell `＊「` that **the engine supplies and the text does not contain**. A box that does carry
`0x7F04` is drawn without it.

MEASURED on screen, text id 0x006C: strings 00 to 06 all open with `0x7F04` and none shows the
prefix; strings 07 to 10 open without it and all four show it. The discriminating case is **string
04, `シンシアは　モシャスをとなえた！！`, which carries `0x7F04` but has no speaker bracket and no
name code at all, and still draws no prefix.** It renders twice in that scene.

MEASURED across the shipped script:

| | boxes | share |
|---|---|---|
| opening run contains `0x7F04` | 14,084 | 58.71% |
| opening run does not | 9,904 | 41.29% |

**This does not correct the published reading of `0x7F04` as a name decorator; it confirms it.**
Of the 14,084 boxes that carry the code, **13,550 (96.21%) do supply a name**, 12,545 through a
name control code inside the same opening run and 1,005 as literal text followed by `「`. Only 534
carry no name, and those are narration lines where a name appears in prose without a bracket. What
is recorded here is the rendering consequence rather than the purpose: the prefix is keyed on the
code, and it stays suppressed even for the 534.

**The practical consequence for anyone laying out text**: the usable width of a box is 20 cells
with `0x7F04` and 18 without, because the prefix eats two.

**A methodological warning, since this took three attempts.** `0x7F04` is normally followed inside
the same opening run by the name code. A regex that consumes the whole leading control-code run
before looking for a name therefore eats the name, and reports a population of nameless boxes that
does not exist. Parse the opening run into a list of codes and look inside it.

---

### 15c-i. THE BOX IS 224 UNITS AND FONT 2 IS PROPORTIONAL. A CHARACTER COUNT IS NOT THE QUANTITY THE ENGINE ADDS UP

MEASURED 2026-08-26. **This supersedes the character cap this project has authored against since
Phase 1.** Nothing computed against the old cap is retracted: every such figure is true of the
character count it measured. What changes is that a character count was never the engine's
quantity.

**1. THERE IS NO HORIZONTAL WIDTH CHECK. The engine draws past the box edge.** The instruction
long read as the width test is **VERTICAL**: a Y accumulator against box HEIGHT, confirmed on 55
live blocks reading rows rather than columns. **Every access to the box width in the formatter was
read, and it is used ONCE, for a centering offset.** Nothing stops a long line; it simply draws
outside the frame. **And the shipped game very likely does exactly that, once**, which is under
"The shipped game against the model" below.

> **AND THE CENTERING LEG IS NOT TAKEN. MEASURED 2026-08-26, Phase 114: the message box is NOT
> centered in any of the 55 observed states. Text is LEFT ALIGNED at x = 0.** The centering is
> gated on `137(s0) == 0` through the same test that gates the 12-unit pull back in point 4, and
> `137(s0)` reads 0 in all 55. **The sentence above stays because it is true of the CODE**: the box
> width is read once and it feeds a centering offset. **What it does not tell you is that the offset
> is never applied in any state this project has observed.** Anything describing the dialogue box as
> centering its lines is describing a leg these 55 samples do not take. Stated as a 55-sample
> observation, not as a proof of impossibility.

**2. The box is 224 UNITS and font 2 is PROPORTIONAL**, widths **3 to 13** across 521 entries **in
the PRISTINE executable. A build of ours carries 523**, and which one a width tool walks is not a
detail: `docs/FONTS.md` section 7.
Kana average **10.7**; fullwidth lowercase Latin averages **7.4**.

**3. The old cap of 21 was a statistic over JAPANESE**, whose glyphs average **11.6 units**.
**English averages 8.01.** Over 348 authored lines the widest, at 20 characters, is **176 units,
79 percent of the box.**

**4. THE PREFIX AND THE HANGING INDENT. THE DRAWN PREFIX COSTS 15 UNITS ON LINE 0, SO THE LINE-0
BUDGET IS 209.** And, not previously in this record at all:

> **`{7F01}` and `{7F02}` start the next line at a 16-UNIT HANGING INDENT when the latch is set.**

The prefix is **bit 0 of the box flags word, PER CALL SITE**, live in **22 of 55** states, and it
is **cleared by `{7F0A}` and `{7F0B}`, so it fires once per BOX** rather than once per line.

> **CORRECTED IN PLACE, 2026-08-26, Phase 114. This paragraph used to read "15 units less a 12-unit
> pull back, so 3 units net on line 0", which disagreed with the model block seventeen lines below
> by 12 units. THE MODEL BLOCK WAS RIGHT. A reader computing 221 from the old clause gets a number
> no leg of the code produces.**
>
> **The 12-unit pull back is REAL and it does not RUN.** MEASURED: `lhu 120(s0)` / `addiu -12` /
> `sh 120(s0)` does rewind the horizontal accumulator, clamped on the accumulator itself, so "3
> net" was mechanically defensible **as a statement about the right-edge shift of a short line**.
> **It is not a budget.** The `-12` sits behind a guard on `137(s0)`, and **`137(s0)` reads 0 in all
> 55 live message-box states and in all 22 where the prefix is enabled**, so the branch is taken and
> **the skip target zeroes the accumulator instead.** Stated as a 55-sample observation, not as a
> proof of impossibility.
>
> **A second reason that holds even if it did run.** The pull back **spends left-edge room to buy
> right-edge room, and at the cap there is no left-edge room left.** Simulated exactly: **by
> `s1 = 201` the centering is already under 12, the clamp fires, and the full 15 is paid.**
>
> > **The refund exists only in the regime where it is not needed.**
>
> **Largest line 0 that does not clip: 209 units, with centering on or off. Both legs, one answer.**
>
> **Convention, and it is worth one unit: 209 counts the trailing 1-unit gap as INSIDE the box.**
> Treated as outside, the same measurement reads 210. Pick one and say which; nothing else changes.

**5. THE HAZARD NO CHARACTER GATE CAN SEE: 21 capitals plus the prefix is 232 units, 104 percent
of the box. It clips.** A character cap is **simultaneously too tight for lowercase and too loose
for capitals**, which is why this is a change of unit and not a change of number. Codex rule 35.

**THE 232 SHOWS ITS WORK, so nobody has to take it on trust.** Per-letter fullwidth capital widths
come from the game's own font 2 table, and the **1-unit gap per glyph is measured in all 43 live
boxes**: **mean capital 9.35**, so **10.35 with the gap**, and **21 x 10.35 = 217. 217 + 15 = 232**,
104 percent of 224.

**And a worked sentence rather than a mean, because rule 35's own corollary forbids leaning on
one.** `THE HERO HAS RETURNED` is **21 characters, 216 units, 231 with the prefix. It clips by 7.**
Three realistic all-caps lines measured letter by letter rather than averaged: **231, 231, 226.
All three exceed 209.** **21 of the widest capital is 288.** At the mean, **20 capitals is the last
length that fits.**

**The hazard is not an artifact of charging 15 rather than 3**, which is the first thing anyone will
suspect after the correction in point 4. It survives either figure, and it survives the mean being
replaced by real letters.

#### The model, in general form

```
line width = sum over glyphs of ( font2_width(glyph) + one gap )
budget     = 224
             minus 15 on line 0        when the box has no {7F04}   ->  209
             minus 16 on lines 1 and 2 when the box has no {7F04}   ->  208
```

**THIS BLOCK IS THE AUTHORITY AND POINT 4 USED TO CONTRADICT IT.** MEASURED, Phase 114: **the
line-0 budget with the prefix live is 209**, and the 12-unit refund that would have made it 221 is
behind a guard the message box does not pass. **No leg of the code produces 221.** The correction
and both independent reasons are in point 4. **A box that carries `{7F04}` draws no prefix and gets
the full 224.**

**8.01 AND 11.6 ARE MEANS AND A GATE MUST NEVER MULTIPLY THEM.** Sum the real widths, glyph by
glyph, out of the font 2 table. The means are for reasoning about headroom and for nothing else,
and they do not compose: 21 characters at the Japanese mean of 11.6 is **243.6 units against a
224-unit box**, which is an impossible line.

**CORRECTED IN PLACE, 2026-08-26.** This paragraph used to end "so the old 21-character cap and the
measured mean cannot both be describing the same lines", and left that standing as an unresolved
arithmetic inconsistency in the record. **It is resolved**, under "The shipped game against the
model" below: **long shipped lines use narrower glyphs.** 21-glyph lines exist and fit, at **10.6**
units per glyph rather than 11.6, and the game **never writes a 22-glyph line at all**. **243.6
never described a real line.** Nothing above is retracted, and 11.6 remains the correct mean over
the population it was taken on. That is precisely why multiplying it by a length drawn from the top
of the range is wrong: the mean is not constant along the axis it was multiplied by. A gate that
multiplies a mean is a character gate wearing units.

#### THE STANDING LIMIT

> **The unit model PREDICTS. It has not been booted.**

**Nothing may be authored longer on the strength of it.** Confirmation is named and cheap: **one
build with a deliberately 26-character unnamed line 0 on a prefix-live call site.** Until that
boots, treat the extra headroom as unproven and keep authoring to the old budget.

#### A NAME CODE IS CHARGED AT EIGHT CHARACTERS

**DECIDED 2026-08-27, phase 118. Names are sized at EIGHT CHARACTERS throughout, so every name code
in a line is charged at its eight-character width and not at the width of the short token it shows
in an editor.** This is the units model's half of the decision; the authoring half is R15 in
`corpus/editorial/voice-sheet.txt`.

**A name code has no width of its own, and that is why this belongs here rather than only in the
voice sheet.** The engine substitutes glyphs and then sums THEIR widths through the model above, so
what a name costs depends on which letters the player typed. **Eight characters is a BUDGET, not a
measurement**: it fixes how many glyphs may arrive, and the unit cost of those eight still varies
with the glyphs. **A line that fits at the mean can clip at eight capitals**, which is point 5 of
this section aimed at a substitution instead of at typed text, and it is why the character figure
cannot be the whole answer here either.

**It supersedes the 5-cell name budget used in the Phase 46 build**, which is not retracted: it was
true of that build. `voice-sheet.txt` R8 carried a pointer to that figure and has been corrected in
place.

**Cost of the decision, MEASURED and isolated: 29 lines were fixed to clear eight characters, with
zero meaning loss**, proven token for token against a control that catches a deleted word. **Zero
lines are over at four characters and zero at six. Everything that is over is over at eight**, so
the cost does not grow with the width; it is those 29 lines.

**The consequence for a named box's line 0 is already recorded**, in `voice-sheet.txt` 2.3f, which
assumed eight before it was decided: **where the name code IS the tag, the tag alone is 9 cells.**

#### Three limits on the measurement itself

- **224 is measured on 55 blocks that were all the standard dialogue box.** Other window types are
  not covered by it.
- **13,553 of 16,434 strings were excluded from the unit census** for carrying a substitution
  code, leaving 2,881. That is **82.5 percent excluded**, large enough that **the strata comparison
  must not be leaned on.** **And that exclusion is exactly the population the eight-character charge
  above governs**, so the unit census says nothing about lines carrying a name and cannot be used to
  check that charge.
- **The shipped game did NOT settle the prefix question.** Charging the prefix costs **22 extra
  violations in 3,581 lines, 0.6 percent**, which is not a falsification either way: **Japanese
  never runs tight enough against 224 for 15 units to show.** That was reported as a refusal rather
  than as a result, and the refusal is the part worth keeping.

#### The shipped game against the model, and the one line that exceeds the box

MEASURED 2026-08-26. **This is the first shipped-game evidence the unit model has had.** Over
**3,969 shipped lines, exactly ONE exceeds 224 units.**

> **`0x048F` string 70, box 0, line 0, unnamed. 229 units. Over by 5.**

**The next widest is 223.** Every glyph in that line was re-read individually out of the game's own
font 2 table rather than trusted as a sum. **No width is an outlier.** The widths present are 7,
10, 11 and 12, the crowded middle of a 3-to-13 distribution, and **the three suspicious 13s are
only 3 glyphs in the whole table, none of them in this line.**

**Three of the four ways this figure could have been manufactured were tested and closed. The
fourth is open and is stated.**

| escape | verdict |
| --- | --- |
| a bad font 2 table entry inflating the sum | **CLOSED**, every glyph re-read individually, no outlier |
| length, the line is simply longer than any other | **CLOSED**, the overrun is the 20-glyph line, below |
| a wider window exists somewhere on the disc | **CLOSED**, maximum window width on the disc is **240 px**, eight types |
| this string draws in some window not yet characterized | **OPEN**, see the caveat below |

**Live geometry: 61 text states across 85 dumps, two window types, both 240 px, inner width 224 in
every one, margin 16 without exception.**

##### The 21-versus-11.6 puzzle is RESOLVED, and length is not what does it

**Long shipped lines use NARROWER glyphs.**

| glyphs on the line | widest line at that length | units per glyph |
| ---: | ---: | ---: |
| 19 | 222 | 11.7 |
| **20** | **229** | 11.4 |
| 21 | 223 | **10.6** |
| 22 | **no such line exists** | |

**The overrun is the 20-glyph line, not the 21.** And **the shipped game never writes a 22-glyph
line at all, which is what the old character cap was really recording.** The mean of 11.6 was being
applied to a length at which the text has stopped using mean-width glyphs. This is the resolution
the corrected paragraph above points at.

##### THE CAVEAT, NAMED RATHER THAN BURIED

> **The measurement did NOT establish which window `0x048F[70]` actually draws in.** The margin of
> 16 is measured on two window types only. **A 240 px window with a margin under 11 would fit 229.
> No evidence of such a window exists, but it is not excluded.**

**It is answerable and it is cheap: catch that string on screen or in a dump and read the inner
width at that moment.** Until that is done, the form to quote is this one:

> **The shipped game VERY LIKELY draws past its own box edge, on one line in 3,969, by 5 units, in
> the widest box it has.**

**Not "the shipped game clips."** MEASURED: one line at 229 units, a widest box of 240 px giving
224 inner, a margin of 16 on both window types observed live, and glyph widths verified
individually. INFERRED: that this particular string draws in a 240 px window at the standard
margin, and therefore overruns its box by 5 units.

**This also puts a number on the third limit above.** "Japanese never runs tight enough against 224
for 15 units to show" is now measured rather than asserted, and it is nearly true rather than true:
**exactly one line in 3,969 runs tight enough, and that one runs 5 units past.**

##### THIS NARROWS THE STANDING LIMIT. IT DOES NOT LIFT IT

> **The unit model PREDICTS and has not been booted.**

Unchanged, and it stays in the record in those words. The confirmation named above, one build with a
deliberately over-length unnamed line 0 on a prefix-live call site, is still owed and is still the
only thing that lifts it. **Nothing may be authored longer on the strength of this section.**

##### Three counts in this section, three populations, not reconciled

**3,969** shipped lines measured for width here. **3,581** lines in the prefix-charging comparison
under "Three limits" above. **2,881** strings surviving the substitution-code exclusion from the
unit census, out of 16,434. **These are three different questions and the figures must not be
merged or treated as nested.** Anyone needing one denominator to cover two of them re-measures
rather than assuming the larger contains the smaller.

## 15d. Type 46, the MIPS overlays, and the text blocks inside them

MEASURED, Phase 52. 612 type 46 sub-blocks, 600 LZS compressed and 12 raw, 43,846,220 bytes
decompressed. **They hold only 188 distinct contents.** The sub-block header's third u32 is a load
address and takes exactly three values: `0x8013BF04` on 502, `0x80102448` on 93 and `0x80143F80`
on 17. `0x80102448` is the byte the game's own boot clear stops at, section 12b and Phase 49.

**The overlays carry text blocks in the format of section 3.** Same six-u32 header, same 0x7Exx
dictionary, same dual-base tree, same self pointer at `a`.

| | |
|---|---:|
| embedded text blocks, occurrences over the 188 distinct contents | 131 |
| **distinct text blocks** | **15** |
| distinct text ids, all in `0x0473` to `0x048B` | 15 |
| strings | 1,695 |
| displayed characters, dictionary expanded | 28,602 |
| bytes of text block inside 5,618,043 bytes of distinct overlay | 44,196, **0.79%** |

**None of the 15 ids occurs in the archive population or in the executable population.** They sit
immediately below the executable's `0x048C`, `0x048D` and `0x048F`.

The finder is the structural test of section 3 plus a complete decode. It is insensitive to its own
filters: relaxing the id range to `0x0001..0xFFFF` and dropping the self pointer requirement both
return the same 131.

### How an overlay reaches its own pool

An overlay is loaded at a fixed address, so its `jal` targets are absolute:

| target | routine | sites | distinct overlays |
|---|---|---:|---:|
| `0x8008F178` | `register_block` | **137** | 71 |
| `0x8008F280` | the reference resolver, section 12 | **304** | 106 |

Every `register_block` site forms its pool's absolute base with a static `lui`/`addiu` pair, and
that base resolves to a text block header. **This is the dynamic registration Phase 50 inferred
from the executable side**, where 19 of 24 call sites load their base from memory.

The overlays also carry the packed reference word of section 13: **1,781 of them, 1,779 landing
exactly on a string start.**

No length is baked into any instruction, and there is nowhere to put one. String symbol lengths run
0 to 112, so a length field would need 7 bits, and the reference word is 12 bits of text id plus 20
bits of bit offset with nothing spare.

### Correcting Phase 32's reading of the index

Phase 32 found a u16 index whose entries chain as `offset + 2 * length`, could not find a base that
put the boundaries on string starts, and concluded the top four bits were not a length.

**The chain is real, the top four bits ARE a length in 16-bit units, and the entries are DICTIONARY
PHRASES rather than strings.** Measured over 531 entries in 12 blocks: 519 of 519 consecutive pairs
chain exactly; the top four bits take 7 distinct values so it is not a flag; it varies inside every
table so it is not a pool id; 299 of 531 exceed 3 so it is not an alignment count.

**The base is not a constant to search for.** The phrases begin immediately after the index, so

    base = index_start + 2 * count - offset[0]

and the entry count is derived the same way `dictionary.parse` already derives it. The tiled phrase
region ends two bytes before `c` in the pools measured, because **`c` is that region's end rounded
up to a multiple of 4**.

### One population that is not Huffman

MEASURED: 1,565 deduplicated characters of plain Shift-JIS sit outside every text block. They are
the memory card save file title, the message speed labels and a few short labels. INFERRED, and the
reason is sound: the save file title has to be plain Shift-JIS because the PlayStation BIOS memory
card manager renders it, not the game.

---

## 15e. Font 2, the dialogue font

**Font and text rendering detail lives in `docs/FONTS.md`, which is the authoritative
location for it.** It is not duplicated here.

The font 2 table, its descriptor layout, the 2bpp run length payload, the donor rule, the
fact that the region of zeros at `0x800B9248` is the malloc heap rather than free space, and
the terminator method for adding a character are all in `docs/FONTS.md`.

---

## 16. On gates

**The method rules this project runs on live in `docs/CODEX.md`, not here.** That file is the
authoritative location for them; this section states only the one that shapes the gate suite
directly, and does not repeat the rest.

### The rule


The most transferable thing in this repository is not a format detail. It is this.

**Four separate defects passed every gate written from this project's own model of the format.**
Each was caught only by a check derived from a statistic the shipped game exhibits:

| defect | what caught it |
|---|---|
| a collapsed Huffman decoder that round-tripped byte-exactly | **bits per symbol**, 1.06 against a corpus norm of 7.81 |
| a recompressed block whose LZS overrun drifted from +3 to 0 | the **pristine overrun distribution** across the whole archive |
| a font table reading that fit 13 of 13 Latin capitals | a **20-kana companion**, which the 13-capital gate had already passed |
| four builds that hung the console on sub-block misalignment | the **23,828 sub-block alignment census** |

In every case the failing artifact satisfied the checks that came from our own understanding.
The round trip really did round trip. The 13 capitals really did fit. The referrers really did
resolve, 12 of 12, on a disc that would not boot.

**A gate written from a model tests the model.** If the model is wrong, the gate is wrong in the
same direction and agrees with itself. That is why a calibrated, reproducible and
arithmetically correct absence proof (section 11) held a confident wrong answer for three
phases.

Gates that catch real faults compare against **invariants the shipped game exhibits**, measured
from the original data rather than derived from an interpretation of it. They are usually
cheaper to write than the model-based ones, and they are the ones worth adding first. Anyone
reusing this library should add gates of the second kind before trusting what it produces.

The corollary, learned the same way: **every gate needs a companion that can fail differently.**
A gate that can pass degenerately will eventually pass degenerately.
