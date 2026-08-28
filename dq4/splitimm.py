"""Split immediates: the references a 32-bit word scan cannot see.

A reference into a text block is the packed word `(text id << 20) | bit offset`.
`referrers.py` finds the ones the game STORES as that word. This module finds the
ones the game CONSTRUCTS, which never appear as that word anywhere in the image
and are invisible to any search for a literal.

Three forms, all measured on this disc:

  SPLIT   `lui rX,hi` then `ori rX,rX,lo`, or `lui rX,hi` then `addiu rX,rX,lo`.
          The composed value exists only in a register at runtime.
  ORPHAN  `ori rX,rX,lo` where no live `lui` supplies rX and the nearest prior
          write to rX was a LOAD. The high half arrives from memory, so only the
          low half is a rewritable string offset.

WHY THE addiu FORM IS NOT OPTIONAL, and it is a correctness point rather than a
coverage one. `addiu` SIGN EXTENDS its immediate. Composing an `addiu` pair with
the `ori` rule reads a value 0x10000 too low whenever bit 15 of the low half is
set, and WRITING an `ori` composition into an `addiu` pair stores a value 0x10000
too low. A recognizer that does not distinguish the two opcodes is not merely
blind to some sites, it is wrong about the ones it does find.

WHY THE CLOBBER MODEL IS NOT OPTIONAL. A recognizer that pairs the nearest `lui`
with the nearest matching low half, with no register liveness, invents pairs: it
will cross an intervening write to the register, and it will cross a jump. Fifteen
such invented pairs are the entire difference between this scanner and an earlier
one on the id it was scored against, and the disassembly shows the register being
overwritten between the two halves in every one of them. A WIDE WINDOW WITHOUT A
CLOBBER MODEL IS WORSE THAN A NARROW ONE: widening only buys more chances to be
wrong. Both were widened together here.

WHAT THIS TOOL CANNOT DO, stated in its own output rather than in a footnote,
because rule 1 of `docs/CODEX.md` says an instrument that cannot report its own
blind spots is not an instrument:

  * Non-adjacent halves further apart than `window` instructions are missed.
  * `$gp`-relative loads, where neither half names the address, are not a form
    this recognizes at all.
  * A `lui` whose register is written by an instruction this module's `writes()`
    model does not cover would be paired across that write.
  * A HIGH HALF IN A BRANCH DELAY SLOT, with the low half AT THE BRANCH TARGET,
    is not paired. MEASURED 2026-08-28 on an overlay image: three such sites on
    one block that the forms above find 26 on. A MIPS delay slot executes
    whether or not its branch is taken, so a `lui` written there is LIVE on the
    taken path, where the completing low half sits at the destination, and DEAD
    on the fall-through, where the next instruction overwrites the register. The
    linear scan below sees only the fall-through and is CORRECT to call that
    `lui` clobbered. This is not a defect in the clobber model; it is a
    control-flow form the model does not represent, and pairing it needs a
    branch-target pass this module does not have. The low half is then seen
    alone: when its register was last LOADED it surfaces as an ORPHAN, and
    otherwise it is not reported at all.

BECAUSE OF THAT LAST ONE, `hi_off is None` IS NOT A CURIOSITY A CALLER MAY SKIP.
It means "no high half is locatable at this site", which is the whole of what the
image supports, and it is the shape a reference nobody models arrives in. A
caller that drops those sites under-reports exactly the ones worth reading, and a
caller that does arithmetic on `hi_off` without checking raises TypeError on the
first image that has one. `rewrite()` below is built to make neither mistake
quietly.

ABSENCE IS EVIDENCE, NOT PROOF. A zero from this scanner means "no site of these
forms within this window", not "no reference exists". Score it with
`positive_control()` before believing any zero it returns.
"""

import struct

from . import mips

LUI = 0x0F
ORI = 0x0D
ADDIU = 0x09

SPLIT, ORPHAN = "SPLIT", "ORPHAN"

# Instruction distance a pending `lui` stays live. MEASURED: a window of 8
# scored 6,905 of 8,818 on the control population and the misses sat 12 and 15
# instructions after their `lui`. 32 covers every pair on this disc with the
# clobber model carrying the cost of the extra reach.
WINDOW = 32

# The load opcodes, `lb` through `lwr`. An ORPHAN site is only credited when the
# register was LOADED, which is what makes its high half come from memory.
LOAD_OPS = frozenset(mips.LOAD)


def writes(w):
    """The register number an instruction writes, or None.

    Deliberately conservative in one direction only: an instruction this does
    not recognize returns None, which means a pending `lui` survives it. That is
    the unsafe direction and it is why the coverage note in the module docstring
    names it.
    """
    op = (w >> 26) & 0x3F
    if op == 0x00:                                  # SPECIAL
        fn = w & 0x3F
        if fn in (0x08, 0x0C, 0x0D):                # jr, syscall, break
            return None
        if fn in (0x11, 0x13):                      # mthi, mtlo
            return None
        if fn in (0x18, 0x19, 0x1A, 0x1B):          # mult, multu, div, divu
            return None
        return (w >> 11) & 0x1F                     # rd, and jalr is one of them
    if op == 0x01:                                  # REGIMM
        rt = (w >> 16) & 0x1F
        return 31 if rt in (0x10, 0x11) else None   # bltzal, bgezal write ra
    if op == 0x02:                                  # j
        return None
    if op == 0x03:                                  # jal
        return 31
    if op in (0x04, 0x05, 0x06, 0x07):              # beq, bne, blez, bgtz
        return None
    if 0x08 <= op <= 0x0F:                          # addi..lui, all write rt
        return (w >> 16) & 0x1F
    if op in mips.LOAD:
        return (w >> 16) & 0x1F
    if op == 0x10 and ((w >> 21) & 0x1F) == 0:      # mfc0
        return (w >> 16) & 0x1F
    if op == 0x12 and ((w >> 21) & 0x1F) in (0x00, 0x02):   # mfc2, cfc2
        return (w >> 16) & 0x1F
    return None                                     # stores, cop2 ops, unknown


def compose(hi, lo, op):
    """The 32-bit value a `lui`/low-half pair computes.

    `ori` zero-extends and ORs. `addiu` SIGN EXTENDS and adds.
    """
    if op == ORI:
        return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)
    if op == ADDIU:
        lo = lo & 0xFFFF
        return (((hi & 0xFFFF) << 16) + (lo - 0x10000 if lo & 0x8000 else lo)) \
            & 0xFFFFFFFF
    raise ValueError("not a split-immediate low half: opcode 0x%02X" % op)


def halves(value, op):
    """(high halfword, low halfword) to STORE for a composed value.

    The inverse of compose(), and `compose(*halves(v, op), op) == v` for every
    32-bit v and both opcodes. The `addiu` carry is what makes this necessary:
    a low half with bit 15 set borrows 1 from the high half, so the high half
    must be written as `(value + 0x8000) >> 16`, not as `value >> 16`.

    BOTH HALVES ARE ALWAYS RETURNED. A rewriter that patches only the low half
    is correct until the new value crosses a 0x10000 boundary and then silently
    is not.
    """
    value &= 0xFFFFFFFF
    if op == ORI:
        return (value >> 16) & 0xFFFF, value & 0xFFFF
    if op == ADDIU:
        return ((value + 0x8000) >> 16) & 0xFFFF, value & 0xFFFF
    raise ValueError("not a split-immediate low half: opcode 0x%02X" % op)


class Site(object):
    """One constructed reference.

    form      SPLIT or ORPHAN
    hi_off    byte offset of the `lui`, or None when no high half was located.
              Today only an ORPHAN reports None, but the fact a caller may rely
              on is the weaker one: None means the image does not tell us where
              the high half is, so nothing may be composed, written or measured
              at a high half here. See the delay-slot form in the module
              docstring for a site that is a real reference and still has None.
    lo_off    byte offset of the low half
    lo_op     ORI or ADDIU
    reg       the register the value is built in
    value     the composed 32-bit value for a SPLIT; for an ORPHAN this is the
              16-bit immediate alone, because that is the whole of what is
              known and the whole of what may be rewritten
    """

    __slots__ = ("form", "hi_off", "lo_off", "lo_op", "reg", "value")

    def __init__(self, form, hi_off, lo_off, lo_op, reg, value):
        self.form = form
        self.hi_off = hi_off
        self.lo_off = lo_off
        self.lo_op = lo_op
        self.reg = reg
        self.value = value

    def __repr__(self):
        hi = "None" if self.hi_off is None else "0x%X" % self.hi_off
        return "Site(%s, hi=%s, lo=0x%X, %s, %s, 0x%X)" % (
            self.form, hi, self.lo_off,
            "ori" if self.lo_op == ORI else "addiu",
            mips.REG[self.reg], self.value)


def find(buf, accept, accept_low=None, window=WINDOW, base=0):
    """[Site] for every constructed reference in `buf`.

    accept(value)      -> True for a composed 32-bit value worth reporting.
    accept_low(imm)    -> True for a 16-bit ORPHAN immediate worth reporting.
                          None disables the ORPHAN form entirely, which is the
                          right choice for a caller with no low-half oracle:
                          without one the form is a guess, not a measurement.
    window             -> instructions a pending `lui` stays live.
    base               -> added to every reported offset.

    One linear pass. A `lui` is pending for its register until the register is
    written again, so a clobber ends the pair rather than being scanned past.
    """
    out = []
    pending = {}        # reg -> (offset, immediate)
    last_op = {}        # reg -> (offset, opcode of the writing instruction)
    n = len(buf) - (len(buf) % 4)
    for o in range(0, n, 4):
        w = struct.unpack_from("<I", buf, o)[0]
        op = (w >> 26) & 0x3F
        rs = (w >> 21) & 0x1F
        rt = (w >> 16) & 0x1F
        imm = w & 0xFFFF

        if op == LUI:
            # `lui` has no source register. A word with rs set is some other
            # encoding and mips.dis() rejects it, so this does too.
            if rs == 0:
                pending[rt] = (o, imm)
                last_op[rt] = (o, op)
                continue

        elif op in (ORI, ADDIU) and rs == rt:
            live = pending.get(rt)
            if live is not None and (o - live[0]) <= 4 * window:
                value = compose(live[1], imm, op)
                if accept(value):
                    out.append(Site(SPLIT, base + live[0], base + o, op, rt,
                                    value))
                # Consumed either way. The `lui` has been used; a later low half
                # for the same register is a different construction.
                del pending[rt]
                last_op[rt] = (o, op)
                continue
            if op == ORI and accept_low is not None and accept_low(imm):
                # ORPHAN. The high half must have been LOADED. If the nearest
                # prior write was a `lui` this scan already rejected as
                # clobbered or out of range, it is not an orphan, it is a miss,
                # and crediting it would hide the miss.
                src = last_op.get(rt)
                if src is not None and src[1] in LOAD_OPS \
                        and (o - src[0]) <= 4 * window:
                    out.append(Site(ORPHAN, None, base + o, op, rt, imm))
                    last_op[rt] = (o, op)
                    continue

        d = writes(w)
        if d is not None:
            pending.pop(d, None)
            last_op[d] = (o, op)
    return out


def find_word_refs(buf, tid, starts, window=WINDOW, base=0):
    """[Site] for constructed references to text block `tid`.

    `starts` is the set of valid bit offsets for that block, which is what makes
    this a measurement rather than a pattern match: a composed value is credited
    only when its low 20 bits land exactly on a string start. `huffman.string_offsets`
    produces that set.
    """
    starts = frozenset(starts)

    def accept(value):
        return (value >> 20) == tid and (value & 0xFFFFF) in starts

    def accept_low(imm):
        return imm in starts

    return find(buf, accept, accept_low, window, base)


def rewrite(buf, sites, value, base=0):
    """Store `value` at every site in `sites`. Returns (bytes, whole, low_only).

    `whole` lists the sites that took ALL of `value`, high half and low half.
    `low_only` lists the sites with `hi_off is None`, where only `value & 0xFFFF`
    was written because the image does not say where the other half is.

    `base` is the value that was added to the offsets in `sites`, and is
    subtracted again here. It is the same `base` that was passed to `find()`.

    THE RETURN SHAPE IS THE POINT, and it is the shape because of a real defect.
    Gate 45 of verify.py open-coded this loop and read `s.hi_off - base` with no
    check. On an image whose only sites had high halves it ran and passed; on the
    first image carrying a lone low half it raised TypeError midway through the
    suite, and the same code therefore had two different verdicts depending on
    what the image contained. The two available repairs were both worse than this
    one: raising on a lone low half moves the crash without removing it, and
    skipping it silently makes the count fall by one with nothing said, which is
    the failure this whole module exists to avoid.

    So a lone low half is neither refused nor hidden. It is written as far as it
    can be and RETURNED IN ITS OWN LIST, and the caller must decide what a
    partial write means. It does not mean a build may patch one: the composed
    value at such a site depends on a high half somewhere this module cannot see,
    so a 16-bit write there is defensible only against a value that is already a
    complete answer on its own, such as a bare string offset. Passing a full
    packed reference and taking its low half is how a rewriter silently produces
    a reference 0x10000 wrong, which is the same trap `halves()` documents.
    """
    out = bytearray(buf)
    whole, low_only = [], []
    for s in sites:
        hi, lo = halves(value, s.lo_op)
        pairs = [(s.lo_off - base, lo)]
        if s.hi_off is None:
            low_only.append(s)
        else:
            pairs.append((s.hi_off - base, hi))
            whole.append(s)
        for off, imm in pairs:
            w = struct.unpack_from("<I", out, off)[0]
            struct.pack_into("<I", out, off, (w & 0xFFFF0000) | imm)
    return bytes(out), whole, low_only


def positive_control(buf, tid, starts, known, window=WINDOW, base=0):
    """Score this recognizer against references KNOWN to exist.

    Returns (found, expected, missing), where `missing` is the sorted list of
    low-half offsets in `known` that this scan did not report.

    THE POINT OF THE RETURN SHAPE. It is a fraction and a list, not a boolean.
    `pass` is what a scanner prints when it recovered every known reference AND
    what it prints when the harness handed it an empty `known`, and those are the
    two cases a control exists to tell apart. A fraction names its own
    denominator. See rule 33 and rule 45 of docs/CODEX.md.

    AND THE CONSEQUENCE IS RETROACTIVE. If this does not recover all of `known`,
    every clean result this scanner has already produced reverts to UNCONFIRMED.
    A scanner is not re-validated by the runs it has survived.
    """
    known = set(known)
    got = set(s.lo_off for s in find_word_refs(buf, tid, starts, window, base))
    return len(known & got), len(known), sorted(known - got)
