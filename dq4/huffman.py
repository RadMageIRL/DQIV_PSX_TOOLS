"""Huffman decode and encode.

HuffmanTree is built from a parsed TextBlock and owns the tree for that block only.

  walk()            every leaf with its depth, slot, kind, value and bit code
  decode()          the code stream as [(kind, value)]
  encode(syms, pad_to=n)  pack symbols back to bytes
  round_trip_ok()   decode then encode and compare byte for byte

Contract notes for callers:

  * encode() must be given pad_to=len(original) to reproduce a block byte exactly.
  * kind is one of NODE, CTRL, DICT, END, SJIS. DICT symbols are unresolved until
    dictionary.expand() is applied.
  * render() and split_strings() are display helpers, not part of the codec.

Format details are in FORMAT.md section 4.
"""

NODE, CTRL, DICT, END, SJIS = "NODE", "CTRL", "DICT", "END", "SJIS"


class HuffmanTree:
    """Built from a parsed TextBlock."""

    def __init__(self, tb):
        self.tb = tb
        self.pairs = tb.pairs
        self.m = tb.m
        self.root = tb.root
        self.n = tb.npairs
        self._codes = None
        self._depths = None

    def slot(self, nn, side):
        return nn if side == 0 else self.m + nn

    def entry(self, i):
        b0, b1 = self.pairs[i]
        v = (b1 << 8) | b0
        if v >= 0x8000:
            return (NODE, v - 0x8000)
        if b1 == 0x7F:
            return (CTRL, v)
        if b1 == 0x7E:
            return (DICT, v)
        if v == 0x0000:
            return (END, 0)
        return (SJIS, v + 0x8000)

    # --- structure ------------------------------------------------------

    def walk(self):
        """(leaves, arrivals, overflow).

        leaves is [(depth, slot, kind, value, code)], arrivals counts how many
        times each array slot is reached, overflow lists out-of-range children.
        """
        leaves = []
        arrivals = [0] * self.n
        overflow = []
        stack = [(self.root, 0, "")]
        guard = 0
        while stack:
            nn, depth, code = stack.pop()
            guard += 1
            if guard > 1000000:
                raise RuntimeError("tree walk did not terminate")
            for side in (0, 1):
                i = self.slot(nn, side)
                if i >= self.n:
                    overflow.append((nn, side, i))
                    continue
                arrivals[i] += 1
                kind, val = self.entry(i)
                if kind == NODE:
                    stack.append((val, depth + 1, code + str(side)))
                else:
                    leaves.append((depth + 1, i, kind, val, code + str(side)))
        return leaves, arrivals, overflow

    def kraft_sum(self, leaves=None):
        if leaves is None:
            leaves, _, _ = self.walk()
        return sum(2.0 ** -d for d, _, _, _, _ in leaves)

    def min_leaf_depth(self, leaves=None):
        if leaves is None:
            leaves, _, _ = self.walk()
        return min(d for d, _, _, _, _ in leaves)

    def codes(self):
        """{(kind, value): bitstring} for encoding."""
        if self._codes is None:
            leaves, _, _ = self.walk()
            c = {}
            for _, _, kind, val, code in leaves:
                c.setdefault((kind, val), code)
            self._codes = c
        return self._codes

    # --- decode / encode ------------------------------------------------

    def decode(self, data=None, start=None, end=None):
        """[(kind, value)] for the code stream. Defaults to [c, e)."""
        raw = self.tb.raw if data is None else data
        pos = self.tb.c if start is None else start
        stop = self.tb.e if end is None else end
        out = []
        nn = self.root
        bit = 0
        while pos < stop:
            b = (raw[pos] >> bit) & 1
            bit += 1
            if bit == 8:
                bit = 0
                pos += 1
            i = self.slot(nn, b)
            if i >= self.n:
                raise ValueError("tree index overflow while decoding")
            kind, val = self.entry(i)
            if kind == NODE:
                nn = val
            else:
                out.append((kind, val))
                nn = self.root
        return out

    def encode(self, symbols, pad_to=None):
        """Pack symbols back to bytes, LSB first, zero filled to pad_to bytes."""
        codes = self.codes()
        bits = []
        for sym in symbols:
            code = codes.get(sym)
            if code is None:
                raise KeyError("symbol %r is not a leaf of this tree" % (sym,))
            bits.extend(1 if ch == "1" else 0 for ch in code)
        size = pad_to if pad_to is not None else (len(bits) + 7) // 8
        out = bytearray(size)
        for j, b in enumerate(bits):
            if b:
                out[j // 8] |= 1 << (j % 8)
        return bytes(out), len(bits)

    def round_trip_ok(self):
        """Decode [c, e) and re-encode it; True when byte-exact.

        Zero fill to the original region length is part of the contract: 1,114
        blocks end with 1 to 10 trailing bits that complete no code, and all of
        those bits are zero.
        """
        original = self.tb.code_stream()
        symbols = self.decode()
        packed, _ = self.encode(symbols, pad_to=len(original))
        return packed == original


def render_symbol(kind, value):
    """One symbol as display text. Control and dictionary codes stay visible."""
    if kind == CTRL:
        return "<%04X>" % value
    if kind == DICT:
        return "{%04X}" % value
    if kind == END:
        return "<END>"
    try:
        return bytes([value >> 8, value & 0xFF]).decode("shift_jis")
    except Exception:
        return "<!%04X>" % value


def render(symbols):
    return "".join(render_symbol(k, v) for k, v in symbols)


def split_strings(symbols):
    """Split a symbol list on END. Trailing residue is returned separately."""
    out = []
    cur = []
    for k, v in symbols:
        if k == END:
            out.append(cur)
            cur = []
        else:
            cur.append((k, v))
    return out, cur
