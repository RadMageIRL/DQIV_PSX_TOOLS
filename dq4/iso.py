"""Raw disc image access.

RawISO opens a Mode 2 Form 1 image read-only and exposes sector reads, an ISO9660
directory walk, and file extraction by name. extract_to() is the only call here
that opens a file for writing, and it writes a copy out of the image.

Format details are in FORMAT.md section 1.
"""

import struct

RAW_SECTOR = 2352      # Mode 2 / 2352 raw sector
USER_OFFSET = 24       # 12 sync + 4 header + 8 subheader
USER_LENGTH = 2048     # Form 1 user data


class RawISO:
    """A Mode 2 Form 1 disc image opened read-only."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.f.seek(0, 2)
        self.size = self.f.tell()
        self.sector_count = self.size // RAW_SECTOR

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def sector(self, lba):
        """Whole 2352-byte raw sector."""
        self.f.seek(lba * RAW_SECTOR)
        s = self.f.read(RAW_SECTOR)
        if len(s) < RAW_SECTOR:
            raise EOFError("short sector %d in %s" % (lba, self.path))
        return s

    def data(self, lba):
        """The 2048 user bytes of one sector."""
        return self.sector(lba)[USER_OFFSET:USER_OFFSET + USER_LENGTH]

    def read(self, lba, nbytes):
        """nbytes of user data starting at lba."""
        out = bytearray()
        while len(out) < nbytes:
            out += self.data(lba)
            lba += 1
        return bytes(out[:nbytes])

    def pvd(self):
        """(lba, 2048 bytes) of the Primary Volume Descriptor."""
        for lba in range(16, 32):
            d = self.data(lba)
            if d[1:6] == b"CD001":
                if d[0] == 1:
                    return lba, d
                if d[0] == 255:
                    break
        raise ValueError("no Primary Volume Descriptor in %s" % self.path)

    def volume_id(self):
        _, pvd = self.pvd()
        return pvd[40:72].decode("ascii", "replace").strip()

    def system_id(self):
        _, pvd = self.pvd()
        return pvd[8:40].decode("ascii", "replace").strip()

    def files(self):
        """[(path, lba, size, kind)] for the whole tree, kind in {FILE, DIR}."""
        _, pvd = self.pvd()
        root = pvd[156:156 + 34]
        lba = struct.unpack_from("<I", root, 2)[0]
        length = struct.unpack_from("<I", root, 10)[0]
        out = []
        self._walk_dir(lba, length, "", out)
        return out

    def _walk_dir(self, lba, length, prefix, out):
        buf = self.read(lba, length)
        i = 0
        entries = []
        while i < len(buf):
            rlen = buf[i]
            if rlen == 0:
                # directory records do not straddle a sector boundary
                i = (i // USER_LENGTH + 1) * USER_LENGTH
                continue
            rec = buf[i:i + rlen]
            elba = struct.unpack_from("<I", rec, 2)[0]
            esize = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            nlen = rec[32]
            entries.append((rec[33:33 + nlen], elba, esize, flags))
            i += rlen
        for name, elba, esize, flags in entries:
            if name in (b"\x00", b"\x01"):     # . and ..
                continue
            full = prefix + "/" + name.decode("ascii", "replace")
            if flags & 0x02:
                out.append((full, elba, esize, "DIR"))
                self._walk_dir(elba, esize, full, out)
            else:
                out.append((full, elba, esize, "FILE"))

    def find(self, basename):
        """(lba, size) for a file by basename, version suffix ignored. None if absent."""
        for full, lba, size, kind in self.files():
            if kind != "FILE":
                continue
            leaf = full.rsplit("/", 1)[-1].split(";")[0]
            if leaf.upper() == basename.upper():
                return lba, size
        return None

    def extract(self, lba, size, chunk_sectors=512):
        """File contents as bytes, read in bulk."""
        out = bytearray()
        left = size
        cur = lba
        while left > 0:
            n = min(chunk_sectors, (left + USER_LENGTH - 1) // USER_LENGTH)
            self.f.seek(cur * RAW_SECTOR)
            raw = self.f.read(n * RAW_SECTOR)
            for i in range(n):
                base = i * RAW_SECTOR + USER_OFFSET
                out += raw[base:base + USER_LENGTH]
            cur += n
            left = size - len(out)
        return bytes(out[:size])

    def extract_to(self, lba, size, dest_path):
        """Write a file out of the image. The one writing call in this module."""
        with open(dest_path, "wb") as o:
            o.write(self.extract(lba, size))
