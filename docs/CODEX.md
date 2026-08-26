# Codex

Method rules for reverse engineering a game format, each one learned by losing time to it.

A rule enters this file when it has cost a phase, not when it sounds sensible. Every entry carries
what it cost. Where a rule has been learned more than once the instance count is given, and **the
count is the signal for what to check first**.

Ordered by how often violating it has cost a phase. Read it in full before starting work. If it
grows past what someone will actually read, it has failed at its job.

Most of this is general. Entries marked **[PSX]** are platform specific.

---

## 1. Validate the instrument against a case where the thing is present

**Seventeen instances. The most expensive rule here. Its worst single instances cost twenty-five phases, fifteen phases, and a boot test.**

Before trusting a negative result, run the detector against something you know it should find. A
scan that returns zero is not evidence until you have seen it return non-zero.

- A search for a character code across the whole executable returned zero and looked conclusive. The
  same search returned zero for the line break, which the engine certainly handles. The scan could
  not see any character, because characters are not tested as immediates in that code. **The result
  was discarded.**
- A check that a generator did not sweep a hand-authored directory into its output ran **before the
  directory existed**. It passed and tested nothing. The next regeneration swept it in.
- A structural test for text blocks required a header field to equal 24, which is only true of a
  block with no dictionary. **One block with a dictionary stayed invisible for forty-five phases.**

Corollary: **a scan that resolves only static values reports a floor, not a total.** A scan for
range writes resolved one address per store and could not see a loop walking a pointer. A scan for
callers found five that formed the argument with a constant and missed nineteen that loaded it from
memory. Both reported their partial result as if it were complete.

Corollary: **a control must break the specific structure the detector keys on.** A byte-reversed
control was mathematically inert against a filter that counted ink in nibbles, so it "passed" while
proving nothing.

Corollary, and the most expensive single instance in this project: **a population that cannot
discriminate is not a control, however large it is.** A rendering pipeline was investigated for
twenty-five phases on the strength of every other character in the scene rendering correctly. Those
characters could not have discriminated: **43 of the 45 codes the scene draws exist in BOTH of the
game's two font tables**, so every one of them rendered identically whichever table was consulted.
The only two codes that could have told the tables apart were the two being added, and both were
blank, which is the symptom rather than the control. **Before trusting a large control set, ask what
result it would have produced under the hypothesis you have not considered. If the answer is the
same result, it is not a control.**

Corollary, and it is the same rule pointed at an address instead of a detector: **validate the
ADDRESS against a case where the content is known.** A wrong address makes a correct measurement
meaningless, and no gate catches it, because every gate downstream is measuring the wrong bytes
accurately. One phase reported a descriptor's virtual address 0x700 too low, and the experiment
built on it read unrelated bytes, reported them correctly, and was carried as a result for
**fifteen phases**. The check costs nothing: the same mapping applied to a known landmark, the font
table base, resolves to the value already in the library. **Run the mapping on the landmark before
you run it on the unknown.** When an experiment built on an address turns out to have been reading
elsewhere, the result is VOID rather than wrong: it never tested anything, and carrying it as a
negative is worse than having no result at all.

Corollary, and it is the rule pointed at a REGION instead of a detector: **zero bytes in a shipped
image are not free space.** A region can read as zeros because it is an arena that ships empty: a
heap, a pool, a scratch buffer. Four kilobytes of zeros below the boot clear, with no statically
resolvable write reaching them, looked like the safest space in the executable and were
`InitHeap(0x800B9204, 4060)`. **Find the code that OWNS a region, not just the code that writes to
it.** The owner here was one `addiu` and a BIOS call, two hundred bytes away from anything the
address scan reported, and the address scan was not wrong: nothing writes to a heap statically,
which is exactly why the scan was silent. **The validating case is the one where the content is
present, and for an arena that means at runtime, not in the image.**

Corollary, and it is the rule pointed at an ALPHABET: **validate a character table on text that
exercises every class of character you intend to read.** A crib found a text block at one additive
offset and the block decoded into real English, so the table was trusted and used for four separate
searches that all returned clean negatives. **The table was right about uppercase and wrong about
every lowercase letter**, which sat in a different code range entirely. The two crib words were
`LEVEL` and `GOLD`: both uppercase, so neither could ever have detected the fault. **A partial
instrument VALIDATES, which is worse than one that fails**, because a failure sends you looking and
a pass sends you on. The searches that came back empty were searching for mixed-case words that no
single-key cipher could have matched.

Corollary, and it is the rule pointed at a SEARCH: **a search whose candidate set is derived from its
own premise cannot find anything outside it.** A walk meant to enumerate a scene's text blocks
selected sectors *by whether they referenced a block already known*, so it could only ever return the
set it started from, and it did: four blocks, "no extras". A fifth existed, 85 sectors past the
arbitrary window the same walk used. **It was found by the cheap external check instead, reading a
line off a screenshot and grepping.** Before trusting an enumeration, ask what it would have to be
told in order to find something you have not already got.

Corollary, and it has now cost four phases in six: **before rewriting any referrer, enumerate every
POPULATION that can hold one, and prove the enumeration is not seeded from what you already have.**
Three builds in a row scoped a search to the population already in hand: twice to the executable
alone when the archive held four times as many references, and once to a set of sectors selected by
whether they referenced a block already known. **Each time every gate passed, because the checker was
handed the writer's list.** The fix is structural, not attentional: the checker must take its list
from the PRISTINE artifact and never from the build, so that a reference the build never knew about
is still checked. A gate built that way failed the bad disc at 4,631 of 5,833 and passed the good one
at 5,833 of 5,833; the gate it replaced passed both.

Corollary, third instance, and this one was not a search at all: **a CLASS is not a RANGE.** A set
of on-screen messages was scoped as "indices 584 to 627, contiguous, no gaps" and authored to
completion on that basis. The contiguity was real and proved nothing: six more members of the same
class sit at indices 30 to 35, two hundred entries earlier, and twenty-two more occurrences of it
live in the archive rather than the executable. The range was taken from the messages already in
hand, so it could only ever contain them. **Enumerate a class from what the player sees, not from
where the ones you have already found happen to sit**, and treat an index range as a summary of the
answer rather than a definition of the question.

Corollary, fourth instance, and it is the same rule pointed at the OTHER end of the pipeline:
**AUTHORED IS NOT DISPLAYED.** A string can exist, be correct, sit at the right index and still
have nothing that puts it on screen. A title menu was recorded as reading four entries because
four strings decoded as those four entries. The window draws three. The fourth was authored, was
spelled correctly, passed every gate and is dead: zero referrers in all four reference populations,
and the builder the window template names is twenty-nine instructions with no branches and exactly
three draw calls, read to its `jr ra`. Reading the strings answered a question nobody had asked.
**Enumerate what a screen shows from the code that draws it, not from the text that could fill it.**

The method that settled it is the reusable part, and it is rule 1 applied before trusting a result
rather than after: **the instrument was validated on three windows whose entry counts were already
known, and the three are NOT equal in weight.** One of them, the field menu at six entries, was
checked against a capture read in that same phase. The other two, a six and a two, agree with entry
lists already recorded in this project's own notes, and the report says so in as many words:
agreement with the repo's own measurements, not with a capture read that phase.

**So the validation is one observation and two consistency checks**, and by rule 4 a consistency
check against your own notes can only report that the notes agree with themselves. It is worth
having and it is worth less than three captures would have been. Say which is which. The count
taken cold, against nothing, would have been a guess, and a count described as three observations
when one of them is an observation is rule 4's failure mode hiding inside rule 1's remedy.

Corollary, and it is the rule pointed at a PROPERTY rather than a search: **a property measured on
one block is not a rule until it is measured across the population that shares its shape.** A rebuild
path asserted that a block's dictionary ends on a 4-byte boundary, because the block it was written
for does. Thirty-nine copies of another block ship with it ending two bytes earlier. Measured across
all six blocks of that shape the real rule is different and simple, the payload end rounded UP to a
multiple of 4, and it was 0 violations once asked properly. The cost of asking is one loop; the cost
of not asking is a path that works on the block you aimed at and silently refuses or corrupts the
rest.

Corollary, and the cheapest one to fall for: **a search inherits every blind spot of the formatter it
prints through.** A decoder emitted character and control symbols and silently dropped phrase
dictionary references. Every string built from those references was invisible to every search built
on it, and worse, they did not vanish: they came back TRUNCATED, so `LO! FOUND` read as a different
and shorter string rather than as a symbol class gone missing. A whole block of 336 strings was
searched twice and reported clean while holding the eight messages being looked for. The rule for
measuring a line already said to expand the dictionary first; it applies to SEARCHING for one too,
and searching is where it costs more, because a measurement that drops symbols is merely wrong while
a search that drops them reports that the thing is not there.

Corollary, and it is the sharpest form of the rule: **a search can be complete over every population
and every alignment and still be complete over the wrong THING.** Four phases enumerated references
to a text block by looking for the assembled 32-bit word, widening the search each time to more
populations, more sub-block types, every byte alignment. The count kept rising and the answer stayed
wrong, because **a compiler cannot emit a 32-bit immediate in one instruction**: menu code builds the
reference with a `lui`/`addiu` pair and the assembled word never exists in the image at all. The
missing references were not hiding in an unsearched region; they were not words. **When an
exhaustive search returns zero for something that demonstrably happens, stop widening the search and
question what you are searching FOR.**

Corollary, and it is the rule pointed at an INSTRUMENT rather than a search: **an instrument that
uses the thing it is measuring as its own identity test cannot report a discrepancy.** Two of these
in three phases, and they are the same shape as the enumeration corollary above. A figure for
character advance was obtained by dividing a window's width by an assumed character count, so it
could only ever reproduce that width and it silently absorbed every error in the assumption; it
survived three phases and was contradicted the first time a window drew text whose length was known
independently. An enumerator of live window records identified a record by matching its geometry
against its template, so a record whose geometry had been overridden at runtime was not recognized
as a record at all, and the tool reported perfect agreement while sitting on two overrides.
**Before trusting an instrument, ask what it would report if the thing it measures were different
from what you expect. If the answer is "nothing", it is not an instrument.**

## 2. Check a hypothesis against BOTH halves of the symptom before testing it

If a symptom has two parts, a candidate cause that can only account for one of them is either not
the cause or you have two causes. **Check that before spending a phase on it, not after.**

Two resources failed together and were treated as one symptom. A boot-time RAM clear was proposed,
measured carefully, and disproved. **It could never have explained the second half**, which is data
uploaded to video memory and cannot be touched by a loop that zeroes main RAM. The hypothesis was
disqualified before the work started and nobody applied the test.

**Applied retroactively to twenty dead hypotheses: thirteen could only ever have explained one
half.** Each was a correct measurement of something that could not have been the cause.

The filter also has a positive use. When nothing survives it, the two halves are co-occurring rather
than sharing a cause, and should be split into separate problems with separate evidence.

## 3. Never ship a test whose failure is invisible

**Cost: eight phases.**

Every diagnostic build needs at least one change that identifies it on screen **regardless of which
hypothesis turns out to be true**.

Four consecutive builds carried byte-identical dialogue and differed only in the thing under test.
When that thing failed to appear, the build was indistinguishable from the one before it, and a
negative result could not be told apart from "the wrong file was loaded". Adding one visible change
on a channel already known to work ended the ambiguity in a single boot.

## 4. A gate written from your own model only tests your own model

**Four instances.**

Gates that caught real faults all compared against an invariant **the shipped data exhibits**, not
against an expectation derived from the model being tested.

| fault | caught by |
| --- | --- |
| a collapsed decoder tree | bits per symbol across the corpus |
| compressor overrun drift | the distribution of overruns in the untouched data |
| a wrong font table reading | a twenty-character companion resolved through the game's own chain |
| a sub-block alignment fault | a census of all 23,828 sub-blocks |

Corollaries:

- **Every gate needs a companion that a degenerate result would fail.** A byte-exact round trip
  passed on a collapsed tree; only bits-per-symbol exposed it.
- **A gate that can pass trivially is not a gate.** Say so and replace it rather than banking the
  pass.
- **An identity check passes on a degenerate structure by construction.** Rebuilding X from X and
  comparing proves nothing about X.

## 5. Every test build must target something reachable, and the report must say where

**Two instances, both below.** This header read "three" over a body that has only ever listed
two. The third was never written down, so it is not claimed. **An instance count is a pointer
into this file, not a score**, and one that points at nothing is the same defect as a rule that
cites a document not containing it.

Reachable from a fresh start in under two minutes, fired unconditionally, and the report says in
plain language where in the game it appears and how to get there.

- A build targeted the most conditional line in a scene; it never fired.
- A build targeted a character name that does not exist until the next chapter. The tester played
  the prologue, so the test returned **no information at all** and the phase was wasted.

## 6. MEASURED or INFERRED, in the same sentence as the claim

MEASURED means the bytes say so and you read them. Everything else is INFERRED and says so where it
is stated, not in a footnote.

- **Do not say what a routine is NOT until you have read it to its return.** A claim by negation
  from a partial read is invisible to every boundary check, because no boundary was crossed.
- **Prior documentation is a source of hypotheses, not facts.** Every inherited claim that got
  checked was worth checking, and several were wrong. Several others were right and worth crediting
  precisely.

## 7. Write the reading down before the experiment, and do not fit the result

State what each outcome would mean **before** running it. When the result does not land cleanly in
one of them, call it ambiguous and say what would separate the remainder. Fitting an odd result to
the nearest row sends the next phase hunting a fault that is not there.

One result looked like "both changes appeared" and was actually "neither changed, both kept their
old values", which is a different outcome with a different cause. Taking the nearest row would have
cost another two phases.

## 8. A model fitted to one case can be exactly wrong

If a model has two terms that happen to cancel in the case you fitted it to, it will look correct
there and fail everywhere else.

An expansion model was calibrated on one small block where the growth of one region and the saving
in another nearly canceled. On a block nine times larger the saving grew fourfold and the growth
elevenfold. The model under-predicted by a factor of five, and it was missing a third term entirely.

**Fit on at least two cases that differ in the dimension you expect to matter.**

## 9. Read the other language

**Two instances, on two different platforms.**

If the game shipped in another language, that build is a worked example of every problem you are
trying to solve. One pass over a Japanese and English pair answered, in an afternoon, a question
five phases of single-sided measurement had got backwards: the English build was **smaller**, and
the developers had solved the space problem by dropping a table the other language does not need.

## 10. When a number moves, decompose it until the arithmetic closes

**A derived count that disagrees means the derivation is wrong somewhere. Fix the cause, not the
number.**

- Two character totals differing by 2,073 resolved exactly to residue characters that one count
  included and the other did not.
- A reference count of 287 against 285 was a status column with precedence hiding two entries.
  **A status field that picks one label per row is lossy; derive counts from the measurement, not
  from the label.**

## 11. Static verification never scores

Count only observed runtime behavior. A prior effort reported very high completion against static
checks on a build that never booted.

**No percentage of completion anywhere.** It is the same failure wearing a number.

## 12. Where a thing appears matters more than how often

Choosing a donor character by lowest occurrence count would have consumed a menu entry that **was**
the entire string, and separately would have deleted three letters the target language needs. Count
is a weak proxy; look at every site.

## 13. A wrong origin looks exactly like a refutation

Test the obvious alternate bases before concluding a field is not what you think.

A pointer hypothesis scored at chance and was nearly abandoned. It was displaced by a constant 192
bits. Related: **the same bytes at every alignment is not evidence for one alignment**, and picking
one residue of four while calling the rest noise is not a measurement.

## 14. Code first

Blind pattern scans returned chance results three times running. Disassembly resolved every system
those scans could not. Scanning is for confirming a hypothesis the code gave you, not for finding
one.

## 15. Calibrate a threshold on the population you are testing

A similarity threshold calibrated on one script gave 91 and on another gave 66. A threshold carried
across populations is a guess wearing a number.

## 16. Retract in place

**A retraction placed far from the claim it retracts is not a retraction.** Head the original claim,
keep the wrong version visible so the reader knows what they may have carried away, and state what
was measured instead.

## 17. Record what was ruled out

Keep a list of dead hypotheses with what killed each one and where. Seventeen of them exist here so
that nobody retreads them. It is worth as much as the list of what was found.

## 18. **[PSX]** In a per-block Huffman codec, DUPLICATED text is cheaper than distinct text

This inverts the usual instinct and it is worth stating before anyone shortens a string to save
space again.

Each text block carries **its own** Huffman tree, built over that block's own symbol frequencies. A
phrase that already appears in the block costs almost nothing to repeat, because every symbol in it
is already frequent and therefore already short. A *shorter but different* phrase can cost more: it
introduces symbols the block does not otherwise use, which lengthens their codes and every other
code that shares a prefix with them.

Measured, twice:

- Translating six messages **into** a block that was 4 bytes from full left it 8 bytes **smaller**,
  because the English reused vocabulary the block's other messages already carried.
- Translating two duplicated strings identically produced a smaller block than translating them
  distinctly, at equal character count.

Two consequences. **Translate duplicates identically unless there is an editorial reason not to**,
and **do not trim English on size grounds without measuring**: shortening a line by choosing rarer
words makes the block bigger. Measure the block, not the string.

## 19. **[PSX]** When a block is tight, reduce the ALPHABET before shortening the text

The generalization of rule 18 and the reason it keeps surprising people. In a block whose text is
one script, **every character of a second script is a NEW TREE LEAF**, and a leaf costs both its
own tree entry and a lengthening of every code that shares a prefix with it. So the price of a
translated line is dominated by **how many DISTINCT characters it introduces**, not by how long it
is.

Measured on a block with zero slack, translating eight strings:

| draft | distinct characters | result |
| --- | --- | --- |
| written for register | 18 | over capacity by 52 |
| same eight, minimal alphabet | 11 | fits, 4 bytes to spare |

The two drafts say the same things at nearly the same length. **Dropping the full stop alone moved
one draft from over-by-52 to fitting**, because the English full stop widens to a character the
Japanese never uses while the exclamation mark, the question mark and the space widen to characters
already in the block.

So: **check which punctuation is already in the block before writing a line**, prefer words built
from letters already spent, and reach for a shorter sentence only after the alphabet is as small as
it will go. Shortening a line by choosing rarer words makes the block BIGGER.

Corollary, a CLOSED ROUTE: **do not retune a phrase dictionary to fit a translation.** It was tried
against a block with no room, in several scorings. Scoring phrases by symbols removed ignores that
each costs two bytes of index plus two per symbol of payload, accepts anything used twice, and fills
the payload to its cap: over by 1,788. Making the score cost-aware improved it to over by 1,184 and
still lost, because occurrences are counted before substitution and long phrases cannibalize the
short ones inside them. **The shipped table beat every alternative generated.** Emptying the table
entirely was worth +40 bytes and was the only dictionary move that helped at all.

## 20. What the build carries through unchanged is verified by nothing

**The build's BASE is not the pristine artifact.** Gates that compare a build against the file it was
built from cannot see anything already wrong in that file, and data the build copies without touching
is data no gate ever looks at. Carrying data through feels like the safe path precisely because
nothing happens to it.

A diagnostic once substituted two characters throughout a text block to prove two new glyphs
rendered. It was left in the build base. **67 occurrences of one character and 28 of another shipped
as an apostrophe and a semicolon on every disc built afterwards**, in a block where 597 strings are
carried through untouched and were therefore compared to nothing. Every gate passed every time,
because every gate was handed the same corrupted base.

Two rules follow. **Diagnostic edits go in a build, never in a base**, and if one must go in a base it
gets a gate that fails until it is removed. And **gate the carried data too**: decode what the build
copies and compare it to the pristine artifact, not to the intermediate. That check is cheap, it runs
in a second, and it is the only thing standing between a stale experiment and a shipped disc.

Corollary: **a substitution is only invisible if the replacement draws the same pixels.** Check the
glyph, not the code. The two replacement codes here had their own font entries at 3 units wide
against 11 for the characters they displaced, which is the whole difference between a relabeling and
a defect.

## 21. **[PSX]** A rebuilt Huffman tree differs in SHAPE and not in QUALITY

Rebuilding a tree from the frequencies of the same symbols gives a DIFFERENT pair array that encodes
those symbols in EXACTLY the same number of bits: 41,370 both ways on one block, 43,519 both ways on
another, same pair count and same node count in both. Huffman ties are broken arbitrarily and any
tie-breaking order is optimal.

So **tree-shape divergence after a rebuild is not a defect and is not evidence of one.** Do not spend
a phase bisecting it. The practical consequence is for identity gates: a rebuild that must reproduce
its input byte for byte has to REUSE the parsed pair array, because rebuilding the tree is not
obliged to reproduce it and usually will not. Reusing it is what makes such a gate meaningful, and it
still tests every other stage.

## 22. **[PSX]** Boot tests start from a cold emulator process

Not a reset, not a disc swap, not opening a file in a running window. **Starting a new game reloads
save data, not the executable.** Asking whether a save state was used got a truthful "no" that was
not the question, and the wrong question was treated as dispositive for two builds.

## 23. Counting a set is not identifying it

**First of four rules that are one family, and the family is worth more than any of the four
separately: a measurement that is TRUE and a conclusion that is NOT. The others are 24, 25 and
26.** Every one of them began with bytes read correctly and ended in a claim those bytes did
not support, which is why no check aimed at the measurement could have caught any of them. The
question that separates the family is not "did I read this right" but **"what else would
produce exactly this reading".**

A count describes the SIZE of a set. It says nothing about what the members are, and a set
whose members are all one repeated thing counts exactly like a set of distinct things.

Phase 96 found 819 words in a battle overlay that were valid references to a text block **by
value**, and reported an 819-reference regression on that basis, overruling a tool that
disagreed. Phase 97 read the values instead of counting them: all 819 are the single word
`0x48C0AA4F`, in consecutive runs, and its MIPS opcode field is 0x12, COP2. They are filler.
The tool had been right the whole time.

Cost: a regression reported on a count, a working tool overruled on the strength of it, and a
retraction the next phase had to open with. **A `Counter` over the values, one line, would have
ended it before the regression was written down. Print the distinct values of a set before
reporting its size.**

## 24. A gate that races what it checks is worse than no gate

Second of the family in 23. The bytes were read correctly; they were not the artifact.

Phase 95's first verification run started 20 seconds after `FIGHT.bin` appeared on disk, while
the second `discbuild.inject` was still writing 368 MB into that same file. It read a partially
written disc and **exited 0**. Nothing it passed was ever the build.

This is worse than having no gate at all, and the asymmetry is the point. With no gate the
build is known to be unverified and gets treated accordingly. With a racing gate the build
carries a pass, and the next thing spent on it is a boot test, which is the most expensive
attention in the project.

Three fixes, all cheap: **wait on the PROCESS, not on the file appearing**; **hash the artifact
before and after the read and fail if it moved**; **refuse to run at all while the builder's
temporary file exists.**

## 25. A value that fits the hypothesis is not evidence it was used

Third of the family in 23. Registers hold whatever was last put in them, and a stale one is
still a real value that a dump reports accurately.

Phase 99 nearly reported `a2 = 0x800B07C2` as the smoking gun for the battle message box. It
has every property the hypothesis wanted: it lands inside `0x048C`, and its region differs
between discs. The format string at that call site is `"%s"`, which consumes `a1`, and `a1`
there held `0x80022F3C`, a two-byte string in the executable. `a2` was a leftover from an
earlier call and was never read.

**Before a value that fits counts as evidence, show the code CONSUMED it**: read the format
string, the arity, or the instruction that actually uses the register. A fit is a reason to go
and check, never a result.

## 26. A string read wrong looks exactly like a string resolved wrong

Fourth of the family in 23. Before hunting the machinery that put a string on screen, check that
the string says what you think it says.

`Foresee` was carried as a reference that resolved to the wrong index, and the shop that drew it
was carried as **"the reproducible instance of the same fault"** as a corruption elsewhere on the
screen. That is the framing, in its own words, that Phase 105 overturns. Phase 105 put the pristine Japanese disc alongside ours and found the shipped game
drawing `うれない` in the same cell: `0x048C[652]`, the very string that renders as `Foresee` on
ours. **There was no reference fault, no offset error and no wrong branch.** `うれない` is
売れない, "cannot be sold", and it had been read as うらない, 占い, divination. The shop was
never faulty.

**The discriminator was already in hand and cost one query.** `[652]` has 228 reference sites
against 5 to 10 for each of its neighbors. 228 is a per-item marker evaluated once per shop
row; a fortune-telling verb is one menu entry. **A reference count is a cheap type test for
what a string IS**, and it disagreed with the translation before any of the hunting started.

## 27. Verify every doc edit by reading the file back

**Cost: several false "handoff updated" claims, and one destroyed working document.**

Same shape as 24. A script that prints its success line has proved that it reached its success
line, which is a true measurement, and "the file changed" is a conclusion it does not support.

- **A `replace` that matches nothing prints exactly the same success line as one that works.**
  Phase 107 checked several earlier updates to a working document and found the text had never
  been written; the script had reported success every time and nobody read the file back.
- **A `replace` on an EMPTY slice inserts the replacement between every character of the
  file.** That is what destroyed the document, and it was recovered only by stripping the
  insertion back out, which worked only because the insertion was uniform.

So: never `replace` on an empty slice, check the line count before and after every edit, and
**`grep` the text back out of the file on disk**. The write is not done until it has been read
back. This applies to documents exactly as rule 4 applies to builds: the record is an artifact,
and an unverified edit to it is an unverified build.

---

---

# Reframing

**Separate section, different evidence.** The rules above entered because violating them cost a
phase, and they are ordered by that cost. These entered because applying them **saved** phases,
which is a different kind of claim and should not be mixed in, or the ordering above stops meaning
anything.

## The rule

**When measurement inside a frame stops paying, change what you are comparing against rather than
measuring harder.**

The failure this addresses is not a wrong measurement. It is a **correct measurement of the wrong
comparison**, and measuring harder makes it worse, because every clean result reinforces the frame.

Symptoms that the frame is the problem rather than the measurement:

- the same question has been asked more than twice
- hypotheses keep dying cleanly and the phenomenon does not move
- every result is negative and none of them is surprising
- the next test is a variant of the last one

## Worked instances

Each one has a measured before and after. That is the bar for entry.

**Reading the other language.** Five phases measured one game alone and concluded that a relocation
subsystem was required before the text could grow. One pass over a Japanese and English pair of the
same engine showed the developers had dropped a per-language table instead, and the conclusion
reversed: the English blocks came out **smaller**, and the block that could not be made to fit fits
with 2,748 bytes to spare. The comparison changed. The measurement did not get better.

**Which channel, not which bytes.** Nine phases asked why a change did not render. Every hypothesis
was about bytes rendering: the upload extent, the atlas, the table, the sector form, the boot
sectors. None asked **which channel the change traveled on** until the frame was changed to
streamed-at-scene-time against loaded-at-boot. That one sentence covered every observation the nine
phases had produced.

**Which change, not which channel.** Fifteen phases could not separate "edits to the executable do
not arrive" from "something specifically touches the font table", and measured harder against both.
They were indistinguishable because **every executable test until then had been a font table edit**:
the frame had one variable where it needed two. One change to a different part of the same file,
chosen only because it was not the font table, separated them in a **single boot**. The channel was
fine; the region was not.

**What editable means.** Editability had been framed as "does every string in this block have a
referrer". Reframed as "does any **unresolved** string follow this one", the editable figure went
from 139,192 characters to 488,490 **with no new measurement at all**. The bytes had not changed;
the question had.

## How to use it

A candidate frame costs one query against data already in hand. Generate several, test each against
measurement, discard the ones that do not move a number.

**The discipline is in the discard, not the generation.** A frame that survives one check is not
confirmed. Two of this project's dead hypotheses were reframings that looked good arithmetically
and were promoted before being tested; one of them was published and had to be retracted.

**Do not spend a phase on a reframe.** If it cannot be probed with existing data in a few queries,
it is an ordinary hypothesis and belongs in the normal cycle.

## The form most worth keeping

**When one side is ambiguous, find a case where the problem was already solved and read the
difference.**

That is what a two-language pair is. It is also why prior art, shipped localizations, and the same
engine in another title are worth **measuring** rather than only reading about. A shipped build in
the target language is a complete worked answer to every question about what the format can be made
to do.

## Maintenance

Add an instance when a reframe demonstrably reverses or shortcuts a conclusion, naming the phase and
what it replaced. **Do not add candidate frames that were merely plausible.** This section is worth
having only while every entry has a measured before and after.

---

**27 cost-entered rules, plus the reframing section with 4 worked instances.** Instance counts,
taken by counting the instances written under each entry: rule 1 has seventeen, rule 4 has four,
rule 5 has two, rule 9 has two. Everything else has one. **Rules 23 through 26 are one family**,
a measurement that is true and a conclusion that is not, and 27 is the same shape aimed at a
document.

**Rule 1's seventeenth instance used to sit below this section**, stranded after "Maintenance"
and outside the rule it belongs to, where a heading-based count could not see it and returned
sixteen. It has been moved back inside rule 1. A count that disagrees with a header is a
question about where the text lives before it is a question about the header.

The previous version of this line read "18 cost-entered rules" and attributed the instance
counts to rules 3, 4 and 8. Both were stale: the rules had been renumbered and the footer had
not, and the count was **four short** of the 22 entries that stood before this section was
added. An earlier draft of this paragraph said five, which is the defect it is describing
wearing the correction's clothes. **Count the headings, do not subtract from memory.**

Linked from `FORMAT.md` and from the working notes. **One authoritative location per fact**: nothing
here is duplicated into those files, and format claims are not duplicated into this one.
