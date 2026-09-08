"""THE BUILD-TIME SECTOR TABLE PREFLIGHT. Call this before writing an image.

WHY THIS EXISTS. Relocation is a write, and a partial or flag-dropping
relocation is invisible to booting: duplicate copies mask a stale entry, and
most byte-identical block groups hold no drawable text at all. A build that
moves a block and does not correct its table entry produces a disc that plays
perfectly until the player reaches the one screen that reads the stale entry.

The checks themselves live in sectortable.check_table(). This module only
supplies the base executable, turns a refusal into a nonzero exit, and gives a
build one call to make.

TWO WAYS IN. In a build, before the first inject:

    from dq4 import preflight
    preflight.preflight(bytes(exe), fin, base_disc=BASE, base_blocks=blocks)

where `fin` is hbd.scan_blocks() over the archive that is about to ship and
`base_blocks` is the same over the archive the build started from. The call
raises SystemExit if any of the five checks fails, so the build refuses rather
than writing a disc whose table is wrong.

PASS `base_blocks`. A build already has it, and without it check 5 cannot see a
relocation whose table entry was never rewritten: the entry looks non-live on
both sides and slips through. That hole was found by a mutant, not by review,
and it is reproduced in tests/test_sectortable.py.

On a finished pair of discs, from a shell:

    python -m dq4.preflight --base <base image> --built <built image>
"""

from __future__ import print_function

import argparse
import hashlib
import os

from . import hbd
from . import iso as isomod
from . import sectortable

EXECUTABLE = "SLPM_869.16"
ARCHIVE = "HBD1PS1D.Q41"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract(disc, name):
    with isomod.RawISO(disc) as im:
        return bytes(im.extract(*im.find(name)))


def base_executable(base_disc):
    """The executable out of a disc image. Read only."""
    return _extract(base_disc, EXECUTABLE)


def base_archive(base_disc):
    """The archive out of a disc image. Read only."""
    return _extract(base_disc, ARCHIVE)


def preflight(built_exe, built_blocks, base_exe=None, base_disc=None,
              base_blocks=None, say=print, fatal=True):
    """Run the invariant. Returns the Report. Raises SystemExit on refusal.

    Exactly one of `base_exe` and `base_disc` is needed. `built_blocks` is
    hbd.scan_blocks() over the archive that will ship beside `built_exe`.

    `base_blocks` is hbd.scan_blocks() over the archive the build started from.
    If it is not passed and `base_disc` is, it is read from that disc rather
    than quietly going without.
    """
    if base_exe is None:
        if base_disc is None:
            raise ValueError("preflight needs base_exe or base_disc")
        base_exe = base_executable(base_disc)
    if base_blocks is None and base_disc is not None:
        base_blocks = hbd.scan_blocks(base_archive(base_disc))

    rep = sectortable.check_table(base_exe, built_exe, built_blocks,
                                  base_blocks=base_blocks)
    say("SECTOR TABLE PREFLIGHT, %d entries over the whole table"
        % sectortable.ENTRY_COUNT)
    for line in rep.lines():
        say(line)
    if not rep.ok and fatal:
        raise SystemExit("SECTOR TABLE PREFLIGHT REFUSED: %s"
                         % ", ".join(c.name for c in rep.failures))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sector table preflight.")
    ap.add_argument("--base", required=True,
                    help="the disc image the build started from")
    ap.add_argument("--built", required=True, help="the disc image to check")
    a = ap.parse_args(argv)

    for p in (a.base, a.built):
        if not os.path.exists(p):
            raise SystemExit("no such image: %s" % p)

    # Hashed before and after, because a checker that writes to what it reads
    # is worse than no checker.
    before = [sha256(a.base), sha256(a.built)]
    print("BASE  %s  %s" % (before[0], os.path.basename(a.base)))
    print("BUILT %s  %s" % (before[1], os.path.basename(a.built)))

    rep = preflight(_extract(a.built, EXECUTABLE),
                    hbd.scan_blocks(_extract(a.built, ARCHIVE)),
                    base_exe=base_executable(a.base),
                    base_blocks=hbd.scan_blocks(base_archive(a.base)),
                    fatal=False)

    after = [sha256(a.base), sha256(a.built)]
    if after != before:
        raise SystemExit("REFUSED: an input image changed under the checker")
    print("BASE  %s  AFTER, unchanged" % after[0])
    print("BUILT %s  AFTER, unchanged" % after[1])
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
