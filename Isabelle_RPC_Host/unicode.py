import os
import re


def _load_symbols(path, symbols={}, reverse_symbols={}, groups={}):
    """
    Load Isabelle symbol file
    Return: (ASCII-symbol -> unicode-symbol dict, the reverse dict, and an
             ASCII-symbol -> group dict from the `group:` field).
    """
    if not isinstance(path, str):
        raise ValueError("the argument path must be a string")
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

SYMBOLS_CACHE = None

def _resolve_isabelle_var(name):
    """Resolve an Isabelle settings variable.

    Prefer the process environment (which the ML launcher exports when it starts
    the RPC host), and only fall back to querying the `isabelle` executable —
    which is slow and, more importantly, silently yields "" when Isabelle failed
    to start or is not on PATH. Returns "" if neither source has a value.
    """
    value = os.environ.get(name)
    if value:
        return value
    try:
        return os.popen(f"isabelle getenv -b {name}").read().strip()
    except OSError:
        return ""

def get_SYMBOLS_AND_REVERSED():
    global SYMBOLS_CACHE
    if SYMBOLS_CACHE is not None:
        return SYMBOLS_CACHE
    isabelle_home = _resolve_isabelle_var("ISABELLE_HOME")
    isabelle_home_user = _resolve_isabelle_var("ISABELLE_HOME_USER")
    if not isabelle_home:
        raise RuntimeError(
            "Cannot locate Isabelle: ISABELLE_HOME is not set in the environment "
            "and the `isabelle` executable is unavailable (not on PATH, or it "
            "failed to start). The Isabelle symbol table is required for unicode "
            "conversion, so refusing to silently fall back to identity.")
    SYMBOLS, REVERSE_SYMBOLS, GROUPS = {}, {}, {}
    for file in [f"{isabelle_home}/etc/symbols", f"{isabelle_home_user}/etc/symbols"]:
        # System file first, user file second: the user file layers on top, so
        # a symbol (or its group) redefined in the user file overrides the system.
        SYMBOLS, REVERSE_SYMBOLS, GROUPS = _load_symbols(file, SYMBOLS, REVERSE_SYMBOLS, GROUPS)
    if not SYMBOLS:
        # ISABELLE_HOME resolved to a path, but its etc/symbols was missing,
        # unreadable, or empty (e.g. a relocated/partial install or a stale
        # exported value). Loading yielded an empty table, which would make
        # pretty_unicode silently degrade to identity — the exact regression we
        # refuse. Note: only the system table (ISABELLE_HOME) is required; a
        # missing user overlay (ISABELLE_HOME_USER) is fine and does not trip
        # this, since the system file alone already populates SYMBOLS.
        raise RuntimeError(
            f"Isabelle symbol table is empty: no symbols loaded from "
            f"{isabelle_home}/etc/symbols (file missing, unreadable, or empty). "
            "Refusing to silently fall back to identity conversion.")
    # Isabelle's identifier "letter" class (Symbol.is_letter_symbol, a hardcoded
    # list in Pure/General/symbol.ML) is a SUBSET of the symbols whose file group
    # is `letter` or `greek` — verified: every ML letter-symbol falls in one of
    # these two groups. Using the union is therefore a safe OVER-approximation:
    # it never rejects a legal identifier symbol (no harmful false positive), and
    # its only extras (blackboard-bold letters, \<lambda>) merely fail to flag a
    # would-be proposition, which the ML fact parser catches anyway.
    LETTER_SYMBOLS = frozenset(s for s, g in GROUPS.items() if g in ('letter', 'greek'))
    SYMBOLS_CACHE = (SYMBOLS, REVERSE_SYMBOLS, str.maketrans(REVERSE_SYMBOLS), LETTER_SYMBOLS)
    return SYMBOLS_CACHE

def get_SYMBOLS():
    return get_SYMBOLS_AND_REVERSED()[0]

def get_REVERSE_SYMBOLS():
    return get_SYMBOLS_AND_REVERSED()[1]

def get_LETTER_SYMBOLS():
    """The set of Isabelle symbols (as ASCII `\\<name>` strings) that may occur
    as a *letter* inside an identifier / fact name — a safe over-approximation
    of Symbol.is_letter_symbol (the file's `letter` and `greek` groups)."""
    return get_SYMBOLS_AND_REVERSED()[3]

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

SUBSUP_RESTORE_TABLE = {
    "₀": "⇩0", "₁": "⇩1", "₂": "⇩2", "₃": "⇩3", "₄": "⇩4",
    "₅": "⇩5", "₆": "⇩6", "₇": "⇩7", "₈": "⇩8", "₉": "⇩9",
    "ₐ": "⇩a", "ₑ": "⇩e", "ₕ": "⇩h", "ᵢ": "⇩i", "ⱼ": "⇩j", "ₖ": "⇩k", "ₗ": "⇩l",
    "ₘ": "⇩m", "ₙ": "⇩n", "ₒ": "⇩o", "ₚ": "⇩p", "ᵣ": "⇩r", "ₛ": "⇩s", "ₜ": "⇩t",
    "ᵤ": "⇩u", "ᵥ": "⇩v", "ₓ": "⇩x",
    "⁰": "⇧0", "¹": "⇧1", "²": "⇧2", "³": "⇧3", "⁴": "⇧4",
    "⁵": "⇧5", "⁶": "⇧6", "⁷": "⇧7", "⁸": "⇧8", "⁹": "⇧9",
    "ᴬ": "⇧A", "ᴮ": "⇧B", "ᴰ": "⇧D", "ᴱ": "⇧E", "ᴳ": "⇧G", "ᴴ": "⇧H", "ᴵ": "⇧I",
    "ᴶ": "⇧J", "ᴷ": "⇧K", "ᴸ": "⇧L", "ᴹ": "⇧M", "ᴺ": "⇧N", "ᴼ": "⇧O", "ᴾ": "⇧P",
    "ᴿ": "⇧R", "ᵀ": "⇧T", "ᵁ": "⇧U", "ⱽ": "⇧V", "ᵂ": "⇧W",
    "ᵃ": "⇧a", "ᵇ": "⇧b", "ᶜ": "⇧c", "ᵈ": "⇧d", "ᵉ": "⇧e", "ᶠ": "⇧f",
    "ᵍ": "⇧g", "ʰ": "⇧h", "ⁱ": "⇧i", "ʲ": "⇧j", "ᵏ": "⇧k", "ˡ": "⇧l",
    "ᵐ": "⇧m", "ⁿ": "⇧n", "ᵒ": "⇧o", "ᵖ": "⇧p", "ˢ": "⇧s", "ᵗ": "⇧t",
    "ᵘ": "⇧u", "ᵛ": "⇧v", "ʷ": "⇧w", "ˣ": "⇧x", "ʸ": "⇧y", "ᶻ": "⇧z",
    "₋": "⇩-", "⁻": "⇧-", "₊": "⇩+", "⁺": "⇧+", "₌": "⇩=", "⁼": "⇧=",
    "₍": "⇩(", "⁽": "⇧(", "₎": "⇩)", "⁾": "⇧)",
    "𝐚": "❙a", "𝐛": "❙b", "𝐜": "❙c", "𝐝": "❙d", "𝐞": "❙e", "𝐟": "❙f",
    "𝐠": "❙g", "𝐡": "❙h", "𝐢": "❙i", "𝐣": "❙j", "𝐤": "❙k", "𝐥": "❙l",
    "𝐦": "❙m", "𝐧": "❙n", "𝐨": "❙o", "𝐩": "❙p", "𝐪": "❙q", "𝐫": "❙r",
    "𝐬": "❙s", "𝐭": "❙t", "𝐮": "❙u", "𝐯": "❙v", "𝐰": "❙w", "𝐱": "❙x",
    "𝐲": "❙y", "𝐳": "❙z",
    "𝐀": "❙A", "𝐁": "❙B", "𝐂": "❙C", "𝐃": "❙D", "𝐄": "❙E", "𝐅": "❙F",
    "𝐆": "❙G", "𝐇": "❙H", "𝐈": "❙I", "𝐉": "❙J", "𝐊": "❙K", "𝐋": "❙L",
    "𝐌": "❙M", "𝐍": "❙N", "𝐎": "❙O", "𝐏": "❙P", "𝐐": "❙Q", "𝐑": "❙R",
    "𝐒": "❙S", "𝐓": "❙T", "𝐔": "❙U", "𝐕": "❙V", "𝐖": "❙W", "𝐗": "❙X",
    "𝐘": "❙Y", "𝐙": "❙Z",
}

SUBSUP_RESTORE_TABLE_trans = str.maketrans(SUBSUP_RESTORE_TABLE)


def pretty_unicode(src):
    """
    Argument src: Any script that uses Isabelle's ASCII notation like `\\<Rightarrow>`
    Return: unicode version of `src`
    """
    pattern = r'\\<[^>]+>'
    subscript_pattern = r'⇩.|⇧.|❙.'

    def replace_symbol(match):
        symbol = match.group(0)
        return get_SYMBOLS().get(symbol, symbol)

    def replace_subsupscript(match):
        symbol = match.group(0)
        if symbol in SUBSUP_TRANS_TABLE:
            return SUBSUP_TRANS_TABLE[symbol]
        return symbol

    return re.sub(subscript_pattern, replace_subsupscript, re.sub(pattern, replace_symbol, src))

def unicode_of_ascii(src):
    return pretty_unicode(src)

def ascii_of_unicode(src):
    """
    Argument src: Any unicode string
    Return: Isabelle's ASCII version of `src`.
    This method is the reverse of `pretty_unicode`.
    """
    trans_table = get_SYMBOLS_AND_REVERSED()[2]
    return src.translate(SUBSUP_RESTORE_TABLE_trans).translate(trans_table)
