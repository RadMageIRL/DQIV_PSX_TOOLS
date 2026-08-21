"""Build a Huffman tree from symbol frequencies and emit it in the engine's form.

The decoder in `huffman.HuffmanTree` reads a tree; this builds one. The emitted
layout is the same dual-base structure documented in FORMAT.md section 4:

  tree header at `e`:  u32 base, u32 mid, u16 root      (10 bytes)
  pair array at base:  n = 2m + 1 entries of 2 bytes

Internal node `nn` owns exactly two array slots, `pair[nn]` for side 0 and
`pair[m + nn]` for side 1, so with node numbers 0..m-1 every slot below 2m is
the child of exactly one node and slot 2m is the single pad pair.

Three layout facts hold on all 1,106 blocks and are reproduced here rather than
invented (MEASURED, Phase 17):

    root == m - 1        internal nodes are numbered in creation order, so the
                         root, created last, is always the highest number
    base == e + 10       the pair array follows the 10-byte tree header
    npairs == 2m + 1     m internal nodes, 2m children, one pad

A leaf descriptor is the inverse of `HuffmanTree.entry`:

    NODE   0x8000 + node number      (the WIDE form: 252 blocks exceed 256
                                      nodes, so a high-byte test is wrong)
    CTRL   the 0x7Fxx value as-is
    DICT   the 0x7Exx value as-is
    END    0x0000, a real symbol and not a sentinel
    SJIS   value - 0x8000
"""
import heapq
import struct

from . import huffman

PAD = (0x00, 0x00)


def descriptor(kind, value):
    """The u16 an entry of this kind and value is stored as."""
    if kind == huffman.NODE:
        return 0x8000 + value
    if kind == huffman.CTRL:
        if (value >> 8) != 0x7F:
            raise ValueError("CTRL value %04X is not 0x7Fxx" % value)
        return value
    if kind == huffman.DICT:
        if (value >> 8) != 0x7E:
            raise ValueError("DICT value %04X is not 0x7Exx" % value)
        return value
    if kind == huffman.END:
        return 0x0000
    if kind == huffman.SJIS:
        if value < 0x8000:
            raise ValueError("SJIS value %04X is below 0x8000" % value)
        return value - 0x8000
    raise ValueError("unknown symbol kind %r" % (kind,))


def build(freqs, min_depth=2):
    """(pairs, m, root) from {(kind, value): count}.

    Tie-breaking is deterministic: equal weights order by the symbol's sorted
    position, so the same frequencies always produce the same tree. Heart Beat's
    tie-breaking is implementation-defined and is not reproduced.

    min_depth=2 by default, because Heart Beat's encoder never emits a one-bit
    code: their minimum leaf depth is 2 to 5 on all 1,106 blocks, and Phase 1
    rejected a depth-1 candidate from structure alone (MEASURED, Phase 17).

    Constraining every length to at least 2 is the same problem as packing the
    symbols under a root with FOUR slots, since sum 2^-(L-2) = 4. So the
    constrained optimum is reached by running ordinary Huffman merges until
    exactly four items remain and hanging those at depth 2. Pairing among the
    four does not affect cost; all four sit at the same depth.
    """
    syms = sorted(freqs)
    if len(syms) < 2:
        raise ValueError("a tree needs at least two distinct symbols, got %d"
                         % len(syms))
    if min_depth not in (1, 2):
        raise ValueError("min_depth must be 1 or 2, got %r" % (min_depth,))
    if min_depth == 2 and len(syms) < 4:
        raise ValueError("min depth 2 needs at least 4 distinct symbols, got %d"
                         % len(syms))
    # heap entries: (weight, tag, payload) where payload is ("L", sym) or
    # ("N", node number). tag makes ordering total and therefore deterministic.
    heap = []
    for i, s in enumerate(syms):
        heapq.heappush(heap, (freqs[s], i, ("L", s)))
    children = []           # children[nn] = (side0 payload, side1 payload)
    tag = len(syms)
    stop = 4 if (min_depth == 2 and len(syms) >= 4) else 1
    while len(heap) > stop:
        w0, _t0, p0 = heapq.heappop(heap)
        w1, _t1, p1 = heapq.heappop(heap)
        nn = len(children)
        children.append((p0, p1))
        heapq.heappush(heap, (w0 + w1, tag, ("N", nn)))
        tag += 1
    if stop == 4:
        # four items at depth 2: pair them, then join the pairs at the root
        items = [heapq.heappop(heap) for _ in range(4)]
        for a, b in ((0, 1), (2, 3)):
            nn = len(children)
            children.append((items[a][2], items[b][2]))
            heapq.heappush(heap, (items[a][0] + items[b][0], tag, ("N", nn)))
            tag += 1
        w0, _t0, p0 = heapq.heappop(heap)
        w1, _t1, p1 = heapq.heappop(heap)
        children.append((p0, p1))
    m = len(children)
    root = m - 1
    n = 2 * m + 1
    pairs = [None] * n
    for nn, (p0, p1) in enumerate(children):
        for side, p in ((0, p0), (1, p1)):
            slot = nn if side == 0 else m + nn
            if p[0] == "N":
                v = descriptor(huffman.NODE, p[1])
            else:
                v = descriptor(p[1][0], p[1][1])
            pairs[slot] = (v & 0xFF, (v >> 8) & 0xFF)
    pairs[2 * m] = PAD
    missing = [i for i, p in enumerate(pairs) if p is None]
    if missing:
        raise AssertionError("pair slots left unfilled: %s" % missing[:8])
    return pairs, m, root


def emit(pairs, m, root, e):
    """The 10-byte tree header plus the packed pair array, as bytes.

    `e` is the block offset the header sits at, so base is e + 10.
    """
    base = e + 10
    mid = base + 2 * m
    out = bytearray()
    out += struct.pack("<IIH", base, mid, root)
    for b0, b1 in pairs:
        out.append(b0)
        out.append(b1)
    return bytes(out), base, mid


class _Shim:
    """Minimal TextBlock-alike so huffman.HuffmanTree can read a built tree.

    Gate A4 is exactly this: if the library's own decoder walks the emitted
    array without modification, the array has the structure the engine walks.
    """

    def __init__(self, pairs, m, root, raw=b"", c=0, e=0):
        self.pairs = pairs
        self.m = m
        self.root = root
        self.npairs = len(pairs)
        self.raw = raw
        self.c = c
        self.e = e


def tree_from(pairs, m, root, raw=b"", c=0, e=0):
    return huffman.HuffmanTree(_Shim(pairs, m, root, raw, c, e))


def frequencies(symbols):
    f = {}
    for s in symbols:
        f[s] = f.get(s, 0) + 1
    return f

def build_from_lengths(lengths):
    """(pairs, m, root) for a tree whose symbol code LENGTHS are exactly these.

    {(kind, value): length} in, a canonical assignment out. Used when the goal
    is to emit a tree of one's own construction while leaving every string's
    encoded length, and therefore every string start offset, untouched.

    The length vector must satisfy Kraft equality, which it does whenever it
    came from a full binary tree. A shortfall or excess raises rather than
    silently producing a tree that decodes to something else.
    """
    kraft = sum(2.0 ** -L for L in lengths.values())
    if abs(kraft - 1.0) > 1e-12:
        raise ValueError("code lengths do not satisfy Kraft equality: sum=%r" % kraft)
    # canonical codes: order by (length, symbol) and count up
    order = sorted(lengths, key=lambda s: (lengths[s], repr(s)))
    codes = {}
    code = 0
    prev = None
    for sym in order:
        L = lengths[sym]
        if prev is not None:
            code = (code + 1) << (L - prev)
        prev = L
        codes[sym] = format(code, "0%db" % L)

    # build the tree from the code strings
    root_node = {}
    for sym, bits in codes.items():
        node = root_node
        for ch in bits[:-1]:
            node = node.setdefault(ch, {})
            if not isinstance(node, dict):
                raise ValueError("code set is not prefix free at %r" % sym)
        if bits[-1] in node:
            raise ValueError("code set is not prefix free at %r" % sym)
        node[bits[-1]] = ("L", sym)

    # number internal nodes post-order, so children are created before parents
    # and the root, created last, is m - 1: the convention all 1,106 blocks use
    children = []

    def assign(node):
        kids = []
        for side in ("0", "1"):
            if side not in node:
                raise ValueError("internal node with a missing side")
            ch = node[side]
            kids.append(ch if isinstance(ch, tuple) else ("N", assign(ch)))
        children.append((kids[0], kids[1]))
        return len(children) - 1

    root = assign(root_node)
    m = len(children)
    pairs = [None] * (2 * m + 1)
    for nn, (p0, p1) in enumerate(children):
        for side, p in ((0, p0), (1, p1)):
            slot = nn if side == 0 else m + nn
            if p[0] == "N":
                v = descriptor(huffman.NODE, p[1])
            else:
                v = descriptor(p[1][0], p[1][1])
            pairs[slot] = (v & 0xFF, (v >> 8) & 0xFF)
    pairs[2 * m] = PAD
    if root != m - 1:
        raise AssertionError("root %d is not m-1 (%d)" % (root, m - 1))
    missing = [i for i, p in enumerate(pairs) if p is None]
    if missing:
        raise AssertionError("pair slots left unfilled: %s" % missing[:8])
    return pairs, m, root


def lengths_of(tree):
    """{(kind, value): code length} for an existing tree."""
    out = {}
    for depth, _slot, kind, val, code in tree.walk()[0]:
        out.setdefault((kind, val), len(code))
    return out
