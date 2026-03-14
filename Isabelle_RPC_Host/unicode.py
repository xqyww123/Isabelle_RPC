import os
import re


def _load_symbols(path, symbols={}, reverse_symbols={}):
    """
    Load Isabelle symbol file
    Return: (A dictionary from ASCII symbol to unicode symbol, and the reverse dictionary)
    """
    if not isinstance(path, str):
        raise ValueError("the argument path must be a string")
    if not os.path.exists(path):
        return symbols, reverse_symbols
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            # Every line has a form like `\<odiv>            code: 0x002A38   font: PhiSymbols   group: operator   abbrev: (-:)`
            # Here we extract the `\<odiv>` part as a string and the `0x002A38` part as a character
            # Skip comments and empty lines
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Parse the line to extract symbol and code point
            parts = line.split()

            # Extract the symbol name (like \<odiv>)
            symbol = parts[0]

            # Find the code point (format can be either "code: 0x002A38" or "code:0x002A38")
            code_point = None
            for i, part in enumerate(parts[1:], 1):  # Start index at 1 since we're iterating from parts[1:]
                if part.startswith('code:'):
                    # Handle the case where there's no space after "code:"
                    if ':' in part and len(part) > 5:  # "code:" is 5 chars
                        code_point = part.split(':', 1)[1].strip()
                    # Otherwise, the hex value should be in the next part
                    elif i < len(parts) - 1:  # Check if there's a next element
                        code_point = parts[i + 1].strip()
                    break

            if symbol and code_point:
                try:
                    # Convert hex code point to unicode character
                    unicode_char = chr(int(code_point, 16))
                    # Add to dictionaries
                    symbols[symbol] = unicode_char
                    reverse_symbols[unicode_char] = symbol
                except ValueError:
                    # Skip if code point is invalid
                    continue
    return symbols, reverse_symbols

SYMBOLS_CACHE = None

def get_SYMBOLS_AND_REVERSED():
    global SYMBOLS_CACHE
    if SYMBOLS_CACHE is not None:
        return SYMBOLS_CACHE
    isabelle_home = os.popen("isabelle getenv -b ISABELLE_HOME").read().strip()
    isabelle_home_user = os.popen("isabelle getenv -b ISABELLE_HOME_USER").read().strip()
    SYMBOLS, REVERSE_SYMBOLS = {}, {}
    for file in [f"{isabelle_home}/etc/symbols", f"{isabelle_home_user}/etc/symbols"]:
        SYMBOLS, REVERSE_SYMBOLS = _load_symbols(file, SYMBOLS, REVERSE_SYMBOLS)
    SYMBOLS_CACHE = (SYMBOLS, REVERSE_SYMBOLS, str.maketrans(REVERSE_SYMBOLS))
    return SYMBOLS_CACHE

def get_SYMBOLS():
    return get_SYMBOLS_AND_REVERSED()[0]

def get_REVERSE_SYMBOLS():
    return get_SYMBOLS_AND_REVERSED()[1]

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
