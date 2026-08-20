"""Control code table and census.

MANDY is the published table. EXTRA lists the codes present in the data and absent
from it; no meanings are proposed for those. NAME_CODES is the name substitution range.

census() counts control codes across decoded symbol lists. diff_against_mandy()
returns (missing_from_data, extra_in_data); missing should always be empty.

Format details are in FORMAT.md section 6.
"""

TERMINATOR = 0x0000

MANDY = {
    0x7F02: "new line plus tab",
    0x7F04: "name decorator, starts named dialog",
    0x7F0A: "blinking cursor",
    0x7F0B: "end of line, opposite of 7F0A",
    0x7F0C: "end of line, appears in groups of about six",
    0x7F15: "received gold",
    0x7F16: "unknown, see 7F18",
    0x7F17: "unknown",
    0x7F18: "unknown",
    0x7F1A: "ルーシア",
    0x7F1F: "player name",
    0x7F20: "ライアン",
    0x7F21: "アリーナ",
    0x7F22: "クリフト",
    0x7F23: "ブライ",
    0x7F24: "トルネコ",
    0x7F25: "ミネア",
    0x7F26: "マーニャ",
    0x7F28: "スコット",
    0x7F29: "アレクス",
    0x7F2A: "フレア",
    0x7F2B: "ホイミン",
    0x7F2C: "オーリン",
    0x7F2D: "ホフマン, not always",
    0x7F2E: "パノン",
    0x7F2F: "ルーシア",
    0x7F30: "person",
    0x7F31: "ピサロ, mostly seen as デス{7F31}",
    0x7F32: "ロザリー",
    0x7F33: "person",
    0x7F34: "custom name",
    0x7F42: "town name",
    0x7F43: "emphasis, unconfirmed",
    0x7F44: "emphasis, sad contexts",
    0x7F45: "emphasis, before デスピサロ dialog",
    0x7F4B: "noun",
    0x7F4C: "name, possibly same as 7F33",
}

# Present in the data, absent from Mandy's table. Meanings deliberately not proposed.
EXTRA = (0x7F05, 0x7F11, 0x7F12, 0x7F13, 0x7F14, 0x7F47)

NAME_CODES = tuple(range(0x7F20, 0x7F30))


def describe(code):
    if code in MANDY:
        return MANDY[code]
    if code in EXTRA:
        return "undocumented, no meaning proposed"
    return "unknown"


def census(symbol_lists):
    """{code: count} over any number of decoded symbol lists."""
    out = {}
    for syms in symbol_lists:
        for kind, val in syms:
            if kind == "CTRL":
                out[val] = out.get(val, 0) + 1
    return out


def diff_against_mandy(measured_codes):
    """(missing_from_data, extra_in_data). missing should always be empty."""
    hers = set(MANDY)
    mine = set(measured_codes)
    return sorted(hers - mine), sorted(mine - hers)
