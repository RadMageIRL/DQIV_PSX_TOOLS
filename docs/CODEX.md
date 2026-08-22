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

**Eight instances. The most expensive rule here. The sixth cost fifteen phases, the seventh cost twenty-five, and the eighth cost a boot test.**

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

**Three instances.**

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
in another nearly cancelled. On a block nine times larger the saving grew fourfold and the growth
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

## 18. **[PSX]** Boot tests start from a cold emulator process

Not a reset, not a disc swap, not opening a file in a running window. **Starting a new game reloads
save data, not the executable.** Asking whether a save state was used got a truthful "no" that was
not the question, and the wrong question was treated as dispositive for two builds.

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
sectors. None asked **which channel the change travelled on** until the frame was changed to
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

**18 cost-entered rules, plus the reframing section with 4 worked instances.** Instance counts: rule 1 has eight, rule 3 has four, rule 4 has three, rule 8 has
two. Everything else has one.

Linked from `FORMAT.md` and from the working notes. **One authoritative location per fact**: nothing
here is duplicated into those files, and format claims are not duplicated into this one.
