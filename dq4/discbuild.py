"""Write a file back into a copy of a raw PSX disc image, in place.

Same-size, in-place only. No sector relocation, no length changes: the payload
must be exactly the size the directory entry already records, so the only
sectors that change are the ones the file already occupies.

The source image is opened read-only and never written. Every build produces a
new file.

EDC and ECC are regenerated on every sector the payload touches. On this disc
that regeneration is a no-op for unchanged data, which is itself the check:
`dq4.edcecc` reproduces the original mastering byte for byte, so a null build
comes out identical to its source and any difference is a real difference.
"""
import hashlib
import os
import shutil

from . import edcecc
from . import iso as isomod

RAW = 2352
USER = 2048
USER_OFF = 24


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_cue(cue_path, bin_name):
    """A .cue whose FILE line names the bin sitting next to it.

    The source disc's own cue names a bin that does not exist (Phase 0); that
    defect is deliberately not reproduced.
    """
    with open(cue_path, "w", newline="\r\n") as f:
        f.write('FILE "%s" BINARY\n' % bin_name)
        f.write("  TRACK 01 MODE2/2352\n")
        f.write("    INDEX 01 00:00:00\n")


def inject(src_path, out_path, name, payload, progress=None):
    """Copy src to out, write payload over `name`, refresh EDC/ECC.

    Returns (lba, nsectors, changed_sectors).
    """
    with isomod.RawISO(src_path) as disc:
        found = disc.find(name)
        if not found:
            raise SystemExit("%s not found in %s" % (name, src_path))
        lba, size = found[0], found[1]
    if len(payload) != size:
        raise SystemExit("payload is %d bytes, the directory entry says %d; "
                         "this tool does not relocate or resize"
                         % (len(payload), size))
    nsec = (size + USER - 1) // USER
    shutil.copyfile(src_path, out_path)
    changed = 0
    with open(out_path, "r+b") as f:
        for i in range(nsec):
            off = (lba + i) * RAW
            f.seek(off)
            sec = bytearray(f.read(RAW))
            chunk = payload[i * USER:(i + 1) * USER]
            if len(chunk) < USER:
                chunk = chunk + sec[USER_OFF + len(chunk):USER_OFF + USER]
            before = bytes(sec)
            sec[USER_OFF:USER_OFF + USER] = chunk
            fixed = edcecc.fix(bytes(sec))
            if fixed != before:
                changed += 1
            f.seek(off)
            f.write(fixed)
            if progress and (i % 20000) == 0:
                progress(i, nsec)
    return lba, nsec, changed


def diff_sectors(a_path, b_path, limit=None):
    """[(lba, nbytes differing)] between two raw images of equal size."""
    sa, sb = os.path.getsize(a_path), os.path.getsize(b_path)
    if sa != sb:
        raise SystemExit("sizes differ: %d vs %d" % (sa, sb))
    out = []
    with open(a_path, "rb") as fa, open(b_path, "rb") as fb:
        lba = 0
        while True:
            ba = fa.read(RAW * 256)
            bb = fb.read(RAW * 256)
            if not ba:
                break
            if ba != bb:
                for k in range(0, len(ba), RAW):
                    x, y = ba[k:k + RAW], bb[k:k + RAW]
                    if x != y:
                        out.append((lba + k // RAW,
                                    sum(1 for j in range(len(x)) if x[j] != y[j])))
                        if limit and len(out) >= limit:
                            return out
            lba += len(ba) // RAW
    return out
