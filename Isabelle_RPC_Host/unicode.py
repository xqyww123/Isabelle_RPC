import os
import re
from collections import namedtuple
from itertools import accumulate

from .paths import resolve_isabelle_var, resolve_isabelle_path_list


def _load_symbols(path):
    """
    Load one Isabelle symbol file.
    Return: (ASCII-symbol -> unicode-symbol dict, the reverse dict, and an
             ASCII-symbol -> group dict from the `group:` field).
    """
    if not isinstance(path, str):
        raise ValueError("the argument path must be a string")
    symbols, reverse_symbols, groups = {}, {}, {}
    if not os.path.exists(path):
        return symbols, reverse_symbols, groups
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            # Every line has a form like `\<odiv>            code: 0x002A38   font: PhiSymbols   group: operator   abbrev: (-:)`
            # We extract the `\<odiv>` name, the `0x002A38` code point, and the
            # `operator` group. Skip comments and empty lines.
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Parse the line to extract symbol, code point, and group
            parts = line.split()

            # Extract the symbol name (like \<odiv>)
            symbol = parts[0]

            # Find the code point and group. Each field can be either
            # "key: value" (space) or "key:value" (no space).
            code_point = None
            group = None
            for i, part in enumerate(parts[1:], 1):  # Start index at 1 since we're iterating from parts[1:]
                if code_point is None and part.startswith('code:'):
                    if len(part) > 5:  # "code:" is 5 chars -> value glued on
                        code_point = part.split(':', 1)[1].strip()
                    elif i < len(parts) - 1:  # value is the next token
                        code_point = parts[i + 1].strip()
                elif group is None and part.startswith('group:'):
                    if len(part) > 6:  # "group:" is 6 chars -> value glued on
                        group = part.split(':', 1)[1].strip()
                    elif i < len(parts) - 1:  # value is the next token
                        group = parts[i + 1].strip()

            if symbol and code_point:
                try:
                    # Convert hex code point to unicode character
                    unicode_char = chr(int(code_point, 16))
                    # Add to dictionaries
                    symbols[symbol] = unicode_char
                    reverse_symbols[unicode_char] = symbol
                except ValueError:
                    # Skip an invalid code point, but still record the group below
                    pass
            if symbol and group:
                groups[symbol] = group
    return symbols, reverse_symbols, groups

# The loaded table, one record, read by field name.
_Table = namedtuple('_Table', 'symbols reverse trans letters files')
_TABLE = None

def _table():
    global _TABLE
    if _TABLE is None:
        _TABLE = _load_table()
    return _TABLE

def _load_table(symbol_files=None):
    if symbol_files is None:
        # ISABELLE_SYMBOLS is the authority: Isabelle assembles it from the distribution's
        # etc/symbols, the user overlay, and one entry per component that declares extra
        # symbols (phi-System appends its `symbols` and `symbols-words`). Rebuilding the
        # list from ISABELLE_HOME instead — which this used to do — silently drops every
        # component file, so a component symbol stays literal text and is never converted.
        symbol_files = resolve_isabelle_path_list("ISABELLE_SYMBOLS")
    if not symbol_files:
        # No settings environment to ask: ISABELLE_SYMBOLS is unset and `isabelle` is
        # unavailable. Fall back to the two files Isabelle always puts first, so that a
        # bare ISABELLE_HOME still yields the distribution's table.
        isabelle_home = resolve_isabelle_var("ISABELLE_HOME")
        if not isabelle_home:
            raise RuntimeError(
                "Cannot locate Isabelle: neither ISABELLE_SYMBOLS nor ISABELLE_HOME is "
                "set in the environment, and the `isabelle` executable is unavailable "
                "(not on PATH, or it failed to start). The Isabelle symbol table is "
                "required for unicode conversion, so refusing to silently fall back to "
                "identity.")
        symbol_files = [os.path.join(isabelle_home, "etc", "symbols")]
        # An unset ISABELLE_HOME_USER must not turn into the *relative* path
        # "etc/symbols" — which is what os.path.join("", ...) yields — or we would read
        # whatever stray file happens to sit under the working directory. It is optional.
        isabelle_home_user = resolve_isabelle_var("ISABELLE_HOME_USER")
        if isabelle_home_user:
            symbol_files.append(os.path.join(isabelle_home_user, "etc", "symbols"))
    SYMBOLS, REVERSE_SYMBOLS, GROUPS = {}, {}, {}
    for file in symbol_files:
        # In ISABELLE_SYMBOLS order, each file layering on top of the ones before it:
        # the user overlay overrides the distribution, and a component overrides both.
        symbols, reverse_symbols, groups = _load_symbols(file)
        SYMBOLS.update(symbols)
        REVERSE_SYMBOLS.update(reverse_symbols)
        GROUPS.update(groups)
    if not SYMBOLS:
        # The paths resolved but nothing loaded: files missing, unreadable, or empty
        # (a relocated/partial install, or a stale exported value). That would make
        # pretty_unicode silently degrade to identity — the exact regression we refuse.
        raise RuntimeError(
            f"Isabelle symbol table is empty: no symbols loaded from any of "
            f"{symbol_files} (missing, unreadable, or empty). "
            "Refusing to silently fall back to identity conversion.")
    # Isabelle's identifier "letter" class (Symbol.is_letter_symbol, a hardcoded
    # list in Pure/General/symbol.ML) is a SUBSET of the symbols whose file group
    # is `letter` or `greek` — verified: every ML letter-symbol falls in one of
    # these two groups. Using the union is therefore a safe OVER-approximation:
    # it never rejects a legal identifier symbol (no harmful false positive), and
    # its only extras (blackboard-bold letters, \<lambda>) merely fail to flag a
    # would-be proposition, which the ML fact parser catches anyway.
    LETTER_SYMBOLS = frozenset(s for s, g in GROUPS.items() if g in ('letter', 'greek'))
    return _Table(SYMBOLS, REVERSE_SYMBOLS, str.maketrans(REVERSE_SYMBOLS), LETTER_SYMBOLS,
                  tuple(symbol_files))

def get_SYMBOLS_AND_REVERSED():
    """(symbols, reverse, translation table, letter symbols): callers unpack this
    4-tuple by arity. The files behind it are get_SYMBOL_FILES()."""
    t = _table()
    return (t.symbols, t.reverse, t.trans, t.letters)

def get_SYMBOLS():
    return _table().symbols

def get_REVERSE_SYMBOLS():
    return _table().reverse

def get_LETTER_SYMBOLS():
    """The set of Isabelle symbols (as ASCII `\\<name>` strings) that may occur
    as a *letter* inside an identifier / fact name — a safe over-approximation
    of Symbol.is_letter_symbol (the file's `letter` and `greek` groups)."""
    return _table().letters

def get_SYMBOL_FILES():
    """The symbol files the loaded table was actually built from, in load order.

    Provenance, for anything that ships a compiled copy of the table: the set of files
    depends on which components are registered, so two machines can load different
    tables from identical code. A consumer that bakes the table into an artefact must
    record this list and refuse a mismatch, or the artefact and the data derived from
    it will disagree with no error anywhere. Kept out of get_SYMBOLS_AND_REVERSED()'s
    tuple on purpose — callers unpack that by arity."""
    return _table().files

SUBSUP_TRANS_TABLE = {
    "⇩0": "₀", "⇩1": "₁", "⇩2": "₂", "⇩3": "₃", "⇩4": "₄",
    "⇩5": "₅", "⇩6": "₆", "⇩7": "₇", "⇩8": "₈", "⇩9": "₉",
    #ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ
    "⇩a": "ₐ", "⇩e": "ₑ", "⇩h": "ₕ", "⇩i": "ᵢ", "⇩j": "ⱼ", "⇩k": "ₖ", "⇩l": "ₗ",
    "⇩m": "ₘ", "⇩n": "ₙ", "⇩o": "ₒ", "⇩p": "ₚ", "⇩r": "ᵣ", "⇩s": "ₛ", "⇩t": "ₜ",
    "⇩u": "ᵤ", "⇩v": "ᵥ", "⇩x": "ₓ",
    "⇧0": "⁰", "⇧1": "¹", "⇧2": "²", "⇧3": "³", "⇧4": "⁴",
    "⇧5": "⁵", "⇧6": "⁶", "⇧7": "⁷", "⇧8": "⁸", "⇧9": "⁹",
    "⇧A": "ᴬ", "⇧B": "ᴮ", "⇧D": "ᴰ", "⇧E": "ᴱ",
    "⇧G": "ᴳ", "⇧H": "ᴴ", "⇧I": "ᴵ", "⇧J": "ᴶ", "⇧K": "ᴷ", "⇧L": "ᴸ",
    "⇧M": "ᴹ", "⇧N": "ᴺ", "⇧O": "ᴼ", "⇧P": "ᴾ", "⇧R": "ᴿ", "⇧T": "ᵀ",
    "⇧U": "ᵁ", "⇧V": "ⱽ", "⇧W": "ᵂ",
    #ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖˢᵗᵘᵛʷˣʸᶻ
    "⇧a": "ᵃ", "⇧b": "ᵇ", "⇧c": "ᶜ", "⇧d": "ᵈ", "⇧e": "ᵉ", "⇧f": "ᶠ",
    "⇧g": "ᵍ", "⇧h": "ʰ", "⇧i": "ⁱ", "⇧j": "ʲ", "⇧k": "ᵏ", "⇧l": "ˡ",
    "⇧m": "ᵐ", "⇧n": "ⁿ", "⇧o": "ᵒ", "⇧p": "ᵖ", "⇧s": "ˢ", "⇧t": "ᵗ",
    "⇧u": "ᵘ", "⇧v": "ᵛ", "⇧w": "ʷ", "⇧x": "ˣ", "⇧y": "ʸ", "⇧z": "ᶻ",
    "⇩-": "₋", "⇧-": "⁻", "⇩+": "₊", "⇧+": "⁺", "⇩=": "₌", "⇧=": "⁼",
    "⇩(": "₍", "⇧(": "⁽", "⇩)": "₎", "⇧)": "⁾",
    "❙a": "𝐚", "❙b": "𝐛", "❙c": "𝐜", "❙d": "𝐝", "❙e": "𝐞", "❙f": "𝐟",
    "❙g": "𝐠", "❙h": "𝐡", "❙i": "𝐢", "❙j": "𝐣", "❙k": "𝐤", "❙l": "𝐥",
    "❙m": "𝐦", "❙n": "𝐧", "❙o": "𝐨", "❙p": "𝐩", "❙q": "𝐪", "❙r": "𝐫",
    "❙s": "𝐬", "❙t": "𝐭", "❙u": "𝐮", "❙v": "𝐯", "❙w": "𝐰", "❙x": "𝐱",
    "❙y": "𝐲", "❙z": "𝐳",
    "❙A": "𝐀", "❙B": "𝐁", "❙C": "𝐂", "❙D": "𝐃", "❙E": "𝐄", "❙F": "𝐅",
    "❙G": "𝐆", "❙H": "𝐇", "❙I": "𝐈", "❙J": "𝐉", "❙K": "𝐊", "❙L": "𝐋",
    "❙M": "𝐌", "❙N": "𝐍", "❙O": "𝐎", "❙P": "𝐏", "❙Q": "𝐐", "❙R": "𝐑",
    "❙S": "𝐒", "❙T": "𝐓", "❙U": "𝐔", "❙V": "𝐕", "❙W": "𝐖", "❙X": "𝐗",
    "❙Y": "𝐘", "❙Z": "𝐙",
}

# The fold's inverse. The forward table must stay injective, or one folded character
# would name two escapes; refuse to load rather than restore the wrong one.
SUBSUP_RESTORE_TABLE = {folded: pair for pair, folded in SUBSUP_TRANS_TABLE.items()}
if len(SUBSUP_RESTORE_TABLE) != len(SUBSUP_TRANS_TABLE):
    raise RuntimeError("SUBSUP_TRANS_TABLE folds two different pairs to one character")

SUBSUP_RESTORE_TABLE_trans = str.maketrans(SUBSUP_RESTORE_TABLE)


def is_private_use(ch):
    """Whether a character sits in one of Unicode's three Private Use Areas.

    Such a code point has no meaning of its own: it means whatever the font drawing it
    says, and nothing at all to anything else."""
    c = ord(ch)
    return 0xE000 <= c <= 0xF8FF or 0xF0000 <= c <= 0xFFFFD or 0x100000 <= c <= 0x10FFFD


# Isabelle's own rule for what names a symbol (Pure/General/symbol.scala): a letter,
# then letters, digits, `_` or `'`. A looser `\\<[^>]+>` scans to the next `>` wherever
# it falls, so one malformed escape swallows the next valid one -- `\<alpha \<beta>`
# converts nothing. Identical on well-formed input.
_ESCAPE = re.compile(r"\\<\^?[A-Za-z][A-Za-z0-9_']*>")
# A sub/superscript or bold marker (the fold table's own) and the character after it:
# the fold's candidates.
_MARKERS = re.escape(''.join(sorted({pair[0] for pair in SUBSUP_TRANS_TABLE})))
_FOLD = re.compile(f"[{_MARKERS}].")

# One match a replacement rewrote: its input span and its output length.
_Record = namedtuple('_Record', 'start end out_len')


def _sub_recording(pattern, replace, text):
    """`pattern.sub`, with `replace` called on the matched text rather than the match,
    and one record kept per match the replacement rewrote (ascending, non-overlapping)."""
    records = []

    def callback(match):
        out = replace(match.group(0))
        if out != match.group(0):
            records.append(_Record(match.start(), match.end(), len(out)))
        return out

    return pattern.sub(callback, text), records


def _replace_escape(symbol):
    char = _table().symbols.get(symbol)
    if char is None or is_private_use(char):
        return symbol
    return char


def _fold(pair):
    return SUBSUP_TRANS_TABLE.get(pair, pair)


def _render(text: str) -> tuple[str, tuple[list, list]]:
    """The rendering of `text` and the records of its two passes: escapes to characters,
    then the sub/superscript fold. The one place that decides what a symbol renders as;
    `pretty_unicode` and `pretty_unicode_indexed` are views of it."""
    mid, escapes = _sub_recording(_ESCAPE, _replace_escape, text)
    out, folds = _sub_recording(_FOLD, _fold, mid)
    return out, (escapes, folds)


def pretty_unicode(src: str) -> str:
    """
    Argument src: Any script that uses Isabelle's ASCII notation like `\\<Rightarrow>`
    Return: unicode version of `src`

    A symbol whose code point is private-use is left as its `\\<name>` escape. Its glyph
    exists only in the font that declares it (phi-System draws 135 keywords that way, at
    U+E000 upwards), so the code point would render as a blank box everywhere else,
    while the escape at least still spells the word. Note the asymmetry with
    `ascii_of_unicode`, which does convert such a character back to its name: text
    dragged out of jEdit carries the raw code point, and naming it is a repair.

    `pretty_unicode_indexed` is the same rendering with the position of every symbol.
    """
    return _render(src)[0]


def _map_offsets(records, offsets):
    """Where each of the ascending `offsets` into a pass's input lands in its output.

    Every offset moves with the length changes of the rewritten matches before it. One
    strictly inside a rewritten match lands at that match's output start: the match is
    one unit, so a fold operand shares the folded character's position."""
    mapped = []
    shift = 0                 # output minus input offset, in the text between matches
    k = 0
    for off in offsets:
        while k < len(records) and records[k].end <= off:
            done = records[k]
            shift += done.out_len - (done.end - done.start)
            k += 1
        here = records[k] if k < len(records) else None
        if here and here.start < off:
            mapped.append(here.start + shift)
        else:
            mapped.append(off + shift)
    return mapped


def pretty_unicode_indexed(symbols: list[str]) -> tuple[str, list[int]]:
    """The rendering of ''.join(symbols), and where each symbol begins in it.

    `symbols` is `symbol_explode`'s output, so the text rendered is the CR-folded one an
    index holds. `offsets` has len(symbols) + 1 entries, the last equal to the
    rendering's length; a fold operand shares the folded character's position with its
    marker (`_map_offsets`). Every `_ESCAPE` match must be exactly one of `symbols`:
    `symbol_explode` scans the same name more permissively, tolerating a missing `>`,
    and if that stopped holding the symbols inside a match would be placed at its start
    with no error.
    """
    rendered, (escapes, folds) = _render(''.join(symbols))
    starts = list(accumulate(map(len, symbols), initial=0))
    return rendered, _map_offsets(folds, _map_offsets(escapes, starts))

def unicode_of_ascii(src):
    return pretty_unicode(src)

def ascii_of_unicode(src):
    """
    Argument src: Any unicode string
    Return: Isabelle's ASCII version of `src`.
    This method is the reverse of `pretty_unicode`.
    """
    return src.translate(SUBSUP_RESTORE_TABLE_trans).translate(_table().trans)
