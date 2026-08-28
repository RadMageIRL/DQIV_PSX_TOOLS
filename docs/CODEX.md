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

**The most expensive rule here. Its worst single instances cost twenty-five phases, fifteen phases, and a boot test.**

> **THE INSTANCE COUNT IS OPEN AS OF 2026-08-27, and it is flagged rather than replaced, because
> replacing it would be the defect this file's own footer describes.** This line read **eighteen**.
> A recount against the body could not reproduce that figure and could not produce a defensible
> single figure either: **three of the corollaries below carry more than one episode each** (the
> static-value corollary holds two, the identity-test corollary says "two of these in three
> phases", and the referrer corollary says "three builds in a row"), so **the answer is twenty or
> twenty-two depending on whether an instance is a CASE or a COROLLARY, and the file has never
> said which.** A second instance was added below on 2026-08-27, which moves whichever figure is
> right by one.
>
> **The remedy is a definition, not a number, and it is not applied here because applying it would
> mean rewriting eighteen headers in one pass with nobody to check them.** Until it is: **treat
> rule 1's instance count as UNCOUNTED.** No figure for it may be quoted, here or in any file that
> points at this one. **A count that cannot be reproduced from the text below it is not a
> measurement, and carrying it as one is what put five stale figures into `docs/BOARD.md`.**

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
resolvable write reaching them, looked like the safest space in the executable and were **owned by
a BIOS routine reached through table B, function `0x19`** with `a0 = 0x800B9204`. **Find the code
that OWNS a region, not just the code that writes to it.**

> **THE ROUTINE'S NAME IS OPEN AS OF 2026-08-26 AND THIS RULE DOES NOT DEPEND ON IT.** This
> paragraph used to name it `InitHeap(0x800B9204, 4060)`. The project's own disassembly puts the
> call on table **B** at function **`0x19`**, while psx-spx's kernel BIOS documentation says `B(19h)`
> is `HookEntryInt` and puts `InitHeap` on the **A** table at `A(39h)`; the recorded second argument
> came from an `addiu` writing **`v0`**, not `a1`. **The ownership is not in doubt** and was
> established on hardware, where a build placed two chains in that region and shipped letters
> disappeared. **Only the name and arity are.** Raised and left OPEN in Phase 114, on the working
> record. Rule 36's near-miss is this same discrepancy read as a method failure. The owner here was one `addiu` and a BIOS call, two hundred bytes away from anything the
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

Corollary, same shape and the domain is a PARAMETER RANGE rather than an alphabet: **A SWEEP THAT
STOPS SHORT MEASURES THE SWEEP.** A compressor setting was swept over `{16, 32, 52, 64, 128, 256,
512}` and reported that **48 of 55 carriers grow on an IDENTITY recompression, with no text
changed at all**, one of them already past its sector slack. The finding was real, reproducible
and about to shape three phases, and it named a sector as a blocker. **The shipped archive was
packed at a chain depth ABOVE 512.** At 2048 the unchanged carrier reproduces the shipped length
**exactly, +0**, and the authored English comes out **80 bytes SMALLER** than the Japanese it
replaces.

**The validating case was free and was never run: recompress the UNCHANGED shipped data and
require it to reproduce the shipped bytes.** An identity recompression that does not reproduce
its input has not measured expansion, it has measured the gap between the sweep and the packer.
Anything a sweep reports outside the range it covered is a property of the range.

**This is the general form worth carrying, and it spans more than one rule here: THE
INSTRUMENT'S OWN LIMIT REPORTED AS A PROPERTY OF THE DATA.** Rule 4's fifth instance is its other
face, a check whose reference came from its subject and therefore could not fail. **The two are
not the same defect and the difference decides where to look.** That check could never return
FAIL under any configuration. **This sweep could fail, did fail things, and returned a real
number; what it could not do was see outside its own range.** When an instrument is silent, ask
what it compares against. When an instrument answers, ask what it covered.

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

**SECOND INSTANCE, Phase 118, and it is not a repeat: the first cost a COUNT, this one cost a
SHIPPED DISC.** The same blind spot moved from the enumerator to the REWRITER. When a block was
re-encoded and its string offsets moved, the referrer rewriter updated every reference it could
find and **could not find any of the seven that address that block, because every one of them is a
split immediate.** Six broke and the priest's slot list drew empty at every priest. **A manifest
row read PRESENT and the text was unreachable**, because the strings were present; nothing pointed
at them. **The seventh survived because string 0 sits at bit offset 0, and offset 0 never moves.
That is what proves the diagnosis rather than merely fitting it.**

**And the difference between an undercount and a broken disc is where the blind instrument sits.**
An enumerator that cannot see a form reports a low number that someone may notice. **A rewriter
that cannot see a form silently declines to fix it, and the build is green**, because the gate was
handed the same list the rewriter used. Rule 4, and rule 1's referrer corollary above.

**The blind spots are a list of FORMS, not a count of sites, and a count of sites is the wrong
deliverable here.** Recorded because each one defeats a different filter:

- **`lui` + `ori`.** The composed word exists only at runtime.
- **`lui` + `addiu`.** The `addiu` is SIGN EXTENDED, so **the upper half is off by one when bit 15
  is set** and a filter keyed on the expected `lui` immediate MISSES THESE.
- **`lui` plus the offset field of `lw`/`lb`/`sw`, with no second arithmetic instruction at all.**
- **Non-adjacent pairs**, with unrelated instructions scheduled between the halves.
- **`$gp`-relative loads**, where neither half names the address.
- **Overlays as well as the main executable.** A sweep scoped to one image is scoped to one image.

**A tool that pairs halves by scanning forward with a register-clobber model is APPROXIMATE by
construction, and it must say so in its own output.** The instrument built for this one does, in
its own comment: **absence is evidence, not proof.**

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

### The remedy has a REPORTING FORM, and `pass` is not it

**Recorded Phase 118. The diagnosis half of this is already above and in rule 30**, which works
through a search that returns zero whether or not the thing exists and names that blind. **What was
never written down is what the validating run should PRINT, and it is not a boolean.**

The occasion: a census over a block reported **zero referrers**, and that was the exact output the
card blocks had produced one hour before the split immediates were found. **Two readings, and
nothing in the output separates them.**

| reading | meaning |
| --- | --- |
| no referrers exist | the text is genuinely orphaned |
| referrers exist in a form neither scan sees | the failure above, one layer deeper |

> **The discriminator is not a better search. It is running the scanner against a set of
> references that are KNOWN to exist and reporting `found/6`, not `pass`.**

**A fraction names its own denominator; `pass` conceals it.** `pass` is what a scanner prints when
it recovered every known reference AND what it prints when the harness handed it nothing, and those
are the two cases the harness exists to tell apart. This is rule 33's form applied to a VALIDATION
RUN rather than to a finding, and it is the leg rule 33 does not cover: 33 governs how you state an
answer, this governs how the instrument that produced it reports on itself.

**AND THE CONSEQUENCE IS RETROACTIVE, WHICH IS THE HALF THAT IS EASY TO DROP.**

> **If the harness does not recover all six, every clean result that scanner has already produced
> reverts to UNCONFIRMED**, including sweeps that were used to clear other faults. A scanner is not
> re-validated by the phases it has survived.

**And a zero that has not been through this says nothing, including a zero that is currently
blocking a decision.** Twenty-six authored strings sat unshippable on a zero-referrer measurement
that had never been put against a known-present case. **The cost of leaving that zero unvalidated
is not a wrong answer; it is a decision made against a number with no meaning yet.** Rule 28's
shape, and rule 33's remedy.

**PRIOR-SOLVED IS AN INSTRUMENT TOO.** When the same engine shipped in another language and that
release reaches the strings in question, **how its code addresses the block NAMES THE FORM to look
for**, and it costs one read rather than another sweep. See the reframing section's closing form.

### A worked example of the reporting form, 2026-08-27: the screenshot reader

**Added as an EXAMPLE, not as a new rule.** It is the same failure as the census corollary above,
in a different medium, and the point of recording it is that the shape was recognizable while the
run was still going.

A bisect needed to know which build first showed a hang. The marker was the emulator's on-screen
frame counter, so a reader was written to classify every frame in a large screenshot corpus as
running or stopped. It **matched the status bar as an exact block of RGB values.**

**It came back clean on 1,170 of 1,452 frames it could not read at all.** The text was plainly
present in every one of them. The cause is **subpixel text rendering**: the same string drawn at a
different sub-pixel offset gets different color fringes on its glyph edges, so an exact-color test
matches the frames that happen to land on a whole pixel and silently misses the rest.

> **A reader that cannot see the counter and a build that never stopped PRODUCE IDENTICAL OUTPUT.**
> **This is the referrer census in a different medium: "no referrers found" and "no referrers
> visible to this scan" are the same string.**

**Three things made it recoverable, and all three are the reporting form rather than the fix:**

1. **The blind count was reported as a NUMBER, not folded into the clean count.** The corrected
   reader binarizes on luminance with a tolerance and reports **100 unresolved**, every one of which
   was then sampled by hand and found to hold an ordinary non-target value. **Unresolved is a third
   outcome and it must survive to the summary.** A two-valued report has nowhere to put "I could not
   see this one."
2. **A second self-inflicted blindness was caught by a control the instrument had ALREADY PASSED.**
   A prefilter was added with a budget tighter than the verifier's own tolerance, so the fast path
   rejected frames the slow path accepted. **It failed a control it had passed an hour earlier**,
   which is the cheapest possible detection and only exists if controls are re-run rather than
   retired.
3. **BOTH BLIND VERSIONS WERE KEPT AND MARKED, NOT DELETED.** They are on disk labelled
   **SUPERSEDED, BLIND**. Deleting a bad instrument destroys the only evidence of what its clean
   output looked like, and the next person to write one will write the same thing.

**And the retraction landed inside the same run that produced the result**, so the finding and its
correction arrived together rather than the finding standing alone for a week. **That is what
`found/N` buys over `pass`: a run that reports how much it could see is a run that can notice it
saw nothing.**

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

**Five instances.** The first four are the table below, gates that caught real faults. **The
fifth is a violation rather than a catch** and sits under the corollaries: a check that could not
fail.

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

**The fifth instance is the sharpest and it lived inside a tool rather than in a gate script.** A
repacker validated its output by reading an anchor value off **the disc it was building FROM**,
then checking the output against it. Evaluated on a finished disc, that asks whether a sub-block
agrees with itself. **It failed 0 of 23,828 sub-blocks on every disc ever built**, across four
that were genuinely clean and thirteen that were not, and the same check corrected to read its
anchor off the PRISTINE artifact fails exactly two sub-blocks on all thirteen bad discs and none
on the four good ones.

**What makes it worth recording is everything it was NOT.** It was not read wrongly, the way an
honest report can be. It was not out of date. It was not calibrated too tight or too loose.
**There was no configuration of it that could ever have returned FAIL**, so no amount of care in
reading it would have helped, and the tell was available at any time for free: the check had
never once fired.

**A check that has never failed is not evidence that nothing is wrong.** It is a question about
the check. Ask what artifact it compares against, and if the answer is "the one it came from",
it is an identity test wearing a gate's clothes. **The general form: A CHECK WHOSE REFERENCE IS
DERIVED FROM ITS SUBJECT CANNOT FAIL.**

**Cost: it ran on every build for months, cost nothing to run, and returned PASS 23,828 times per
disc, which is exactly why nobody suspected it**, while the defect it was blind to was dismissed
twelve times on the strength of a related reading. **A check that cannot fail is worse than no
check, because no check does not produce evidence of safety.**

**And this is the line that routes a future defect to the right rule.** Rules 23 through 32 are
all **honest instrument, wrong reading**: the tool told the truth and a reader drew a conclusion
it did not support. **This one is a DISHONEST instrument. Nobody misread it. It returned PASS on
thirteen defective discs.** There was no reader error available to make. So when a check is
silent, do not look for the misreading, because there may not be one; **look at what the check
compares against.** Rule 1's instrument corollary is the same defect pointed at a measurement
instead of a gate, and it carries the second instance of this exact shape: an enumerator that
kept only records whose live geometry matched their template, which hid every runtime override by
construction and reported perfect agreement while sitting on two of them.

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

### Second instance, 2026-08-26: a census that charged one code with two roles

**Two instances.** The first is a set whose members were all one repeated thing. **This one is
harder and is the more common shape: the members were genuinely different from each other, and two
DIFFERENT THINGS were wearing one code.**

A census reported **96 strings in `0x048F` with a line under a 9-cell floor, 90 of them surviving
fixes**, and the 90 were briefed as the population to work. **The Builder then retracted its own
finding: eighty-nine of the ninety are not defects.** Its census **charged a runtime-substitution
code as an unbounded noun everywhere the code appeared**, and that code has two roles the census
could not tell apart.

**The discriminator is STRUCTURAL, and this project already had it.** A description is a run of
segments each TERMINATED by the code, so the string ENDS with it. An existing gate's leg 1 has
skipped that class for phases using exactly this test:

```python
if not t or t.endswith("{7F11}"):
    continue
```

MEASURED on the 325-string held revision:

| | |
| --- | ---: |
| strings containing the code | **100** |
| **ending** with it: DESCRIPTION, its own **7-cell** window | **90** |
| **not** ending with it: RUNTIME substitution, a 21-cell line | **10** |

**The ninety were also being measured against the wrong window by a factor of three.** MEASURED:
248 shipped Japanese segments, longest **7**; 270 authored English segments, longest **7**; **0 of
90 over.** Of the ten runtime-role strings, seven were under the floor and all seven are now
authored. **The corrected distribution is 7 and 0, not 96 and 90.**

> **The count was arithmetically right every time it ran. The set it named was wrong.**

**THE TELL WAS IN THE CENSUS'S OWN OUTPUT THE WHOLE TIME: every one of the ninety ended with the
same code.**

**This widens rule 23's remedy by one word, and that is why it is worth its space.** "Print the
distinct VALUES before reporting the size" would have found nothing here: the ninety are ninety
different strings and a `Counter` over them returns ninety ones. **Print the distinct SHAPES.** A
`Counter` over "what does this string END with" separates the two roles in one line.

**And the part that is not about counting at all: the discriminator was already written down, in
this project's own gate, and had been applied for phases.** The defect was not a missing test. **It
was a test that lived in one tool and not in the one that produced the number**, which is a class no
amount of care inside the second tool would ever have caught.

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

## 28. UNCONFIRMED is a statement about the TOOL, not about the data

**The fifth member of the family in 23, and its tool-shaped one.** In 23 through 26 a
measurement is true and the conclusion drawn from it is not. Here the true measurement is **a
tool's own honest report about itself**, which is the hardest case to doubt, because there is
nothing wrong with it to find.

A reference collector printed this on every build for **ninety phases**:

```
type 46 UNCONFIRMED (no structure known)   236945
```

**Every word of that was true every time it printed.** The exclusion was deliberate, and the
module's own docstring said why: for this block the reference's top byte is `0x48`, which is the
COP2 opcode range, so overlay code produces a quarter of a million false positives. Rather than
silently keeping them or silently dropping them, the tool refused to classify them and **said
so**. The count was real. The rule was a good rule.

**What was never true was the reading: that "no structure known" meant "no structure exists",
and therefore that this population could not be rewritten.** Nobody re-asked whether the premise
still held, and by the time anyone did it had been overtaken by four independent measurements:

- all 236,937 four-aligned candidates across all 284 sub-blocks of that type are **ONE value**,
  and no sub-block holds more than one distinct value
- in the loaded overlay they sit in **two contiguous clusters**, 797 words and 22, with **zero
  outside**
- they sit at **record strides**, each preceded by another reference word or a small integer
- decisively, **the CPU was measured LOADING three of them as data** and passing them to the
  resolver, which consumed them

**Cost: a defect that survived TWELVE candidate hypotheses over many phases.** The population
the tool declined to classify was the population carrying the fault. When the premise was
finally re-asked, the fix was 62 lines added and 0 changed, and **the gate went silent on the
first known-GOOD companion it has ever had**, with four known-bad discs still firing.

**And the half that is easy to lose, because the obvious fix is the wrong one. FOUR-ALIGNMENT
WAS NOT THE DISCRIMINATOR.** 236,937 of the 236,945 candidates were **already** four-aligned, so
copying the neighboring type's test across would have kept essentially every false positive the
original rule existed to reject. The discriminator that works is **value plus cluster bounds**.

That it was not fitted to the data was proved rather than asserted: the threshold sits at 1,024
against a largest intra-cluster stride of **616** and a smallest inter-cluster gap of **11,508**,
and **every value between those two gives the identical answer of 236,937**. A discriminator with
a wide plateau around the value you picked is measured; one that only works at the value you
picked is fitted.

**So: a tool reporting that it cannot classify something is posing a standing question, not
returning an answer.** Give the refusal a date and the reason behind it, and re-ask whether the
reason still holds whenever the surrounding measurements move. This is drift guard 7 pointed at
an instrument instead of at a document: a stale dismissal is a claim believed because it is in
the record, and this is a claim believed **because a tool said it, accurately**.

## 29. A limit observed in output is not a limit of the system

**The third member of 23's family found in a single phase, and unlike the other two it cuts in
your favor.** Rule 28 is a TOOL's honest report read as a fact about the data. This one involves
no tool and no misread report: it is **an OUTPUT's observed range read as the system's
capacity**. Nobody made an error of measurement. The number was right about the thing it
measured, and the thing it measured was not the thing everyone thought.

A message box budget of 20 cells for a named box and 18 for an unnamed one governed **every
authoring decision in this project**, across a prologue, three pilots and hundreds of authored
strings. It was measured carefully, off a disc that had booted, and it is exactly right: **it is
the maximum the shipped English prologue reached.**

**What it measures is what ONE AUTHOR did.** It is a floor on the window, not the window.

**The check that broke it cost one query, and it is the reusable half of this entry: ask whether
the shipped ORIGINAL respects the limit you inferred.** It does not. On the very block being
authored against, **20 lines of the game's own shipped Japanese exceed the 18-cell cap, and the
longest runs to 21.**

> **A cap the shipped game breaks twenty times is not that block's cap.**

**So keep both numbers and never let them share a name.** The **BUDGET** is what an author has
reached and is a real, useful thing to hold a draft to. The **WINDOW** is what the system will
draw. Only the second can produce something on screen, and only the first was ever measured.

**The cost is subtle and worth stating exactly, because it is invisible in the artifact.** It
produced no defect. Nothing clipped, nothing overran, no build failed. **It produced unnecessary
tightness**: line after line squeezed to 18 cells that could have run to 21, and every editorial
loss taken to make that fit. Those losses are recorded in the record as window losses, and a
reader going back to them should know that **they were partly paid for a wall that was not
there.** A constraint that is too tight leaves no evidence of itself anywhere except in the
prose it quietly made worse, which is why it survived so long and why nothing would ever have
caught it.

**The general test, then.** When a limit is inferred from output rather than read out of the
system: **run it against the shipped original.** If the original breaks the limit, the limit
belongs to the observer and not to the system. It is the same instinct as rule 9, read the other
language, pointed at the same game instead of a different one, and it is one query.

## 30. A search for a literal cannot find a value that is computed

**The third of the family in 23 to be about an instrument's honest answer, and the one where the
instrument is not even wrong about its own domain.** Line them up, because the difference is the
whole entry:

- **28** is a TOOL's honest report about ITSELF, read as a fact about the data.
- **29** is a system's observed OUTPUT RANGE, read as its capacity.
- **30** is a search's honest ABSENCE, read as the absence of the thing.

The search here was correct. It found no literal **because there was no literal.** Nothing was
broken, nothing was misreported, and no amount of care applied to the tool would have changed
its answer. The fault is entirely in the assumption underneath the search: that the value must
exist somewhere as a written constant.

Twenty-two control codes stood unidentified, **two of them opening the boss scene's own
strings**, and every per-code search came back empty. They were cracked by reading a **DISPATCH
TABLE** instead: the engine tests the symbol against a threshold and, above it, indexes an
8-byte-per-entry table with `code - 0xFF00`, taking flags from word 0 and a handler from word 1.
It is the same route that had already resolved three other codes.

> **Nothing compares these codes. They index.**

There is no comparison instruction to find, because the engine never asks "is this code
`0x7F43`". **It subtracts a base and multiplies by eight.** The value being hunted is
arithmetic, not a literal, so a literal search is **structurally blind** to it and returns zero
however many times it is run, on however many populations, at whatever alignment.

**Cost: four searches returned empty before the table was read**, and the codes stood
unidentified in the meantime, **blocking a tower and a boss scene from being authored at all.**
Not a wrong answer that had to be undone later, which is the cheap kind: a true answer that
stopped work.

**The reusable half is a test, not a lesson. When a search returns zero, ask how the code would
USE the value.**

- **A value that is COMPARED appears as an immediate.** Search is the right instrument.
- **A value that INDEXES never appears at all.** The thing to find is **the table's base and
  stride**, not the value.

**And this is Instrument QA's standing question with the answer already known.** Ask it here:
*what would this search report if the code were not handled at all?* **Zero.** And what does it
report when the code IS handled, by a table? **Zero.** An instrument that returns the same answer
whether or not the thing exists cannot distinguish the two cases, which is the definition of
**blind**, and a blind instrument is unsound however clean its output looks.

**Relation to rule 1's search corollary, so the two are not mistaken for duplicates.** That one
covers a value that exists but is SPLIT, a 32-bit reference a compiler must build from a
`lui`/`addiu` pair, so the assembled word is never in the image. This one covers a value that is
never built at all. **Split, and never constructed, are different failures with the same
symptom**, and the same remedy: stop widening the search and go read what consumes the value.

## 31. A self-flagged limit is worth acting on before it is worth arguing with

**The family in 23 has a member that points the other way, and this is it.** 28, 29 and 30 are
honest reports read wrongly **by a reader**. This is an honest report whose **own author named
its weakness**, and the weakness turned out to be the entire finding.

A census reported one line over its window. Attached to it, unprompted, was the limit: **the
census had run against the authored SOURCE rather than a decode off a disc, and it said so, and
it said to re-run it off the disc before anyone acted on it.**

Step one of the follow-up was exactly that re-run. **The proposed fix was already shipped on all
seven English discs. The defect did not exist.** The string had read correctly on every disc
including the oldest on disk, and the phrase the finding was built on **appears in no source in
the tree**, so it was never even the authored text. The census was measuring something that has
never been on a disc.

> **Step one of the brief inverted the brief, and the flag was the entire result.**

**The cost is unusually clean in both directions, which is why this entry can state it
symmetrically. Acting on the flag cost one re-run. Not acting on it would have shipped an edit
to a string that did not need one**, into a scene that was already correct, on the strength of a
number that was real and irrelevant.

**Second instance, same author, same session.** A substitution width was unmeasured and it
declined to guess, leaving the peer's figure in place and flagging it. The flag kept the number
honest, and **it did not keep the line safe**, because a line authored to a width nobody has
measured is at risk whichever number is written down. The better lesson is the one that author
drew itself: **an unmeasured width is a reason to give the line MARGIN, not merely a reason to
annotate it.**

So, two halves, and the second is the one that is easy to skip:

- **When a result carries a limit its own author attached, spend the cheap check FIRST.** Before
  arguing with the finding, before scoping the fix, before briefing anyone. The author has
  already told you where it is weakest, and that is free information nobody else can produce.
- **A flag is not a remedy.** Annotating an unmeasured quantity records the risk; it does not
  reduce it. Where the flagged quantity feeds a budget, take margin against it.

**The reason this is worth an entry at all is that the incentive runs the wrong way.** A
self-flagged limit reads as diligence and invites a nod rather than a test, and it arrives
attached to a finding that is usually otherwise sound, which makes the flag the easiest part of
the report to skim past. **It is the highest-value sentence in the report precisely because its
author was the only person positioned to write it.**

## 32. When two counts disagree, check what each was ASKED before checking either

**Two instances, and a third that looks identical and is not. The third is in this entry on
purpose**, because a clean set of three would make this rule look better sourced than it is, and
because telling the two apart is most of the value.

The reflex when two instruments return different counts is to go and find the bug in one of them.
**That reflex spends a session and finds nothing, because in both real instances here BOTH
INSTRUMENTS WERE CORRECT.** They had been asked different questions.

**Instance 1: 9 against 27.** Same question, smaller population. Nine was the part that had been
looked at; eighteen more had not. Neither number was wrong about what it covered.

**Instance 2: 26 against 29.** The brief that produced the 26 asked for a **TAG-LINE** census by
its own wording, so three name codes sitting on BODY lines were outside its question **by
construction**. The re-run swept every subset of the name codes against three cap policies and
found **no policy that lands on exactly 26**, which is the tell: when no configuration of the
second instrument reproduces the first number, the difference is not a threshold, it is the
question. The 29 contained all 26 by name with none missing.

**And the near-miss, instance 3, which is a DIFFERENT FAILURE.** Four of five numbers in a brief
moved when someone finally measured them. That is not two instruments disagreeing: **the brief's
numbers had never been measured by anything.** They appear in no report; a search for them
returns only the brief's own sentence. Someone labeled an unsourced sentence MEASURED and handed
it on as a given.

**The separating test is the same first move in both cases, which is why one rule covers them:**

- In a **SCOPE** disagreement, **both numbers are real and answer different questions.** Find
  the two questions and the disagreement dissolves.
- In a **PROVENANCE** failure, **one number was never an answer to anything.** There is no
  second question to find.

**So: ask what each was asked. If one of them was not asked anything, that is the finding**, and
it is a bigger one than the count.

**The practical corollary, and it is what actually shipped in instance 2: when the counts are
NESTED, fix the superset and do not adjudicate.** The larger set contained the smaller entirely,
so acting on it could not leave anything in the smaller set unfixed. Declaring one instrument
wrong was unnecessary, would have cost a phase, and would have been false. **An agent that
notices two counts are nested does not need anyone to rule between them.**

Related to rule 10, decompose a moving number until the arithmetic closes, and distinct from it
in the first move: rule 10 assumes one derivation is faulty and takes it apart. **This one says
check the QUESTIONS first, because when the questions differ there is no faulty derivation to
find and taking either one apart is wasted work.**

## 33. State a negative as a positive measurement over a named population

**The converse of rule 1, and it is not the same rule.** Rule 1 is about whether an instrument
COULD have found the thing. This is about the FORM the answer takes once it has run, and the two
are independent: an instrument can be sound and its result still be stated in a way nobody can
check.

> **"I searched and found nothing" is unfalsifiable. "Across 306 distinct loadable images, not
> one instruction forms the address of a specific entry" is a number someone else can reproduce
> and disagree with.**

That sentence settled whether a sector table has a second consumer. It does not claim
thoroughness, it claims a **shape does not occur**, over a population it names and counts.
**Completeness answered without appealing to effort.**

**The form has three parts, and dropping any one returns it to an anecdote:**

1. **The population, enumerated and counted.** Not "the code", but 306 images. A reader can
   dispute the population, which is the point.
2. **The shape, stated positively enough to be searched for by someone else.** Not "references to
   this", but "an instruction that forms the address of a specific entry".
3. **The count, which is allowed to be zero.** Zero over a named denominator is a measurement.
   Zero over an unnamed one is a mood.

**Where this project asked it badly, and both are already in this file under a different
heading.** Rule 1's search corollary and rule 30 each record a search that returned nothing, and
in both the response was to widen the search rather than to change its form:

- A reference was hunted across more populations, more sub-block types and every byte alignment.
  **Four phases, the count rising, the answer staying wrong.** What ended it was a positive
  structural statement: **a compiler cannot emit a 32-bit immediate in one instruction**, so the
  assembled word is not in the image at all.
- Twenty-two control codes were hunted one code at a time. **Four searches came back empty.**
  What ended it was again positive and structural: **nothing compares these codes, they index.**

**Those two entries record how to DIAGNOSE a failed search. This one records what the answer
should look like when you have one**, and in both cases the answer that finally worked had this
shape rather than a bigger search behind it.

**And the rule in use, refusing rather than asserting.** A reference tool's own docstring holds
that a string with no entry is **UNRESOLVED, meaning no referrer has been FOUND, not that none
exists.** When an exact fix depended on one such string being genuinely unreferenced, the work
stopped there rather than spending the absence. **A negative you cannot state in this form is a
negative you may not lean on.**

**One thing this rule does NOT do, recorded because the counterexample is in this project's own
history.** A bestiary was excluded three ways, with denominators on every leg (all 5,821
decompressed sub-blocks, a structural test over all 23,828) **and a control that proved the search
worked.** It was still wrong: the table was found later, in plain sight, because **7 of the 12
probe names were not monsters in this game.** The form was right and the targets were not.
**Rule 33 makes a negative checkable. It does not make it true, and it never replaces rule 1.**

## 34. A holdout error is an ESTIMATE of error, not a BOUND on it

**Related to 8 and 15 and different from both, and the difference decides the remedy.** Rule 8 is
a model fitted to one case that fails elsewhere. Rule 15 is a threshold calibrated on one
population and carried to another. **Here the model was right, the validation was real, and the
number that failed to travel was the ERROR BAR ITSELF.**

This instrument did everything the file already asks for. It ran a **proper holdout**: the same
procedure applied to five blocks whose truth was already known, **with the error printed before
the projection was used.** Worst holdout error **8.43 percent**. That is rule 1 satisfied, not
violated.

Then the real text was authored and measured. **The projection had named two blocks as growing
and MISSED TWO MORE**, and the worst real error was **8.66 percent against the holdout's 8.43.**

> **The holdout slightly UNDERSTATED the true worst case rather than bounding it.**

**And rule 15's remedy is not available here, which is why this is its own entry.** "Calibrate on
the population you are testing" cannot be done: not knowing that population's truth is the entire
reason a projection exists. The remedy has to be a property of the SAMPLE instead.

**The cause was measurable and the tell was available beforehand.** The projector sampled at
**1.5876** English characters per Japanese character; the authored text came out at **1.7163**. It
under-predicted the largest blocks, by **238 bytes** on one and **183** on another, **and both
missed growers sit in that tail.** The holdout never reached the part of the range where the
estimate was hardest.

**So the test, and it costs one comparison:**

> **Before quoting a holdout error as a bound, ask whether the holdout SPANS THE POPULATION'S
> RANGE on the parameter that drives the estimate.** If the sample's own driving parameter differs
> from the population's, the error figure describes the easy part of the range and the misses will
> be in the tail.

**AND THE HARM IS ASYMMETRIC, WHICH THIS ENTRY MUST NOT FLATTEN.** The projection **succeeded at
the decision it was run for**: nothing needed relocation either way, and the two missed growers
changed no course of action. **It failed only at the confidence it expressed.**

**"The projection was wrong" would be a worse rule than the true one, which is that THE
PROJECTION WAS RIGHT AND ITS ERROR BAR WAS NOT.** Read the first way, this discourages projecting
at all, and projecting before authoring 316 strings was the correct call and remains so. Read the
second way, it changes one sentence in the report: quote a holdout error as **what the procedure
scored on the cases it was checked against**, and say which part of the range those cases covered.

**A number that is honest about its own derivation can still be quoted as something it is not.**
The failure was in the word "worst", not in the measurement behind it.

## 35. A limit in the wrong UNIT is not merely wrong, it is blind in both directions

**Two instances. The second is the shipped game measured in the RIGHT unit, and it resolves a
contradiction the first one parked in the record as though it were a conclusion.**

**Rule 29 is the near neighbor and this is a different failure, decided by a test rule 29 itself
supplies.** Rule 29 is a limit **narrower than the real one in the SAME unit**: everything
authored under it fits, the error is monotone and safe, and its remedy is to check the shipped
original against the limit.

**This is a limit in a unit the engine never accumulates**, and that changes both the consequence
and the remedy.

A text budget was carried as a **character count** for the life of this project. **The engine
sums PROPORTIONAL GLYPH WIDTHS**, 3 to 13 units across 521 font entries, against a box measured
at **224 units**.

> **A character count is not the quantity the engine adds up.**

**The consequence is the entry.** A wrong-unit cap is **simultaneously too tight and too loose**:

- **Too tight for narrow text.** English averages **8.01 units** per glyph, and the widest of 348
  authored lines runs 20 characters for **176 units, 79 percent of the box.** Every line squeezed
  to the character cap gave up room that was there.
- **Too loose for wide text, and this is the half no character gate can see.** **21 capitals plus
  the drawn prefix is 232 units, 104 percent. It clips.**

**A rule 29 error can never produce a clip. A wrong-unit error can, and this one does.**

**AND RULE 29's REMEDY WOULD NOT HAVE FOUND IT, which is the decisive part.** Run it here and it
returns nothing: charging the prefix against the shipped Japanese costs **22 extra violations in
3,581 lines, 0.6 percent**, which falsifies nothing in either direction, **because the shipped
language never runs tight enough against the box for the discrepancy to show.** Checking the
original against a limit tests whether the limit is too tight. **It cannot tell you the limit is
denominated in the wrong thing**, because both sides of that comparison are in the wrong unit.

**So the test is not "is the limit right" but "is the limit in the quantity the machine
accumulates".** Find the accumulator. Read what the code adds to it and what it compares it
against, and denominate the budget in that. Here the instruction long read as the width test turned
out to be **vertical**, a Y accumulator against box HEIGHT, and **every access to the box width in
the formatter was read: it is used ONCE, for a centering offset.** There is no horizontal width
check at all; the engine draws past the edge. **And that centering offset is itself never applied
in any of the 55 observed states**, which is a second layer of the same lesson: reading what the
code CAN do is not reading what it DOES. Geometry in `FORMAT.md` 15c-i.

**A corollary that is the same defect at one remove: NEVER MULTIPLY A MEAN.** Once a budget is in
units, a mean width times a character count is not a measurement of anything, and it fails in both
directions on the same page. The mean is 8.01 for English and 11.6 for Japanese, and **21 times
11.6 is 243.6 against a 224-unit box**, so the old character cap and the measured mean cannot both
describe the same lines. **A gate must SUM THE REAL WIDTHS, glyph by glyph.** A gate that
multiplies is a character gate wearing units.

### Second instance, 2026-08-26: the shipped game measured in the right unit

**The corollary above parked an unresolved contradiction and read as though it were a conclusion.**
"21 times 11.6 is 243.6 against a 224-unit box, so the old character cap and the measured mean
cannot both describe the same lines" is correct arithmetic and was the right reason to stop
multiplying. **It also left a live inconsistency sitting in the record.** It is now resolved, and
resolved is not retracted: nothing above is withdrawn.

MEASURED: **long shipped lines use NARROWER glyphs.** A 21-glyph line runs **10.6** units per glyph
rather than 11.6 and fits, at 223. **The game never writes a 22-glyph line at all**, which is what
the old character cap was really recording. **243.6 never described a real line.**

> **A mean is not constant along the axis you are multiplying it by. That is WHY the multiplication
> fails. The entry above only knew THAT it failed.**

**And the sharper half. Over 3,969 shipped lines, exactly one exceeds 224 units**: `0x048F[70]`,
box 0, line 0, at **229 units, over by 5**, next widest 223. **It is the 20-glyph line, not the 21.
Length did not predict which line it would be**, which is the same defect one level down: character
count fails as a proxy for width even when you are only using it to guess where to look.

**RULE 29's REMEDY IS PARTLY REHABILITATED HERE, and the paragraph above overstated its
uselessness.** Above, running the shipped original against the limit "returns nothing". That is
right in the CHARACTER unit and wrong as a general statement. **Run the shipped original against
the limit once the UNIT is right and it returns exactly one line.** The order is the reusable part:
**fix the unit first, then run rule 29's check.** In the wrong unit the check is uninformative; in
the right one it produced the only shipped-game evidence this model has.

**WHAT THIS INSTANCE MUST NOT BE FLATTENED INTO.** It is one line in 3,969, and **which window that
string draws in was not measured.** The margin of 16 is measured on two window types only, and a
240 px window with a margin under 11 would fit 229. **The honest form is "the shipped game VERY
LIKELY draws past its own box edge, on one line in 3,969, by 5 units", not "the shipped game
clips."** The geometry, the caveat and the test that would settle it live in `FORMAT.md` 15c-i,
which is the authoritative location; the figures are quoted here only far enough to make the method
point legible.

**And the standing limit is untouched: the unit model PREDICTS and has not been booted.** A
shipped-game measurement narrows a model. It does not boot one.

## 36. Before deriving a fact, check whether the project already holds it

**Two instances, both below, plus a near-miss of a different shape that supplies the third half of
the remedy.** Named by Dos on 2026-08-26, after the third time in one week that the answer was
already in the tree.

**The cost is not a wrong answer, which is exactly why nothing else in this file catches it.** In
both instances the fact was **already correct, already committed, and already being relied on by
working code.** Every gate passed. Nothing was retracted for being false. **What was spent was a
derivation that did not need to happen**, and in the first instance a brief built on the wrong
population and **90 strings queued for authoring that did not need authoring.**

### First instance: a discriminator that fourteen files were already using

A census could not tell a description from a runtime substitution, because one control code carries
both roles, and it reported **90 defects**. **Eighty-nine were not defects.** The retraction is rule
23's second instance.

**The test that separates the two roles is one line**, in the Chapter 1 gate's leg 1:

```python
if not t or t.endswith("{7F11}"):
    continue
```

**It is not in one file. MEASURED: 15 files across 6 directories** of working scripts spanning
Phases 108 to 114, earliest timestamped 2026-08-25, **14 of them using it as code.** The gate whose
leg 1 depends on it had been passing with it for phases.

**The fifteenth is the Builder's own note**, inside the docstring of the retracted census itself,
quoted verbatim: **"gate.py's leg 1 skips the class with `t.endswith("{7F11}")` and has done for
phases. I did not use it."**

**The same episode re-derived a SECOND thing the project already held.** The corrected 7-cell
description budget was measured afresh out of the text, 248 shipped segments with the longest at 7,
while `BOARD.md` had carried "the description budget is 7 characters per line" since Phase 87,
reached there independently from window geometry. **Two facts, one episode.** It is not a separate
instance and is not counted as one.

### Second instance: a sharp form that was already a gate's expected value

The record carried a loose statement, *zero overruns beyond +3 across 23,828 sub-blocks*. The sharp
form is **`{0: 3089, 3: 2732}` over 5,821 LZS sub-blocks**, and the loose one was wrong twice over:
a denominator of 23,828 for a claim whose population is 5,821, and **"beyond +3" stated as a BOUND
where the measurement is an ENUMERATION** of two values and nothing else.

**The sharp form was already `verify.py` gate 20's literal expected value**, line 367:

```python
two_valued = sorted(deltas.items()) == [(0, 3089), (3, 2732)]
```

**And it was already written out in prose in `FORMAT.md`'s compression section**, attributed to gate
20. **Two locations, both committed, both correct.** When a Builder finally looked, the outcome was
**CONFIRMED, not corrected.**

### The near-miss, and it carries a THIRD remedy neither half covers

**A third instance was proposed, did not survive checking, and the way it failed is worth more than
the instance would have been.** A standing rule cited one numbered line of psx-spx's kernel BIOS
documentation as
having documented a BIOS routine "the whole time", at a cost of a build and 36 font codes.

**The cost half is real** and has phase-report citations behind it. **The "already documented" half
is not.** The project's own disassembly puts the call on BIOS table **B**, function **0x19**. The
cited document says **`B(19h)` is `HookEntryInt`**, and puts the named routine on the **A** table at
`A(39h)`, which is what line 235 actually holds. **The document was consulted. The citation does not
resolve to the claim.**

> **Check that the citation RESOLVES, not merely that one exists.**

**The conclusion built on it is untouched**, because the region being owned rather than free was
established on hardware and not from the routine's name. **A broken citation does not cost you the
conclusion. It costs every future reader who follows the pointer and finds something else**, and
each of them pays it again. Raised in Phase 114 and left OPEN.

### Why this is an entry and not a note

**The nearest thing this file had was not in this file.** The standing instruction to read
psx-spx before deriving console behavior lives in the team document. **The codex said
nothing at all about looking before deriving.**

**And what the codex DID say points the other way.** Rule 6 carries "prior documentation is a source
of hypotheses, not facts", which is true and was paid for. **Stated alone, it reads as license.**
This file warned against trusting inherited documentation and said nothing about failing to look,
and the two have to stand together or the first one excuses the second.

- **Rule 6 governs what you may CONCLUDE from something you found.** A found fact is a hypothesis
  until it is measured.
- **This rule governs whether you LOOKED AT ALL.** Not looking is not skepticism.

**The three halves of looking need three different remedies, which is why folding this into the
outward-facing instruction would have lost the useful part:**

| | what you are looking for | the remedy |
| --- | --- | --- |
| **outward** | console behavior, in a document you KNOW exists | go read it |
| **inward** | a fact you do NOT know the tree holds | **grep before you derive** |
| **either** | a claim that already cites a source | **follow the citation and check it lands** |

**The inward half is the hard one, because it has no natural trigger.** You cannot go and read a
document you do not know exists. **What you can do is grep**, and both instances say what to grep
for: **the discriminator you are about to write, and the number you are about to derive.** Each was
one grep. Each would have returned a hit.

**The tell that you are in this rule's territory: you are about to measure something the project
must already have needed in order to get this far.** A gate that passes already contains the test it
passes on. A number quoted in a phase report already came from somewhere.

## 37. Do not re-encode what has not changed

**Recorded Phase 118, and it is the only entry here that REMOVES a class rather than detecting
one.** Every other rule in this file makes a failure visible. This one arranges for the failure not
to be available.

> **A block that is not re-encoded does not move its string offsets. Every reference into it stays
> valid BY CONSTRUCTION: word form, split immediate, or a form nobody has found yet.**

**That last clause is the whole entry.** Rule 1's referrer corollaries and rule 30 are DETECTION,
and both of them depend on knowing every reference form there is. **This one requires knowing
none of them.** It is the only remedy in this file that is safe against blind spots that have not
been measured, which is exactly the class that has cost the most here.

**Four rules, and they are not guidance:**

1. **Default: never re-encode a block whose input hash is unchanged.** Copy the previous encode.
2. **The hash covers the strings, the dictionary, the encoder version, the per-block parameters
   AND the global build configuration.** Scoped to the strings alone it **silently serves a stale
   encode after an encoder change**, which is a worse failure than the one it was added to prevent,
   because it looks like a cache hit rather than like a defect.
3. **When such a block's text genuinely must change, PIN its string bit-offsets to their pristine
   values. Pad, do not repack.** Paying bytes is cheaper than moving an offset a reference form you
   cannot see is holding.
4. **Companion, two legs, and BOTH must fire.** Change one string: **only that block re-encodes.**
   Change only the encoder version and nothing else: **every block re-encodes.** **If the second leg
   does not fire, the hash is under-scoped**, and it will keep passing the first leg while doing so.
   Rule 6 in `docs/DRIFT.md`, and rule 3 above.

**Its relation to rule 20, because read carelessly they point opposite ways.** Rule 20 says data the
build carries through unchanged is verified by nothing. This says carry it through unchanged. **They
compose, and rule 20 supplies the missing half: gate the carried data against the PRISTINE
artifact.** Skipping the re-encode is what keeps the references valid; decoding the carried bytes
and comparing them to pristine is what keeps the skip honest. **A skip with no such gate is a cache
nobody checks, and rule 20 is the entry about exactly that.**

**Cost: the whole class, on every build, until it exists.** Stated that way on purpose. This entry
has no single expensive instance behind it because it was specified after the instance that
motivated it was already being fixed a different way, and **an entry whose cost is prospective
should say so rather than borrow the cost of the defect it would have prevented.**

## 38. A status field is a CLAIM, and it needs a reference like any other

**`SENT` must be derived from something other than the field that says `SENT`.**

This is the FPS reader one level up. There, an instrument that could not see the screen and a run
with nothing to see produced the same output. Here, **a job that was dispatched and a job whose
status field merely says it was dispatched produce the same output**, and the second one is not
doing any work.

**It has now failed in both directions in the same project, which is what makes it a rule rather
than a slip:**

| | what the record said | what was true |
| --- | --- | --- |
| **four times** | nothing | **dispatched, and never written down** |
| **once** | **`SENT`** | **never dispatched** |
| **twice more** | described in conversation as "running in parallel, unchanged" | **one existed only as a specification inside a brief marked QUEUED, NOT SENT; the other did not exist anywhere in the tree** |

**The second row is the dangerous one**, because the first row's failure is discovered the moment
someone looks for the record, and the second row's failure is discovered only when someone waits
for a result that was never coming. **The work was planned around three jobs, and one of the three
was real.**

### The remedy is mechanical and it is one line

> **WRITE THE STATUS FIELD WHEN THE SEND RETURNS. Never before, and never from intent.**

**Nothing else may write it.** Not the author finishing the brief, not a summary, not a plan that
says what will happen next. **A brief is written before it is sent - that discipline is separate and
still correct - but the STATUS is a record of an event and may only be written by the event.**

### The general form, and it is the reusable half

**Any field that records whether something happened is a measurement of the world, and inherits
every rule in this file.** It needs a reference outside itself, and **the reference cannot be the
document it lives in.** A record that says a thing is true, kept by the person who wants it to be
true, checked against nothing, is the anchor problem in prose: **a check whose reference is derived
from its subject cannot fail.**

**A tell that costs nothing to look for:** if you are about to report that several jobs are running,
**grep the tree for each one by name first.** Two of the three that were reported as running on
2026-08-27 left no trace at all - one word appeared **nowhere** in the entire documentation tree.
**That search takes seconds and it is the reference the status field did not have.**

## 39. Independent results require independent INPUTS, not independent code paths

**Two scans reported zero referrers for the same block. That was recorded as corroboration. It was
one measurement printed twice.**

The word scan and the split-immediate scan are **different code, different authors' intent,
different failure modes**, and everything about them looks independent from outside. **They resolve
against the SAME `index()`.** That index was scoped to three carrier types and the block in question
lives in a fourth, so **`res()` returned `None` unconditionally in both.** Neither scan ever searched
for it.

> **Agreement between two tools is evidence only to the extent their INPUTS differ. Shared state
> upstream of both makes them one instrument wearing two names.**

**The tell is cheap and nobody looked for it**: trace each result back to the data it was computed
from, and **stop when the two traces meet.** Everything above the meeting point is common, not
corroborating. Here the traces met immediately, at the first shared call.

**This is the general form of the anchor problem.** There, a check's reference derived from its
subject. Here, **two checks' references derive from each other's**, which is harder to see because
neither check is individually circular.

**COST: 26 authored strings marked CANNOT BE SHIPPED on a doubled zero**, plus a recorded belief
that the population had been searched twice. **The corrected statement is that it had not been
searched at all**, and the real search, once run against the decoded block with positive controls,
took one leg.

**The corollary for reporting:** when you write "confirmed by two independent X", **name what makes
them independent.** If you cannot name it in one clause, they are not.

## 40. Every classifier needs a residual bin, and a residual of ZERO is a claim needing its own evidence

**A classifier that sorts everything into the categories it knows about has not found that
everything fits. It has found that it has no way to say otherwise.**

**Three instances in one night, in three unrelated instruments:**

| instrument | the missing bin | what it produced instead |
| --- | --- | --- |
| a screenshot reader | **unreadable** | **1,170 frames it could not read, reported as the clean value** |
| a reference index | **carrier types not enumerated** | a block that was never searched, reported as **zero referrers** |
| a block census | **types that could not be classified** | a denominator derived from **four hand-picked types**, quoted as a total |

**All three are the same shape**: a two-valued output where the world has three states, so the third
state is silently distributed into the other two - **and always into the reassuring one.**

> **The remedy is structural, not diligence. The third bucket must EXIST, must be a NUMBER, and must
> SURVIVE TO THE SUMMARY.** A count that is folded into "clean" before anyone reads it may as well
> never have been taken.

**And the follow-through that is easy to skip: a residual of zero is itself a claim.** "Nothing was
unclassifiable" and "I had no category for unclassifiable" are the same output, **which is this
whole rule applied to its own remedy.** So say HOW zero was established. Sampling the residual by
hand is enough. Asserting it is not.

**A residual bin is also where the next finding usually is.** The eight blocks invisible to the
reference index were not a defect to be patched and forgotten - **they were a population**, and the
same eight had already been reached by a completely different route months earlier. **The bin nobody
built was holding the answer.**

### SCOPE ERRORS AND SHAPE ERRORS ARE NOT THE SAME DEFECT, and only one of them is catchable by asking

**The corrected version of the census above was still wrong, and wrong in a way the correction could
not reach.** Told that its denominator came from a hand-picked type list, it re-derived the total
across **all 37 types present**, all bytes outside every parsed block, and **every file in the
container.** Thorough, and it still missed two, **because the two blocks it missed live in no
sub-block of any type.** They were not outside the scope. **They were outside the SHAPE.**

| defect | the question that catches it | why |
| --- | --- | --- |
| **scope** | "did you look everywhere?" | the honest answer is **no** |
| **shape** | "did you look everywhere?" | the honest answer is **YES**, and it is wrong |

> **A scope error is a gap in a survey. A shape error is a survey of the wrong kind of thing.**
> Asking for more coverage fixes the first and **confirms** the second.

**The question that does reach it is not about coverage at all:** *what would an instance look like
that my enumeration has no ROW for?* Here the enumerator walked sub-blocks, so **anything not in a
sub-block was uncountable rather than uncounted** - a distinction that never appears in the output.

**The tell, when you have it, is two routes disagreeing on the total rather than on the contents.**
When one route finds 5 the other cannot see and the other finds 2 the first cannot see, **the
directions of the two misses name the two shapes.** One route missing things in one direction only
is a scope gap; **misses in both directions mean the routes are enumerating different universes.**

## 41. A property that holds THROUGHOUT a process cannot certify the process is COMPLETE

**A file being copied sector by sector is at an exact sector multiple at EVERY INSTANT OF ITS
LIFE.** So "its size is an exact multiple of the sector size" is true of a transfer that finished,
a transfer half done, and a transfer that failed on its first block. **It cannot distinguish them,
and it was used to report one as the other.**

**This is the anchor problem in the time dimension.** There, a check's reference derived from its
subject. Here, **the check's evidence is an invariant of the process it claims to be measuring the
end of.** An invariant is precisely the thing that carries no information about progress.

> **Before accepting any completeness check, ask: WHEN DID THIS BECOME TRUE? If the answer is "at
> the start", or "always", it certifies nothing.**

**A second, weaker check was stacked on it and inherited the same defect:** the size was observed
**stable across an interval**, which felt independent and is not - a transfer stalls, throttles, or
is between writes, and stability over one sample says nothing. **Two bad checks agreeing is one bad
check, which is the shape of entry 39.**

**The sound checks were available and cheaper.** The image had **no ISO9660 primary volume
descriptor at all** - sectors 16 to 31 entirely zero - and **1,952 of 2,000 sampled sectors were
zero.** It **grew by 46 MB while being read.** Any of the three would have settled it. **The right
check asks for something that is FALSE UNTIL THE END and true after: a terminating structure, a
declared total compared against the actual, or a hash against a known-good value.**

**COST here was small, one deferred question. The rule is recorded because the shape is not
specific to files:** a build "looks complete" because every intermediate is well-formed; a
migration "looks done" because every row processed is valid; a scan "looks exhaustive" because
every result it returned was correct. **In all of them the property being checked was never absent
at any point, so its presence at the end means nothing.**

**And note where this one was caught: in the checker's own reasoning, unprompted, not by the
instrument and not by review.** That is the cheapest place, and it is available only if you are in
the habit of asking what a passing check would have looked like if the thing had failed.

## 42. A sub-agent must not ratify a JUDGMENT call, and must absolutely refute a FACTUAL one

**These pull in opposite directions and both are required. Getting only one produces either a
rubber stamp or a runaway.**

**The judgment half:** a delegate may author, measure, gate and propose. **It may not decide a
naming call, an editorial convention, or anything whose answer is a preference rather than a
measurement.** The trap is that **a proposal and a ratification look identical once the text is in
the file**, and the file is what the next delegate reads. So the open ones live in one named list,
and **being written into an authored artifact is not evidence the call was made.**

**The factual half, and it is the one that gets trained out:** when a delegate holds a measurement
that **refutes the instruction it was given, the measurement wins and it should say so.**

**The worked case.** A brief said, in capitals: *"THE 2014 BUILD IS A DIFFERENT PROJECT FROM THE v1.2
PATCHES. Do not conflate them."* Reasonable, defensible, and **wrong.** The delegate measured
instead of complying: **a 96-byte glyph width table byte-identical across the two, 0 of 96 differing,
and 394 of 394 injected bytes matching.** Same project.

> **That refutation was load-bearing, not pedantic. It licensed reading code out of the COMPLETE
> older build and applying it to the patched one.** An agent that had obeyed would have been slower
> and no safer, and would have reported a correct result by a worse route while leaving the false
> instruction standing in the record for the next person.

**The distinguishing question is not "how confident am I", it is "what KIND of claim is this?"**

| the instruction asserts | the delegate should |
| --- | --- |
| **a fact about the artifact** | **test it, and refute it if the measurement says so** |
| **a preference, a name, a convention** | **follow it, propose alternatives, never overrule** |

**A brief's factual premises are not orders. They are the author's current best reading, and the
delegate is standing closer to the data.**
## 43. A note recorded as an OBSERVATION does not block anything

**The gap was written down, in the right file, by someone who understood it - and it did not fire
for 26 phases.**

A corpus file carried this line in its own footer:

```
THE 152 TYPE 44 SUB-BLOCKS - no tool covers them at all.
```

**That is the exact reason the project could not see a referenced text block, stated plainly, in the
document about that block.** Everyone who worked on it read past it. **26 phases later the block
turned out to have 26 referrers sitting in the shipped archive the whole time**, and the reference
was **found every single time and discarded at the resolve step.**

> **The note was correct, well-placed, and completely inert. It described a condition instead of
> asserting one.**

### The distinction that matters

| form | what it does when someone runs the build |
| --- | --- |
| **an observation** | **nothing** |
| **a gate** | **fails** |
| **a residual bin** | **prints a number that has to be explained** |
| **an `UNCONFIRMED` in the output** | **contaminates every claim downstream of it** |

**Prose in a document is the weakest of the four and it is the one everybody reaches for**, because
it is the only one that costs nothing to write. **That is exactly why it does not work: it also
costs nothing to skip.**

### The rule

> **When you record a limitation, ALSO record what it is allowed to break.** If a known gap cannot
> make anything fail, print a number, or taint a result, **it is a diary entry, not a control.**

**The cheapest promotion, and it is usually available:** turn the sentence into **a count the tool
emits every run.** "No tool covers type 44" becomes **"152 sub-blocks not scanned"** on every
report. **A number that appears beside a clean result is read; a paragraph in a file three
directories away is not.**

**And the corollary for tooling, which this project has now paid for twice:** a codex that is
**readable by people** and **not greppable from the tools** will keep producing this failure. The
rule lived where it applied and still did not propagate, **so the fix is not "write it down more
clearly" - it is to make the machine carry it.**

### THE REMEDY THAT WAS ACTUALLY ADOPTED: ATTACH THE GAP TO THE JOB

**Writing the limitation better was never going to work, because it was already written well.** What
was missing is that **nothing consumed it.**

> **Every known blind spot is ATTACHED to the job it invalidates, and the job cannot report clean
> without naming it.**

**A register of blind spots, each with what it invalidates. Every brief carries the rows that touch
it. A report may not say `clean`, `zero`, `none found` or `PASS` without naming its attached rows
and saying, for each, WHAT ITS RESULT WOULD LOOK LIKE IF THE BLIND SPOT WERE THE CAUSE.**

**The test is one sentence: COULD THIS JOB RETURN EXACTLY THIS OUTPUT WITH THE BLIND SPOT AS THE
WHOLE EXPLANATION? If yes, the output is UNCONFIRMED, not clean.**

**This is cheaper than a gate and works where a gate cannot** - it can be written for a limitation
**nobody yet knows how to test**, which is the exact case where the observation gets written instead
and then ignored. **And closing a row takes a measurement rather than an argument; rows are edited
in place and never deleted, because a closed row is the record of what a clean result used to look
like when it meant nothing.**

**Cost: 26 phases, 26 authored strings marked unshippable, a published claim of orphanhood, and a
capture session commissioned to answer a question the archive had already answered.**
---

---

## 44. A loop written against a FIXED-WIDTH source hides an off-by-one until VARIABLE-WIDTH input arrives

**Cell math that is correct for every input the author ever had is not correct code. It is code whose
defect has no reachable witness.** Change the input distribution and the defect activates without
anything having been edited.

**The instance cost six weeks.** A party name is padded out to a four-character field:

```
addiu t0,zero,4      ; the field width
subu  s0,t0,v0       ; s0 = 4 - n
addiu s0,s0,-1       ; s0 = 3 - n
beq   s0,-1,exit     ; <- EQUALITY against the boundary, not a SIGN test
```

**Every Japanese party name in the shipped game is 4 fullwidth characters or fewer, so `3 - n` lands
EXACTLY on -1 every time and the guard always fires.** At n = 5 the counter starts **below** the
value it tests for, the guard misses, and it counts down through zero and wraps: **4,294,967,294
iterations**, each emitting a sprite packet through an allocator with no bound. **Enix's defect,
latent since 1990, activated by English names. Nothing we wrote was wrong.**

**This is the same class as wide-character handling in terminal libraries** - column arithmetic that
holds for uniform-width input and breaks when width varies. **It is not a domain-specific romhacking
problem and the general form is worth carrying to any codebase.**

### WHERE TO LOOK FOR THE OTHERS

**Three signatures, and they are greppable:**

1. **Any loop computing a COUNT from a FIELD WIDTH.** `width - length` is the shape. Ask what
   guarantees `length <= width`, and whether that guarantee is a check or an accident of the data.
2. **Any buffer sized to a CHARACTER COUNT rather than to BYTES.** In a mixed-width encoding those
   are different numbers, and the one that matters is the one the writer uses.
3. **Any comparison testing EQUALITY AGAINST A BOUNDARY instead of sign or bound.** `== -1`, `== 0`,
   `== max` where `< 0`, `<= 0`, `>= max` was meant. **Equality is only safe when the step size
   divides the distance exactly, which is exactly the assumption a wider input breaks.**

### THE INSTRUMENT POINT

**A fixed-width assumption cannot be found by testing with the data the author had.** The shipped
game exercises this loop on every status screen and never fails. **The test that finds it is a
LONGER STRING, and if the corpus cannot produce one, the test has to fabricate one.** Property tests
over the width parameter, not example tests over the shipped corpus.

**Corollary, and it is the cheap half:** when a defect activates on new input, **check whether the
original code was already wrong before assuming the new input introduced it.** Six weeks here were
spent looking for what our edits broke. **Nothing we edited was broken.** The question "is this
latent or introduced" is answerable early and cheaply by reading the guard, and it routes the entire
investigation.

**Cost: six weeks of hypotheses, four discs built to test wrong theories, a wrap mechanism
investigated at length that DOES NOT EXIST in this engine, and a name-length ceiling that shaped
editorial decisions across three phases before it turned out to be removable in one word.**

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

**37 cost-entered rules, plus the reframing section with 4 worked instances.** Instance counts,
taken by grepping every "instances" sentence in this file and attributing each to the `## <n>.`
heading above it: **rule 4 has five**, and **rules 5, 9, 23, 32, 35 and 36 have two each**.
Everything else has one. **RULE 1 IS UNCOUNTED**, and that is a state rather than an omission:
its own header carries the reason, dated 2026-08-27, and no figure for it may be quoted until
this file says what an instance is. **Rules 23 through 26 are one family**,
a measurement that is true and a conclusion that is not, and **27 through 31 are that family
aimed at five different honest reports**: a script's success line, a tool's own report about
itself, the observed range of a system's output, a search that returns zero, and a limit the
report's own author attached to it. **31 is the one that points the other way**, where the
honest report was read wrongly by nobody and the flag was the finding. **32 stands apart from
that family**: there the reports do not disagree with reality, they disagree with each other, and
both are right. **33 is the converse of rule 1**: rule 1 asks whether an instrument could have
found the thing, and 33 asks what form the answer takes once it has run. **34 sits beside 8 and
15**, the three ways a number measured on one population misleads about another, and it is the
one where the number that failed to travel was an error bar rather than a model or a threshold.
**35 is rule 29's near neighbor and a different failure**: 29 is a limit too narrow in the right
unit, which is monotone and safe, while 35 is a limit in a unit the machine never accumulates,
which is blind in both directions and can clip. **36 is the one rule here that is not about getting
a measurement wrong**: every other entry describes an answer that was wrong, misread, or wrongly
scoped, while 36 describes a correct answer arrived at twice. **Its near neighbor is rule 6's "prior
documentation is a source of hypotheses, not facts", and it points the opposite way**: 6 governs
what you may conclude from what you found, 36 governs whether you looked. **37 is the only entry
here that removes a class instead of detecting one**, and it is deliberately the last: every other
rule makes a failure visible, and 37 arranges for the failure not to be available. **It is also the
only entry whose cost is PROSPECTIVE**, which its body says in as many words rather than borrowing
the cost of the defect it would have prevented. The count above was taken by counting the `## <n>.` headings in this file, not by
adding one to the previous figure.

**CORRECTED IN PLACE, 2026-08-26, and it is this footer's own defect a third time.** The instance
line read "rule 5 has two, rule 9 has two. Everything else has one" while **rule 32's own body has
said "two instances" since it was written.** The list was maintained by adding the rule that had
just changed rather than by re-counting, so a rule that gained its second instance without the
footer being touched stayed invisible. **Rules 23 and 35 each gained a second instance on
2026-08-26**, and the list above was then taken by grepping every "instances" sentence in the file
and attributing each to the `## <n>.` heading above it, not by amending the previous list. Rule
count was 35 at that point, counted the same way.

**RE-COUNTED AGAIN when rule 36 was added later the same day**, by the same grep rather than by
adding 36 to the list it had just produced. **Rule count 36, from `grep -c "^## [0-9]\+\."`.**
Reframing's 4 worked instances were counted in the same pass and are unchanged. **The instance
list is regenerated, never appended to**; appending is precisely what hid rule 32 for as long as it
was hidden.

**Rule 1's seventeenth instance used to sit below this section**, stranded after "Maintenance"
and outside the rule it belongs to, where a heading-based count could not see it and returned
sixteen. It has been moved back inside rule 1. A count that disagrees with a header is a
question about where the text lives before it is a question about the header.

**RE-COUNTED AGAIN, 2026-08-27, when rule 37 was added and Phase 118's three durable findings were
recorded.** `grep -c "^## [0-9]\+\."` returns **37**. The instance list was regenerated by the same
grep, not amended, and it changed in one way that is not an addition: **rule 1's figure of eighteen
was WITHDRAWN rather than updated.**

**That withdrawal is the maintenance event worth reading, because it is this footer's own defect in
a fourth costume.** The three earlier corrections here all ended in a better number. **This one ends
in no number**, because a recount could not reproduce eighteen and could not defend a replacement:
**three of rule 1's corollaries each describe more than one episode**, so "counting the instances
written under each entry" has two readings that differ by two, and nothing in this file picks one.
**Choosing one silently and printing the result would have looked exactly like a correction while
being a fresh unsourced figure**, which is the shape of every stale count this footer has had to
retract. **A count you cannot derive twice the same way is not a count.** The definition is the fix
and it is not attempted here; see the note under rule 1's header.

**Two findings from Phase 118 were recorded WITHOUT a new heading, deliberately, and that is the
routing this footer should show rather than hide.** The split-immediate reference form was already
this file's own material, in rule 1's search corollary and cross-referenced from rules 30 and 33, so
Phase 118's far more expensive instance went in as a second instance of that corollary and not as
rule 38. The blind-census finding was already worked through in rule 30, so only its previously
unrecorded half went in, as a remedy under rule 1. **Only the third finding, which removes a class
rather than detecting one, had nothing in this file to attach to, and it is rule 37.** **The check
that produced that routing is one grep per candidate, and it is cheaper than the duplicate entry it
prevents.** Rule 36.

The previous version of this line read "18 cost-entered rules" and attributed the instance
counts to rules 3, 4 and 8. Both were stale: the rules had been renumbered and the footer had
not, and the count was **four short** of the 22 entries that stood before this section was
added. An earlier draft of this paragraph said five, which is the defect it is describing
wearing the correction's clothes. **Count the headings, do not subtract from memory.**

Linked from `FORMAT.md` and from the working notes. **One authoritative location per fact**: nothing
here is duplicated into those files, and format claims are not duplicated into this one.
