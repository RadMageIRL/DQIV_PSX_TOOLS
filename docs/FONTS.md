# Fonts and text rendering

Dragon Quest IV, PlayStation, SLPM-86916. How a character code becomes pixels.

This assumes you have the disc and a disassembler. Addresses are virtual
addresses in `SLPM_869.16` unless a file offset is given. Values described as
measured were read out of the executable or observed on hardware; values
described as not confirmed are structural readings that have not been checked
against a running game.

## 1. There are two fonts

The game registers two font tables at fixed addresses inside the executable.
Neither is in the archive, which is why scanning archive data never finds them.

| | font 1 | font 2 |
|---|---|---|
| registered from | `0x800B2A3C` | `0x800B3600` |
| font record | `0x800B2A58` | `0x800B361C` |
| hash modulus | 137 | 29 |
| entries as shipped | 533 | 521 |
| chain stride | 4, code at `+2` | 8, code at `+4` |
| cell | fixed 8 by 14 | per glyph, up to 16 by 16 |
| pixels | resident 4bpp atlas | 2bpp run length, expanded per character |
| advance | fixed 8 | per glyph, from the entry |

**Font 1 draws the menus. Font 2 draws the message box.** Measured on
hardware: three separate edits to the font 1 table had no effect on a dialogue
box, and one edit to font 2 rendered, on the same disc in the same box.

Font 2 is the variable width font, it carries per glyph width and height, and
the renderer already honors them. It is not a spare or a fallback. It is in use
for all running dialogue.

### The trap

The two tables overlap heavily. Of the codes they carry, **435 are in both, 98
are in font 1 only, and 86 are in font 2 only.** Nearly everything the game
draws in normal play exists in both tables.

The practical consequence: **you cannot tell the two apart by watching working
text.** Edit the wrong table and the game keeps drawing the character correctly
out of the other one, and the edit looks inert rather than misdirected. A
missing entry is equally quiet. The lookup walks the bucket chain, finds no
matching code, returns zero, the caller returns -1, nothing is drawn and the pen
does not advance. Nothing on screen distinguishes a missing glyph from a space.

Check a code against the table the drawing context actually uses, not against
either table.

### The selector

Font choice is a caller-set mode, not a property of the character. At
`0x8002D620` the drawing routine loads a byte from the text state at `+131` and
compares it:

```
0x8002D620  lbu a0,131(s0)
0x8002D638  beq a0,s3,0x8002D650      ; s3 = 1 -> font 1
0x8002D640  beq a0,fp,0x8002D6E4      ; fp = 2 -> font 2
```

The same character code goes to whichever font is active.

## 2. The lookup

`0x8008F7B0`. A chained hash table, not arithmetic on the code.

```
bucket = code % modulus            ; divu, then mfhi
head   = halfword at buckets + 2 * bucket
```

The bucket halfword is a **self relative** offset: the chain starts at
`slot_address + head`, not at `buckets + head`. A zero head means an empty
bucket. Walking the chain, a **zero code terminates it**.

Two chain layouts, selected by whether the record's cell width and height at
`+20` and `+22` are both nonzero. Nonzero selects the 4-byte layout, zero
selects the 8-byte layout.

The walk is bounded on every axis: 12 registration slots, `slot+20` records per
slot, and a zero-code terminator per chain. A code with no entry simply misses.
There is one unbounded hazard, `break 0x1C00` at `0x8008F830` on a zero modulus.

That bounding only holds while the chain data is well formed. A bucket array
pointing at arbitrary bytes walks arbitrary memory.

### The font record

Reached through the block header at `base + 12`. The record is at
`base + [base+12] + 4`, 24 bytes:

| offset | field |
|---|---|
| `+0` | bucket array offset, from the block base |
| `+4` | glyph payload offset, from the block base |
| `+8` | modulus, u16 |
| `+10` | font id, u16 |
| `+14` | entry count, u16, **never read by the lookup or the expander** |
| `+20` | cell width, u16 |
| `+22` | cell height, u16 |

`+0` and `+4` are offsets **from the block base**, which makes them fragile.
Anything that moves the block's regions has to move them too. Copying a region
verbatim while the base moves points the bucket array at whatever now occupies
that offset.

For the two resident fonts: buckets at `base + 0x34` for both, glyph payload at
`base + 0` for font 1 and `base + 0x11A0` for font 2, so `0x800B47A0`.

## 3. Font 1: descriptors and the atlas

A font 1 chain entry is 4 bytes: descriptor u16 at `+0`, code u16 at `+2`. Width
and height come from the record's cell fields, 8 by 14 for every character
including kanji.

"Fullwidth" names a region of the Shift-JIS **code** space, not a rendered
width. Font 1 renders everything in 8 pixels.

### The descriptor is a cell and a plane

This is the part that is not guessable and costs time.

```
cell  = descriptor >> 1
plane = descriptor & 1
U     = (cell % 32) * 8
V     = (cell / 32) * 14
```

Measured at `0x80087364` through `0x800873BC`.

**Every atlas cell holds two glyphs, one in each 2-bit plane of the 4bpp
pixel.** Bit 0 of the descriptor selects which one is visible, by selecting a
CLUT. Reading a cell as a single 4bpp image superimposes both glyphs and
produces a plausible looking but wrong inventory: consecutive cells read as an
alternating, descending run of letters.

To render one glyph, extract the 2-bit plane its descriptor names:

```python
plane_values = [[(v >> (2 * plane)) & 3 for v in row] for row in cell_rows]
```

One character emits one 20-byte GPU packet: command `0x65`, textured rectangle,
width 8, height 14, with the CLUT id at `+14` taken from a table at
`0x800E7810`.

### Atlas geometry

The atlas lives in the archive as type 1 sub-blocks. Six sub-blocks, two
distinct contents, three copies each.

| property | value |
|---|---|
| pixel format | 4bpp, **low nibble first** |
| width | 256 pixels |
| cell | 8 wide by 14 tall, origin (0, 0) |
| size | 16,128 bytes, 126 rows, 9 bands |
| slots | 288, of which 268 are non-blank |

Rendering high nibble first breaks every vertical stroke into a dotted line,
which is a fast way to check you have the nibble order right.

288 cells at 268 non-blank gives up to 536 glyph positions; the font 1 table
names 533 of them. The two blank cells, 6 and 7, are named by no code, and their
four descriptors are among the six the table never uses. The unused half-cells
and the blank cells are the same cells, which is two independent routes to the
same answer.

The rightmost column and the bottom row of each cell carry the glyph's drop
shadow rather than the letterform. For width work: the advance is 8 pixels and
the letterform body occupies columns 1 through 6.

The atlas carries all 26 Latin capitals, all 26 lowercase and all 10 digits,
resolved through the game's own table rather than by eye.

Classification of the remaining slots into kana against symbols rests on ink
density and height and is **not confirmed**.

## 4. Font 2: the dialogue font

A font 2 chain entry is 8 bytes:

| offset | field |
|---|---|
| `+0` | descriptor, u32 |
| `+4` | code, u16 |
| `+6` | width, u8 |
| `+7` | height, u8 |

Note the code sits at `+4`, not `+2`. Reading it at the font 1 offset yields
nothing that looks wrong, just a table that misses everything.

Widths are real: capitals average 9.3 pixels, lowercase 7.4, digits 7.7, kanji
11.9.

### The descriptor is patched at runtime

```
bits  0..19   pixel index into the payload, 2 bits per pixel
bits 20..27   registration slot
bits 28..31   record index within that slot
```

**The high 12 bits are zero in the shipped image because the lookup writes them
on first use.** `0x8008F8E8` through `0x8008F900` masks with `0xF00FFFFF`, ors
in the slot, masks with `0x0FFFFFFF`, ors in the record index, and stores the
descriptor back. A table dumped from a running game therefore differs from the
same table dumped from the disc, in a way that is not corruption.

The expander resolves the payload address as
`[slot+0] + [record+4] + (index >> 2)`, word aligned, with the starting bit at
`(index * 2) & 0x1F`.

### The payload is a 2bpp run length stream

Read at `0x8008FA30` through `0x8008FB40`:

```
read 2 bits -> value
if value != 0:  run = 1
else:           read 2 more bits, run = those + 1     ; 1 to 4 zeros
emit run pixels of value
repeat until width * height pixels are emitted
```

Streams are packed contiguously and a glyph rarely starts on a word boundary.

## 4b. Every map text block carries its own font 2 supplement

The resident tables are not the only source of glyphs. `register_block` at
`0x8008F178` registers text blocks using the same header shape as font blocks,
so `block + 12` becomes the record count and record array pointer, and the block
record at `d + 4` is a real font record with font id 2.

For one map block, as a worked example of the shape:

| field | value |
|---|---|
| record at `d + 4` | `+0` bucket array offset 984, `+4` glyph payload offset 1124, modulus 2, font id 2 |
| bucket array | `block + 984` |
| chain entries | `block + 988`, which is `d + 32`, 15 entries of 8 bytes |
| entry layout | descriptor u32, code u16 at `+4`, width u8 at `+6`, height u8 at `+7` |

That block supplies 15 kanji at 12 by 13 and 11 by 8, and **14 of the 18 leaves
in its own script have no font 1 entry at all**. The scene cannot draw its own
dialogue without this table. If you are auditing which codes a block can draw,
the resident tables are not the whole answer.

The same fragility as section 2 applies and bites harder here: `+0` and `+4` are
offsets from the block base, so anything that moves the block's regions must
move them too. In one build a region was copied verbatim while `d` moved, the
bucket array landed inside the tree pair array, and the chain walked to offset
33,821 in an 1,804-byte block.

## 5. The code space, and why halfwidth ASCII is unreachable

Both tables are keyed by **fullwidth Shift-JIS codes**. Measured on the shipped
executable: font 1 spans `0x8140` to `0x9862`, font 2 spans the same range, and
**neither table contains a single entry below `0x8000`.**

That alone would only be a property of the tables. The wall is in the decoder.

`0x8008F3BC` returns a character. Its Huffman path ends:

```
0x8008F594  beq s1,zero,0x8008F5A0      ; END skips the ori
0x8008F59C  ori s1,s1,0x8000            ; file offset 0x077E9C
```

**Every non-zero leaf has bit 15 set unconditionally.** The Huffman path can
return only `0x8000` through `0xFFFF`, plus `0x0000` for END. A stored leaf of
`0x0041` comes back as `0x8041`.

So halfwidth ASCII is not reachable from compressed text. That single `ori` at
`0x8008F59C` is the wall, and it is the most useful single fact here for anyone
planning an English script: **your text is fullwidth, one code per character,
and the width you get is the width the font gives you.**

Of the reachable space, `0xFE01` to `0xFEFF` is consumed by the phrase
dictionary and `0xFF00` to `0xFFFF` by control codes.

The engine does have a single-byte path. When the state word is negative,
`0x8008F3BC` reads raw Shift-JIS and classifies lead bytes at `0x8008F3F0`
through `0x8008F414`, returning a single byte of `0x00` to `0xFE` from
`0x8008F4E8`. It is not reachable from compressed text, and since neither font
table holds a code below `0x8000`, such a value would miss both fonts and draw
nothing.

## 6. The shipped English game on this engine did the same thing

Dragon Warrior VII US, `SLUSP012.06`, is a released English game on the same
engine family. Its font table is at `0x800B1F84`: modulus 17, 8-byte stride,
font id 2, 309 entries.

Measured, by reconstructing that table the same way:

- **0 codes below `0x8000`.** The range is `0x8140` to `0x96F2`.
- **62 of 62** fullwidth Latin letters and digits present.
- **0 halfwidth ASCII entries.**

The developers shipping an English game on this engine did not solve halfwidth
either. They set English in fullwidth Latin.

Worth knowing if you need punctuation DQ4 lacks: DW7's table carries `0x8166`,
the right single quotation mark used as an apostrophe, and `0x8147`, the
semicolon, at the same codes.

## 7. Adding a character

The tables are exactly packed. For font 2 the chain region runs `0x800B3670` to
`0x800B47A0`: 550 slots holding 521 entries and 29 terminators, with no gaps.
**No chain grows in place.**

### There is no free space

The region of zeros at `0x800B9248` is not free. `0x8009A1CC` calls
`0x800A5EA0`, which is `jr 0xB0` with `t1 = 25`, so it is BIOS `B(19h)`
`InitHeap(0x800B9204, 4060)`. It ships as zeros because a fresh heap is empty.

A chain relocated there is overwritten by the allocator, and **every code in
that chain is lost, not just the new one.** Measured on hardware: three shipped
letters disappeared from the message box. Treat no zero region in this data
segment as free unless you have shown it is.

### The terminator method

This needs no free space and moves nothing.

**Write the new entry over the bucket's own terminator.** No relocation, no
bucket head changes, and no byte outside the table moves. Then write a fresh
terminator into the following slot, which is the first entry of the next chain,
so that chain must in turn be handled or the write must land on its terminator.

The cost, stated plainly:

- A **miss** on that bucket now walks on into the next chain and stops at that
  chain's terminator. No false hit is possible, because every code in the next
  chain hashes to a different bucket and is never looked up through this one.
- **The chain must have a successor.** Never do this to the last chain in the
  array, where the walk has nothing to stop it.

**For the payload, overwrite the stream of a glyph that is never drawn.**
Because streams are packed contiguously and a donor rarely starts on a word
boundary, write the bits **at the donor's own bit offset** rather than as whole
bytes, or you destroy the neighboring glyphs.

**The donor's payload is spent.** That glyph decodes garbage afterward and
leaves the usable inventory. This is a real cost and it should be stated every
time the method is used, not treated as free.

Two codes were added this way with zero of the 521 existing entries altered,
zero lost, executable length unchanged, and 29 bytes differing from the shipped
executable, none of them in the heap.

### If you substitute instead of appending

A code written over an existing entry must satisfy
`new_code % 29 == old_code % 29`, or the entry leaves the bucket it physically
sits in and is never found. The miss is silent. All 521 shipped entries obey
this rule, which is a good check that you have the modulus right.

The record's entry count at `+14` is never read, so it does not need updating.

## 8. Window geometry

Not strictly font work, but you will need it the moment you make text longer.

Window geometry comes from a table at `0x800A883C`, stride 28, indexed by a
window type code. The creation routine at `0x80085EA0` derives the record:

```
lui   v0, 0x800B
addiu v0, v0, -30660      ; 0x800A883C
sll   v1, a2, 3
subu  v1, v1, a2          ; a2 * 7
sll   v1, v1, 2           ; a2 * 28
addu  v1, v1, v0
```

and reads geometry **in grid cells**, scaling each field by bits 5 through 8 of
the flags word at `+0`:

```
lh   a0, 12(v1)           ; width, in grid cells
srl  v0, v0, 5
andi v0, v0, 0x0F         ; scale
mult a0, v0
sh   t1, 32(s1)           ; width, in units
```

| template offset | field |
|---|---|
| `+0` | flags; scale is bits 5 through 8 |
| `+8`, `+10` | x, y in grid cells |
| `+12`, `+14` | width, height in grid cells |
| `+18` | entry count |
| `+24` | **address of the routine that fills the window** |

The scale is 8 in every record examined. The screen is 256 units wide.

**THE TEMPLATE IS THE DEFAULT, NOT THE GEOMETRY.** A live window can carry
values the template does not. Measured across five memory images: one window
reads a width of 48 against a template of 160, and another reads a height of 40
against a template of 16. Both are consistent across every image, so this is
deliberate and not corruption.

Consequences, in order of how badly each bites:

* A capacity read off a template is only sound once you have confirmed that
  window is not overridden, which needs a memory image with it on screen.
* Editing the template of an overridden window is inert. The value is written
  and then replaced at runtime.
* An enumerator that identifies a live record by matching it against its
  template cannot report a mismatch, because a mismatch stops it recognizing
  the record at all. Identify records by their position in the window array and
  report the comparison as a result.

The live record holds its type at `+0`, x and y at `+0x1C` and `+0x1E`, and
width and height at `+0x20` and `+0x22`. Window records sit 200 bytes apart.

**Two grids, and confusing them is the trap here.** Template geometry is in
8-unit grid cells. Menu text advances 12 units. So a template width of 12 is 96
units, which is 8 text cells, and 8 does not divide 12.

### Text capacity per window, and the two grids

Window width is in 8-unit grid cells; text advances 8 units in font 1 and per
glyph in font 2. A window also carries **16 units of padding**, 8 on each side,
so the usable text width is `w * scale - 16`.

That model was solved from one window and then checked against others, which is
the only reason to trust it: the field command menu holds its Japanese row and
clips its English one at 96 units, bounding usable to `[80, 83)`, and 80 is
exactly the Japanese row. It then predicts, without further fitting:

| window | units | usable | holds | observed |
|---|---|---|---|---|
| a 72-unit description window | 72 | 56 | 7 characters at font 1 | Japanese uses exactly 7 |
| a 48-unit verb menu | 48 | 32 | 4 characters | a 5th clips |
| a 64-unit party list line | 64 | 48 | 6 characters | a 6-character line fits exactly |
| a 48-unit party box | 48 | 32 | 4 characters | a 4-character name fits exactly |

The last two were not used to derive the model.

**The font a window uses can be deduced from what it holds.** A 72-unit window
carrying seven kana must be font 1, because seven kana in font 2 need about 77
units against a 56-unit interior. Likewise a 48-unit box holding a four-kana
name is font 1, since font 2 would want 48 for the same four.

### Line breaks and the dictionary, before you measure anything

Two control codes break lines and they are not interchangeable. Dialogue uses
one; the narrow description class uses another. Splitting on the wrong one
reports a three-line box as a single line several times over budget.

**Expand the phrase dictionary before counting.** A `{7Exx}` reference is one
symbol and expands to several characters, so an unexpanded count understates any
line that uses one. `dictionary.parse` then `dictionary.expand` resolves the
whole corpus with zero unresolved references, so there is no excuse for
measuring the packed form.

### The builder address is in the table

`+24` holds the address of the routine that fills the window. That routine is
reached from this table, so **no call to it exists anywhere**: not in the
executable, not in any archive sub-block, and not as a stored pointer in RAM. If
you are looking for the code that draws a particular menu and finding no callers,
this is why.

The live window record, once created, holds its type at `+0`, x and y at `+0x1C`
and `+0x1E`, and width and height at `+0x20` and `+0x22`. The routine at
`0x80088E7C` makes a window current by storing its address to `0x800E9568`, and
caches `x + width` to `0x800E9538`. There are four such stores in the whole
executable and none in the archive, which makes `0x800E9568` a good place to
break if you want to know which window is being drawn into.

Text is formatted by `0x8008879C`, a printf style interpreter. Its format
strings are ordinary data and support width specifiers. A two column menu is
typically one format string with a literal space between the two conversions,
which means **the second column has no fixed x**: it starts wherever the first
column ends, and lengthening the left column pushes the right column right.

## 9. What is not known

- **Window capacities for the item list, the shop, battle messages and the
  Immigrant Town recruit roster.** None of these have been located in the
  template table.

- **SETTLED. The item list holds 9 characters.** The earlier 8-cell figure was
  wrong for a specific reason worth recording: the 12-unit advance it rested on
  was obtained by dividing a window's width by an assumed character count, which
  is the width it was meant to explain. There is no 12-unit advance. Font 1
  advances a fixed 8 units and font 2 advances per glyph, both read from the
  draw path. The item list is 96 units, draws through font 1, and the shipped
  game puts 9-character names in it.

  It cannot be widened. The list spans x 72..168 and the windows that draw the
  gold and the item description begin at exactly 168, so every widening collides
  with both. All four windows sharing the item-list geometry are 96 units.

- **The equip screen has never appeared in a memory image.** It draws item names
  and if it is narrower than the item list it governs instead. Two of the four
  item-list shaped windows were seen live at the same position and both are 96
  units, so the likeliest case is that the budget is the same, but that is not
  the same as having measured it.

- **Fifteen window templates whose builder addresses point into overlays** that
  were not resident in the memory images examined, so their contents were never
  read. They are unclassified, not empty.

- **The full set of callers that set the font mode byte at text state `+131`.**
  The selector is understood; which drawing contexts choose which font has been
  established for menus and the message box and not enumerated beyond that.

- **Kana against symbol classification for the remaining atlas slots**, which
  rests on ink density and height rather than on the table.

- **Whether any window width can be enlarged without side effects.** Widths in
  the template table are shared across window types in some cases, and no survey
  of which types share a record has been done.
