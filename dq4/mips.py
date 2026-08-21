"""MIPS R3000A disassembler and assembler.

dis(word, addr) returns a canonical text form. asm(text, addr) parses that form
back to a word. The pair is what makes the round-trip gate meaningful: a decoder
that emitted the wrong register or a truncated immediate would fail to reassemble.

COP2 (the GTE) is decoded as an opaque `cop2` op carrying its payload, which
round-trips but is not interpreted. Anything the tables do not cover returns None
from dis() and is reported as undecodable rather than guessed at.

Address mapping for a PS-X EXE is derived from its header, not assumed. See
exe_mapping().
"""

import struct

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]
RIDX = {r: i for i, r in enumerate(REG)}

SPECIAL = {
    0x00: "sll", 0x02: "srl", 0x03: "sra", 0x04: "sllv", 0x06: "srlv", 0x07: "srav",
    0x08: "jr", 0x09: "jalr", 0x0C: "syscall", 0x0D: "break",
    0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo",
    0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu",
    0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu",
    0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor",
    0x2A: "slt", 0x2B: "sltu",
}
SHIFT = {"sll", "srl", "sra"}
SHIFTV = {"sllv", "srlv", "srav"}
RRR = {"add", "addu", "sub", "subu", "and", "or", "xor", "nor", "slt", "sltu"}
HILO_GET = {"mfhi", "mflo"}
HILO_SET = {"mthi", "mtlo"}
MULDIV = {"mult", "multu", "div", "divu"}

REGIMM = {0x00: "bltz", 0x01: "bgez", 0x10: "bltzal", 0x11: "bgezal"}

LOGICAL_IMM = frozenset((0x0C, 0x0D, 0x0E))
IMM = {0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu",
       0x0C: "andi", 0x0D: "ori", 0x0E: "xori"}
LOAD = {0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw",
        0x24: "lbu", 0x25: "lhu", 0x26: "lwr"}
STORE = {0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw", 0x2E: "swr"}
BRANCH2 = {0x04: "beq", 0x05: "bne"}
BRANCH1 = {0x06: "blez", 0x07: "bgtz"}
COP2MEM = {0x32: "lwc2", 0x3A: "swc2"}


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def dis(w, addr=0):
    """Canonical text for one instruction word, or None if not decodable."""
    op = (w >> 26) & 0x3F
    rs = (w >> 21) & 0x1F
    rt = (w >> 16) & 0x1F
    rd = (w >> 11) & 0x1F
    sa = (w >> 6) & 0x1F
    fn = w & 0x3F
    imm = w & 0xFFFF
    if op == 0x00:
        name = SPECIAL.get(fn)
        if name is None:
            return None
        if w == 0:
            return "nop"
        # Reserved fields must be zero. Without these checks arbitrary data
        # decodes as plausible instructions and the round-trip gate cannot hold.
        if name in SHIFT:
            if rs: return None
            return "%s %s,%s,%d" % (name, REG[rd], REG[rt], sa)
        if name in SHIFTV:
            if sa: return None
            return "%s %s,%s,%s" % (name, REG[rd], REG[rt], REG[rs])
        if name == "jr":
            if rt or rd or sa: return None
            return "jr %s" % REG[rs]
        if name == "jalr":
            if rt or sa: return None
            return "jalr %s,%s" % (REG[rd], REG[rs])
        if name in ("syscall", "break"):
            return "%s 0x%X" % (name, (w >> 6) & 0xFFFFF)
        if name in HILO_GET:
            if rs or rt or sa: return None
            return "%s %s" % (name, REG[rd])
        if name in HILO_SET:
            if rt or rd or sa: return None
            return "%s %s" % (name, REG[rs])
        if name in MULDIV:
            if rd or sa: return None
            return "%s %s,%s" % (name, REG[rs], REG[rt])
        if name in RRR:
            if sa: return None
            return "%s %s,%s,%s" % (name, REG[rd], REG[rs], REG[rt])
        return None
    if op == 0x01:
        name = REGIMM.get(rt)
        if name is None:
            return None
        return "%s %s,0x%08X" % (name, REG[rs], (addr + 4 + (_s16(imm) << 2)) & 0xFFFFFFFF)
    if op in (0x02, 0x03):
        name = "j" if op == 0x02 else "jal"
        return "%s 0x%08X" % (name, ((addr + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2))
    if op in BRANCH2:
        return "%s %s,%s,0x%08X" % (BRANCH2[op], REG[rs], REG[rt],
                                    (addr + 4 + (_s16(imm) << 2)) & 0xFFFFFFFF)
    if op in BRANCH1:
        if rt: return None
        return "%s %s,0x%08X" % (BRANCH1[op], REG[rs],
                                 (addr + 4 + (_s16(imm) << 2)) & 0xFFFFFFFF)
    if op in IMM:
        # andi/ori/xori zero-extend their immediate; the arithmetic and set-less-than
        # forms sign-extend it. Printing a logical immediate signed is wrong for a reader
        # even though it reassembles, so the two families are formatted differently.
        if op in LOGICAL_IMM:
            return "%s %s,%s,0x%04X" % (IMM[op], REG[rt], REG[rs], imm)
        return "%s %s,%s,%d" % (IMM[op], REG[rt], REG[rs], _s16(imm))
    if op == 0x0F:
        if rs: return None
        return "lui %s,0x%04X" % (REG[rt], imm)
    if op in LOAD or op in STORE:
        name = LOAD.get(op) or STORE[op]
        return "%s %s,%d(%s)" % (name, REG[rt], _s16(imm), REG[rs])
    if op == 0x10:                      # COP0
        if rs == 0:
            if w & 0x7FF: return None
            return "mfc0 %s,%d" % (REG[rt], rd)
        if rs == 4:
            if w & 0x7FF: return None
            return "mtc0 %s,%d" % (REG[rt], rd)
        if rs == 0x10 and fn == 0x10:
            return "rfe"
        return None
    if op == 0x12:                      # COP2, opaque
        return "cop2 0x%07X" % (w & 0x3FFFFFF)
    if op in COP2MEM:
        return "%s $%d,%d(%s)" % (COP2MEM[op], rt, _s16(imm), REG[rs])
    return None


def asm(text, addr=0):
    """Parse the canonical form back to a word. Raises on anything it cannot build."""
    text = text.strip()
    if text == "nop":
        return 0
    if text == "rfe":
        return (0x10 << 26) | (0x10 << 21) | 0x10
    parts = text.split(None, 1)
    name = parts[0]
    args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []

    def r(x):
        return RIDX[x]

    inv = {v: k for k, v in SPECIAL.items()}
    if name in SHIFT:
        return (inv[name]) | (r(args[1]) << 16) | (r(args[0]) << 11) | (int(args[2]) << 6)
    if name in SHIFTV:
        return (inv[name]) | (r(args[2]) << 21) | (r(args[1]) << 16) | (r(args[0]) << 11)
    if name == "jr":
        return (inv[name]) | (r(args[0]) << 21)
    if name == "jalr":
        return (inv[name]) | (r(args[1]) << 21) | (r(args[0]) << 11)
    if name in ("syscall", "break"):
        return (inv[name]) | (int(args[0], 16) << 6)
    if name in HILO_GET:
        return (inv[name]) | (r(args[0]) << 11)
    if name in HILO_SET:
        return (inv[name]) | (r(args[0]) << 21)
    if name in MULDIV:
        return (inv[name]) | (r(args[0]) << 21) | (r(args[1]) << 16)
    if name in RRR:
        return (inv[name]) | (r(args[1]) << 21) | (r(args[2]) << 16) | (r(args[0]) << 11)
    rinv = {v: k for k, v in REGIMM.items()}
    if name in rinv:
        off = ((int(args[1], 16) - addr - 4) >> 2) & 0xFFFF
        return (0x01 << 26) | (r(args[0]) << 21) | (rinv[name] << 16) | off
    if name in ("j", "jal"):
        op = 0x02 if name == "j" else 0x03
        return (op << 26) | ((int(args[0], 16) & 0x0FFFFFFF) >> 2)
    binv = {v: k for k, v in BRANCH2.items()}
    if name in binv:
        off = ((int(args[2], 16) - addr - 4) >> 2) & 0xFFFF
        return (binv[name] << 26) | (r(args[0]) << 21) | (r(args[1]) << 16) | off
    b1inv = {v: k for k, v in BRANCH1.items()}
    if name in b1inv:
        off = ((int(args[1], 16) - addr - 4) >> 2) & 0xFFFF
        return (b1inv[name] << 26) | (r(args[0]) << 21) | off
    iinv = {v: k for k, v in IMM.items()}
    if name in iinv:
        return (iinv[name] << 26) | (r(args[1]) << 21) | (r(args[0]) << 16) | (int(args[2], 0) & 0xFFFF)
    if name == "lui":
        return (0x0F << 26) | (r(args[0]) << 16) | int(args[1], 16)
    linv = {v: k for k, v in LOAD.items()}
    sinv = {v: k for k, v in STORE.items()}
    if name in linv or name in sinv:
        op = linv.get(name)
        if op is None:
            op = sinv[name]
        offpart, base = args[1].split("(")
        return (op << 26) | (r(base.rstrip(")")) << 21) | (r(args[0]) << 16) \
            | (int(offpart) & 0xFFFF)
    if name in ("mfc0", "mtc0"):
        rs = 0 if name == "mfc0" else 4
        return (0x10 << 26) | (rs << 21) | (r(args[0]) << 16) | (int(args[1]) << 11)
    if name == "cop2":
        return (0x12 << 26) | (int(args[0], 16) & 0x3FFFFFF)
    c2inv = {v: k for k, v in COP2MEM.items()}
    if name in c2inv:
        offpart, base = args[1].split("(")
        return (c2inv[name] << 26) | (r(base.rstrip(")")) << 21) \
            | (int(args[0].lstrip("$")) << 16) | (int(offpart) & 0xFFFF)
    raise ValueError("cannot assemble %r" % text)


def exe_mapping(buf):
    """(load_addr, entry, text_size, text_file_offset) from a PS-X EXE header."""
    if buf[:8] != b"PS-X EXE":
        raise ValueError("not a PS-X EXE")
    entry = struct.unpack_from("<I", buf, 0x10)[0]
    load = struct.unpack_from("<I", buf, 0x18)[0]
    size = struct.unpack_from("<I", buf, 0x1C)[0]
    return load, entry, size, 0x800


def va_to_off(va, load, text_off=0x800):
    return va - load + text_off


def off_to_va(off, load, text_off=0x800):
    return off - text_off + load


def iter_words(buf, load, text_off=0x800, size=None):
    """(va, word) over the text segment."""
    end = len(buf) if size is None else text_off + size
    for o in range(text_off, min(end, len(buf)) - 3, 4):
        yield off_to_va(o, load, text_off), struct.unpack_from("<I", buf, o)[0]


def disasm_range(buf, load, start_va, count, text_off=0x800):
    """[(va, word, text)] for count instructions from start_va."""
    out = []
    o = va_to_off(start_va, load, text_off)
    for k in range(count):
        if o + 4 > len(buf):
            break
        w = struct.unpack_from("<I", buf, o)[0]
        out.append((start_va + 4 * k, w, dis(w, start_va + 4 * k)))
        o += 4
    return out


def disasm_function(buf, load, start_va, limit=4000, text_off=0x800):
    """Disassemble to the first jr $ra plus its delay slot, or limit."""
    out = []
    va = start_va
    o = va_to_off(va, load, text_off)
    seen_jr = False
    while len(out) < limit and o + 4 <= len(buf):
        w = struct.unpack_from("<I", buf, o)[0]
        t = dis(w, va)
        out.append((va, w, t))
        if seen_jr:
            break
        if t == "jr ra":
            seen_jr = True
        va += 4
        o += 4
    return out
