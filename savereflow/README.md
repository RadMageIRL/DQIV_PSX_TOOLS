# savereflow

`reflow-dqiv-psx.py` rewrites the text fields stored in a Dragon Quest IV
(PlayStation, SLPM-86916) memory card save so they match a current glossary, and
recomputes the checksums the game validates when it loads the save.

stdlib only. No dependencies. **No game data ships here** - you supply your own
memory card image and your own glossary files.

## Why it exists

A translation patch renames things. A save written before a rename keeps the old
words, so a player who carries a save across builds sees a mix of old and new
text and has no way to reconcile it. The save is not the disc: the party name
fields and the slot title's place name are stored **verbatim inside the save**,
so editing the disc never reaches them.

Editing them by hand does not work either. The save is checksummed in two
independent places, and a save whose checksums do not match is refused by the
game's loader. That is the whole reason this tool can exist: it edits the fields
and then reseals them.

## What it changes

Two kinds of field, and only these two:

| field | where | size | padding |
| --- | --- | --- | --- |
| party record name | 24 records inside the save body | 12 bytes, 6 fullwidth characters | zero |
| place name | the save block's Title Frame, `block+0x28` | 20 bytes, 10 fullwidth characters | fullwidth space `81 40` |

The place name is what the memory card slot list shows. The record names are what
the party menus, battle and dialogue show.

It does **not** touch the player-entered hero name, the save body's game state,
the icon, the card directory, or anything else.

## Usage

```
python reflow-dqiv-psx.py CARD.mcd --glossary FILE [--glossary FILE ...] \
                                   [--rename OLD=NEW ...] [--apply]
python reflow-dqiv-psx.py CARD.mcd --verify
python reflow-dqiv-psx.py CARD.mcd --restore
```

Dry run by default: it prints the full plan - block, offset, old bytes, new bytes
for every field and every checksum - and writes nothing. `--apply` writes.

| flag | effect |
| --- | --- |
| `--glossary SPEC` | a glossary file. Repeatable. |
| `--rename OLD=NEW` | an explicit remap for a value no glossary row accounts for. Repeatable. |
| `--apply` | back up, write, read back, re-audit |
| `--restore` | put the backup back and prove it by hash |
| `--verify` | audit the card's checksums and stop |
| `--backup PATH` | backup location, default `CARD.reflow-backup` |
| `--force-backup` | allow overwriting an existing backup |
| `--no-party`, `--no-place` | leave one kind of field alone |

### Safety

1. **Dry run by default.** Nothing is written without `--apply`.
2. **Backup first, verified by hash before a byte is written.** If the backup's
   hash does not match the source, the run stops and writes nothing. It refuses
   to overwrite an existing backup unless you pass `--force-backup`.
3. **`--restore` is a first-class operation** and is the simplest code path in
   the file: copy the backup over the card, hash both, report. Round trip -
   back up, write, restore - returns a file byte-identical to the original.
4. **It refuses a card that does not already validate.** Reflowing a card whose
   checksums already fail would hide whatever broke it.
5. **It refuses rather than guesses.** A field whose current bytes it cannot
   account for - not whole Shift-JIS characters, not name-plus-zero-pad, no
   glossary row, an English name too long for the field - is skipped and named
   in the report. A partial run that names what it skipped is worth more than a
   complete one that guessed.
6. **It verifies its own output.** After writing it re-reads the file from disk
   and re-runs the entire checksum audit over it, so it proves the written card
   would pass the game's loader before it claims success.

## Glossary format

A glossary is a text file of `|`-separated fields, one entry per line.
Everything from a `#` to end of line is a comment. Blank lines and lines with no
`|` are ignored.

```
アルファ | Alpha
ブラボ   | Bravo
```

By default the tool reads the **Japanese from field 1 and the English from field
2**. Real glossaries put those columns in different places, so a glossary can name
its columns, 1-based:

```
--glossary characters.txt:2:4      # Japanese in field 2, English in field 4
```

Both the Japanese column and the English column become lookup keys, so a field
that already holds a **previous build's English** is recognized and reflowed to
the current spelling. Fullwidth Latin in a save is folded to ASCII for the
lookup, because the save stores English fullwidth and a glossary writes it in
ASCII.

If two glossaries disagree about a name, the run stops and names the conflict
rather than picking one.

`--rename OLD=NEW` is the escape hatch for a value that no glossary row accounts
for - typically an English spelling that a ruling withdrew, so no row maps it any
more.

## What it cannot do

- **It cannot fix a field the game does not populate from the save.** A save
  holds the name field verbatim and the game copies it out and displays it, so
  rewriting it works. Anything the game materializes from the disc at run time is
  out of reach of a save editor by construction.
- **It cannot make a name longer than the field.** 12 bytes is six fullwidth
  characters; 20 bytes is ten. Anything longer is refused, not truncated.
- **It only encodes fullwidth Latin letters, digits, space, period, comma and
  apostrophe.** Anything else is refused. Halfwidth ASCII is not written, because
  the game's field holds fullwidth.
- **Zeroing a name field is not a substitute for writing one.** The game's
  record initializer skips its name copy when the field is already non-empty,
  which invites the idea that blanking a field makes the game refill it from its
  own character table. On this engine the initializer is reached only when a
  record is *allocated*, and allocation only picks a record whose character id is
  zero. A record restored from a save has a non-zero id, so nothing re-runs the
  initializer over it and a blanked field stays blank.

## The format this relies on

A PlayStation memory card is 16 blocks of 8192 bytes. Block 0 is the directory;
blocks 1 to 15 each hold one save. Each block is 64 frames of 128 bytes.

- **Frame 0 is the Title Frame.** `SC` magic, then a 64-byte Shift-JIS title at
  `+0x04`. Byte `+0x7F` is the **8-bit XOR of bytes `+0x00` to `+0x7E`**. The game
  checks it, and on mismatch replaces the whole title with its own "broken log"
  string rather than trusting the frame.
- **Frames 1 and 2 are the icon.** Not checksummed.
- **Frames 3 to 42 are the save body**, 40 chunks. Each frame holds **124 bytes
  of payload followed by a 4-byte little-endian CRC-32/BZIP2 of those 124 bytes**
  - polynomial `0x04C11DB7`, MSB first, init `0xFFFFFFFF`, xorout `0xFFFFFFFF`,
  input and output **not** reflected.
- **The first 8 bytes of chunk 0 are a 40-bit present-chunk map.** A chunk whose
  bit is clear is neither written nor read; its frame on the card is left erased.
  The tool follows this map, so a stale frame left behind by an earlier, longer
  save is neither audited nor edited.
- The body is a flat image of a fixed RAM region cut into those 124-byte chunks,
  so a structure in the save can straddle a frame boundary. When a field does,
  the tool writes both pieces and reseals both frames.

## Tests

```
python -m unittest discover -s tests -t .
```

Thirty tests, and **none of them reads a save file**. Every card is fabricated,
because the saves any one person owns exercise a narrow slice of the shapes the
tool claims to handle and therefore cannot falsify the claim.

The mutants are the load-bearing part. A checksum verifier that has only ever
seen good data is not a verifier - it passes just as well when it returns true
unconditionally. So:

- the CRC is pinned to its published check value **and** asserted to differ from
  the reflected CRC-32 it is easy to mistake it for;
- every one of the 992 single-bit mutations of a 124-byte frame is asserted to
  change the CRC;
- the audit is shown to catch a mutated data byte and a mutated title byte;
- the resealer is **disabled** in one test, and the audit must then fail - which
  is what makes the test where it passes mean anything;
- a stale frame outside the present map is given a deliberately wrong CRC and the
  audit must **not** report it;
- unaccountable padding, an overlong name, an unknown name and an unencodable
  character each have a test asserting the tool writes nothing and says why.

## License

MIT.
