"""Isabelle tokenizer and symbol occurrence finder.

Implements a simplified Isabelle lexer based on ``symbol_pos.ML`` and
``lexicon.ML``, operating in ASCII space (so ``\\<forall>`` and the rendered
``∀`` are equivalent). Used to locate a *named symbol* on a source line so
callers never have to count columns.

Reuses :func:`Isabelle_RPC_Host.unicode.symbol_explode` and
:func:`Isabelle_RPC_Host.unicode.ascii_of_unicode`.
"""

from .unicode import (
    _is_digit, _is_letdig, _is_letter, _is_sub, _scan_ident_tail, ascii_of_unicode, symbol_explode)

def _is_blank(sym: str) -> bool:
    return sym in (" ", "\t", "\n", "\x0b", "\f", "\r")


def tokenize_isabelle_line(ascii_text: str) -> list[tuple[str, int, int]]:
    """Tokenize Isabelle ASCII text into (token_text, ascii_offset, symbol_index) triples."""
    symbols = symbol_explode(ascii_text)

    offsets: list[int] = []
    off = 0
    for sym in symbols:
        offsets.append(off)
        off += len(sym)

    tokens: list[tuple[str, int, int]] = []
    pos = 0
    n = len(symbols)

    while pos < n:
        sym = symbols[pos]

        # Skip (* ... *) comments (nestable). Their free text holds no PIDE
        # entities, so matching a token inside one would be a spurious hit.
        # NOTE: strings ("...") and cartouches (\<open>..\<close> / ‹..›) are
        # intentionally NOT skipped — their inner syntax carries the very
        # entities a hover/definition lookup targets.
        if sym == '(' and pos + 1 < n and symbols[pos + 1] == '*':
            depth = 1
            pos += 2
            while pos < n and depth > 0:
                if symbols[pos] == '(' and pos + 1 < n and symbols[pos + 1] == '*':
                    depth += 1
                    pos += 2
                elif symbols[pos] == '*' and pos + 1 < n and symbols[pos + 1] == ')':
                    depth -= 1
                    pos += 2
                else:
                    pos += 1
            continue

        if _is_blank(sym):
            pos += 1
            continue

        if _is_letter(sym):
            start = pos
            pos = _scan_ident_tail(symbols, pos + 1)
            while (
                pos < n
                and symbols[pos] == "."
                and pos + 1 < n
                and _is_letter(symbols[pos + 1])
            ):
                pos = _scan_ident_tail(symbols, pos + 2)
            tokens.append(("".join(symbols[start:pos]), offsets[start], start))
            continue

        if sym == "'" and pos + 1 < n and _is_letter(symbols[pos + 1]):
            start = pos
            pos = _scan_ident_tail(symbols, pos + 2)
            tokens.append(("".join(symbols[start:pos]), offsets[start], start))
            continue

        if sym == "?" and pos + 1 < n:
            next_sym = symbols[pos + 1]
            if _is_letter(next_sym) or (
                next_sym == "'" and pos + 2 < n and _is_letter(symbols[pos + 2])
            ):
                start = pos
                pos += 1
                if symbols[pos] == "'":
                    pos += 1
                pos = _scan_ident_tail(symbols, pos + 1)
                if (
                    pos < n
                    and symbols[pos] == "."
                    and pos + 1 < n
                    and _is_digit(symbols[pos + 1])
                ):
                    pos += 1
                    while pos < n and _is_digit(symbols[pos]):
                        pos += 1
                tokens.append(("".join(symbols[start:pos]), offsets[start], start))
                continue

        if _is_digit(sym):
            start = pos
            while pos < n and _is_digit(symbols[pos]):
                pos += 1
            tokens.append(("".join(symbols[start:pos]), offsets[start], start))
            continue

        tokens.append((sym, offsets[pos], pos))
        pos += 1

    return tokens


def find_symbol_token_indices(text: str, symbol: str) -> list[int]:
    """Find all token-level occurrences of ``symbol`` in ``text``.

    Returns the 0-based **symbol index** (into ``symbol_explode(text)``) of each
    matched occurrence's first token, in source order. No cap — the caller
    decides truncation.

    ``text`` MUST already be in Isabelle symbol-escape form (e.g. ``\\<forall>``,
    as produced by ``command_at_position`` / ``FileIndex.ascii_line``); it is
    tokenized directly, so the returned indices live in the same symbol space as
    Isabelle ``raw_offset``s (a caller can add a command/line symbol base to get
    a file-global offset). Only the target ``symbol`` is normalized via
    ``ascii_of_unicode``, so it may be passed in ASCII or Unicode. Matching is on
    Isabelle token boundaries (``x`` does not match inside ``xs``).
    """
    line_tokens = tokenize_isabelle_line(text)
    target_tokens = tokenize_isabelle_line(ascii_of_unicode(symbol))
    if not target_tokens or not line_tokens:
        return []

    target_texts = [t[0] for t in target_tokens]
    target_len = len(target_texts)
    results: list[int] = []
    for i in range(len(line_tokens) - target_len + 1):
        if all(line_tokens[i + j][0] == target_texts[j] for j in range(target_len)):
            results.append(line_tokens[i][2])
    return results
