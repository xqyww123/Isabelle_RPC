import bisect
import os
from array import array
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rpc import Connection


# ---------------------------------------------------------------------------
# Symbol explode
# ---------------------------------------------------------------------------

def symbol_explode(text: str) -> list[str]:
    """Split a string into Isabelle symbols.

    Port of Pure/General/symbol_explode.ML. Purely static — no configuration
    or context needed. Handles:
    - ``\\r\\n`` / ``\\r`` → ``\\n`` (CR normalization)
    - Named symbols ``\\<name>`` and ``\\<^name>`` as single symbols
    - All other characters as individual symbols

    Since Python strings are already decoded Unicode (not raw bytes), UTF-8
    multi-byte sequences are already single characters and need no special handling.
    """
    result: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # CR normalization: \r\n -> \n, bare \r -> \n
        if ch == '\r':
            result.append('\n')
            if i + 1 < n and text[i + 1] == '\n':
                i += 2
            else:
                i += 1
        # Named symbol: \<...>
        elif ch == '\\' and i + 1 < n and text[i + 1] == '<':
            j = i + 2
            # optional ^ for control symbols
            if j < n and text[j] == '^':
                j += 1
            # ASCII identifier
            if j < n and text[j].isascii() and text[j].isalpha():
                j += 1
                while j < n and (text[j].isascii() and (text[j].isalnum() or text[j] in "_'")):
                    j += 1
            # optional closing >
            if j < n and text[j] == '>':
                j += 1
            result.append(text[i:j])
            i = j
        # Single character (includes decoded Unicode like α, ⇒, etc.)
        else:
            result.append(ch)
            i += 1
    return result


# ---------------------------------------------------------------------------
# File index: compact arrays for efficient position conversion
# ---------------------------------------------------------------------------

class FileIndex:
    """Compact index arrays for converting between position coordinate systems.

    Built once per file from ``symbol_explode(source)``. Cached and invalidated
    on file modification.

    Arrays (all ``array.array('I')``):
    - ``sym_ascii_offsets[i]``: char offset in source where symbol *i* starts
      (0-based symbols). Length = num_symbols + 1 (sentinel = source length).
    - ``sym_unicode_offsets[i]``: char offset in rendered unicode string where
      symbol *i* starts. Length = num_symbols + 1 (sentinel = unicode length).
    - ``ascii_line_offsets[i]``: char offset in source where line *i+1* starts.
    """

    __slots__ = ('sym_ascii_offsets', 'sym_unicode_offsets', 'ascii_line_offsets')

    def __init__(self, source: str):
        from .unicode import get_SYMBOLS, SUBSUP_TRANS_TABLE

        SYMBOLS = get_SYMBOLS()
        symbols = symbol_explode(source)
        n = len(symbols)

        sym_ascii = array('I')
        sym_unicode = array('I')
        ascii_lines = array('I')

        ascii_off = 0
        unicode_off = 0
        ascii_lines.append(0)

        i = 0
        while i < n:
            sym = symbols[i]
            sym_ascii.append(ascii_off)
            sym_unicode.append(unicode_off)

            # Compute unicode representation of this symbol
            if sym.startswith('\\<'):
                uni = SYMBOLS.get(sym, sym)
            else:
                uni = sym
            uni_len = len(uni)

            # Check for sub/superscript merging: modifier + next → 1 char
            if uni_len == 1 and uni in '\u21e9\u21e7\u2759' and i + 1 < n:
                # ⇩ = \u21e9 (subscript), ⇧ = \u21e7 (superscript), ❙ = \u2759 (bold)
                next_sym = symbols[i + 1]
                if next_sym.startswith('\\<'):
                    next_uni = SYMBOLS.get(next_sym, next_sym)
                else:
                    next_uni = next_sym
                combined = uni + next_uni
                if len(next_uni) == 1 and combined in SUBSUP_TRANS_TABLE:
                    # Modifier symbol: unicode width 0
                    ascii_off += len(sym)
                    if sym == '\n':
                        ascii_lines.append(ascii_off)
                    i += 1
                    # Operand symbol: carries the merged char (unicode width 1)
                    sym_ascii.append(ascii_off)
                    sym_unicode.append(unicode_off)
                    ascii_off += len(next_sym)
                    unicode_off += 1
                    if next_sym == '\n':
                        ascii_lines.append(ascii_off)
                    i += 1
                    continue

            ascii_off += len(sym)
            unicode_off += uni_len

            if sym == '\n':
                ascii_lines.append(ascii_off)

            i += 1

        # Sentinels
        sym_ascii.append(ascii_off)
        sym_unicode.append(unicode_off)

        self.sym_ascii_offsets = sym_ascii
        self.sym_unicode_offsets = sym_unicode
        self.ascii_line_offsets = ascii_lines

    @property
    def num_symbols(self) -> int:
        return len(self.sym_ascii_offsets) - 1

    @property
    def num_lines(self) -> int:
        return len(self.ascii_line_offsets)

    # --- helpers ---

    def _line_of_ascii(self, ascii_offset: int) -> int:
        """Return 1-based line number for an ascii char offset."""
        return bisect.bisect_right(self.ascii_line_offsets, ascii_offset)

    def _line_start_unicode(self, line: int) -> int:
        """Return unicode char offset at the start of 1-based line."""
        ascii_start = self.ascii_line_offsets[line - 1]
        sym_idx = bisect.bisect_right(self.sym_ascii_offsets, ascii_start) - 1
        return self.sym_unicode_offsets[sym_idx]

    # --- 6 conversions ---

    def isabelle_to_ascii(self, raw_offset: int) -> tuple[int, int]:
        """Symbol offset (1-based) → (line, column) in ASCII source."""
        idx = min(raw_offset - 1, self.num_symbols)
        ascii_off = self.sym_ascii_offsets[idx]
        line = self._line_of_ascii(ascii_off)
        col = ascii_off - self.ascii_line_offsets[line - 1] + 1
        return (line, col)

    def isabelle_to_unicode(self, raw_offset: int) -> tuple[int, int]:
        """Symbol offset (1-based) → (line, column) in rendered Unicode."""
        idx = min(raw_offset - 1, self.num_symbols)
        ascii_off = self.sym_ascii_offsets[idx]
        line = self._line_of_ascii(ascii_off)
        unicode_off = self.sym_unicode_offsets[idx]
        line_start_uni = self._line_start_unicode(line)
        col = unicode_off - line_start_uni + 1
        return (line, col)

    def ascii_to_isabelle(self, line: int, column: int) -> int:
        """(line, column) in ASCII source → symbol offset (1-based)."""
        if line < 1 or line > self.num_lines:
            return 0
        ascii_off = self.ascii_line_offsets[line - 1] + column - 1
        return bisect.bisect_right(self.sym_ascii_offsets, ascii_off)

    def unicode_to_isabelle(self, line: int, column: int) -> int:
        """(line, column) in rendered Unicode → symbol offset (1-based)."""
        if line < 1 or line > self.num_lines:
            return 0
        line_start_uni = self._line_start_unicode(line)
        unicode_off = line_start_uni + column - 1
        return bisect.bisect_right(self.sym_unicode_offsets, unicode_off)

    def ascii_to_unicode(self, line: int, column: int) -> tuple[int, int]:
        """(line, column) in ASCII → (line, column) in Unicode."""
        if line < 1 or line > self.num_lines:
            return (line, column)
        ascii_off = self.ascii_line_offsets[line - 1] + column - 1
        sym_idx = bisect.bisect_right(self.sym_ascii_offsets, ascii_off) - 1
        unicode_off = self.sym_unicode_offsets[sym_idx]
        line_start_uni = self._line_start_unicode(line)
        col_u = unicode_off - line_start_uni + 1
        return (line, col_u)

    def unicode_to_ascii(self, line: int, column: int) -> tuple[int, int]:
        """(line, column) in Unicode → (line, column) in ASCII."""
        if line < 1 or line > self.num_lines:
            return (line, column)
        line_start_uni = self._line_start_unicode(line)
        unicode_off = line_start_uni + column - 1
        sym_idx = bisect.bisect_right(self.sym_unicode_offsets, unicode_off) - 1
        ascii_off = self.sym_ascii_offsets[sym_idx]
        line_start_ascii = self.ascii_line_offsets[line - 1]
        col_a = ascii_off - line_start_ascii + 1
        return (line, col_a)


# ---------------------------------------------------------------------------
# File index cache with file watcher invalidation
# ---------------------------------------------------------------------------

_file_index_cache: dict[str, FileIndex] = {}

from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch
from watchdog.events import FileSystemEventHandler


class _CacheInvalidator(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and isinstance(event.src_path, str):
            path = os.path.realpath(event.src_path)
            _file_index_cache.pop(path, None)

_observer = Observer()
_observer.daemon = True
_invalidator = _CacheInvalidator()
_watched_dirs: OrderedDict[str, ObservedWatch] = OrderedDict()
_MAX_WATCHED_DIRS = 64


def _ensure_watching(file_path: str):
    dir_path = os.path.dirname(file_path)
    if dir_path in _watched_dirs:
        _watched_dirs.move_to_end(dir_path)
        return
    if len(_watched_dirs) >= _MAX_WATCHED_DIRS:
        evicted_dir, watch = _watched_dirs.popitem(last=False)
        _observer.unschedule(watch)
        prefix = evicted_dir + os.sep
        for path in [p for p in _file_index_cache if p.startswith(prefix)]:
            del _file_index_cache[path]
    watch = _observer.schedule(_invalidator, dir_path, recursive=False)
    _watched_dirs[dir_path] = watch
    if not _observer.is_alive():
        _observer.start()


def get_file_index(file_path: str) -> FileIndex:
    """Get or build the FileIndex for a file (cached, invalidated on modification)."""
    real_path = os.path.realpath(file_path)
    idx = _file_index_cache.get(real_path)
    if idx is not None:
        return idx
    with open(real_path, 'r', encoding='utf-8') as f:
        source = f.read()
    idx = FileIndex(source)
    _file_index_cache[real_path] = idx
    _ensure_watching(real_path)
    return idx


# ---------------------------------------------------------------------------
# IsabellePosition: offset-based (symbol offset, 1-based)
# ---------------------------------------------------------------------------

class IsabellePosition:
    """ Based on Isabelle's symbol offset
    """
    def __init__(self, line : int, raw_offset : int, file : str):
        self.line = line
        self.raw_offset = raw_offset
        self.file = file

    def __str__(self):
        return f"{self.file}:{self.line}:{self.raw_offset}"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, IsabellePosition):
            return False
        return (self.line == other.line and
                self.raw_offset == other.raw_offset and
                self.file == other.file)

    def __hash__(self):
        return hash((self.line, self.raw_offset, self.file))

    def __lt__(self, other):
        if not isinstance(other, IsabellePosition):
            return NotImplemented
        return (self.file, self.line, self.raw_offset) < (other.file, other.line, other.raw_offset)

    def __le__(self, other):
        if not isinstance(other, IsabellePosition):
            return NotImplemented
        return (self.file, self.line, self.raw_offset) <= (other.file, other.line, other.raw_offset)

    def __gt__(self, other):
        if not isinstance(other, IsabellePosition):
            return NotImplemented
        return (self.file, self.line, self.raw_offset) > (other.file, other.line, other.raw_offset)

    def __ge__(self, other):
        if not isinstance(other, IsabellePosition):
            return NotImplemented
        return (self.file, self.line, self.raw_offset) >= (other.file, other.line, other.raw_offset)

    @staticmethod
    def from_s(position_str):
        parts = position_str.split(':')
        match parts:
            case [file, line, raw_offset, _]:
                return IsabellePosition(int(line), int(raw_offset), file)
            case [file, line, raw_offset]:
                return IsabellePosition(int(line), int(raw_offset), file)
            case [file, line]:
                return IsabellePosition(int(line), 0, file)
            case [file]:
                return IsabellePosition(0, 0, file)
            case _:
                raise ValueError("The string must be in the format: file:line:raw_offset")

    @staticmethod
    def unpack(data):
        line, offset, end_offset, tup3 = data
        label, file, id = tup3
        return IsabellePosition(line, offset, file)

    def pack(self):
        return (self.line, self.raw_offset, 0, (b'', self.file, 0))

    def to_ascii_position(self) -> "AsciiPosition":
        idx = get_file_index(self.file)
        line, col = idx.isabelle_to_ascii(self.raw_offset)
        return AsciiPosition(line, col, self.file)

    def to_unicode_position(self) -> "UnicodePosition":
        idx = get_file_index(self.file)
        line, col = idx.isabelle_to_unicode(self.raw_offset)
        return UnicodePosition(line, col, self.file)

    # backward compat
    def to_position(self, connection: "Connection | None" = None) -> "AsciiPosition":
        return self.to_ascii_position()


# ---------------------------------------------------------------------------
# Position: column-based (line + column, 1-based)
# ---------------------------------------------------------------------------

class Position:
    def __init__(self, line : int, column : int, file : str):
        self.line = line
        self.column = column
        self.file = file

    def to_s(self, with_column=True):
        if with_column:
            return self.__str__()
        else:
            return f"{self.file}:{self.line}"

    def __str__(self):
        if self.column == 0:
            return f"{self.file}:{self.line}"
        else:
            return f"{self.file}:{self.line}:{self.column}"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, Position):
            return False
        return (self.line == other.line and
                self.column == other.column and
                self.file == other.file)

    def __hash__(self):
        return hash((self.line, self.column, self.file))

    def __lt__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return (self.file, self.line, self.column) < (other.file, other.line, other.column)

    def __le__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return (self.file, self.line, self.column) <= (other.file, other.line, other.column)

    def __gt__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return (self.file, self.line, self.column) > (other.file, other.line, other.column)

    def __ge__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return (self.file, self.line, self.column) >= (other.file, other.line, other.column)

    @staticmethod
    def from_s(position_str):
        parts = position_str.split(':')
        match parts:
            case [file, line, column, _]:
                return Position(int(line), int(column), file)
            case [file, line, column]:
                return Position(int(line), int(column), file)
            case [file, line]:
                return Position(int(line), 0, file)
            case [file]:
                return Position(0, 0, file)
            case _:
                raise ValueError("The string must be in the format: file:line:column")

    def offset_of(self, lines=None):
        if lines is None:
            with open(self.file, 'r', encoding="latin-1") as f:
                lines = f.readlines()
        base_ofs = sum(len(line) for line in lines[:self.line-1])
        return base_ofs + self.column - 1

    @staticmethod
    def unpack(data):
        line, column, end_offset, tup3 = data
        label, file, id = tup3
        return Position(line, column, file)

    def pack(self):
        return (self.line, self.column, 0, (b'', self.file, 0))


class AsciiPosition(Position):
    def to_isabelle_position(self, connection: "Connection | None" = None) -> IsabellePosition:
        idx = get_file_index(self.file)
        raw_offset = idx.ascii_to_isabelle(self.line, self.column)
        return IsabellePosition(self.line, raw_offset, self.file)

    def to_unicode_position(self) -> "UnicodePosition":
        idx = get_file_index(self.file)
        line, col = idx.ascii_to_unicode(self.line, self.column)
        return UnicodePosition(line, col, self.file)


class UnicodePosition(Position):
    def to_isabelle_position(self, connection: "Connection | None" = None) -> IsabellePosition:
        idx = get_file_index(self.file)
        raw_offset = idx.unicode_to_isabelle(self.line, self.column)
        return IsabellePosition(self.line, raw_offset, self.file)

    def to_ascii_position(self) -> AsciiPosition:
        idx = get_file_index(self.file)
        line, col = idx.unicode_to_ascii(self.line, self.column)
        return AsciiPosition(line, col, self.file)


# ---------------------------------------------------------------------------
# RPC procedures (called from Isabelle/ML)
# ---------------------------------------------------------------------------

from .rpc import isabelle_remote_procedure, Connection


@isabelle_remote_procedure("position.offset_to_line_column")
async def _offset_to_line_column(arg: tuple, connection: Connection):
    """Given (file_path, offset), return (line, column) in ASCII coordinates."""
    file_path, offset = arg
    if isinstance(file_path, bytes):
        file_path = file_path.decode('utf-8')
    pos = IsabellePosition(0, offset, file_path)
    result = pos.to_ascii_position()
    return (result.line, result.column)


@isabelle_remote_procedure("position.line_column_to_offset")
async def _line_column_to_offset(arg: tuple, connection: Connection):
    """Given (file_path, line, column), return symbol offset."""
    file_path, line, column = arg
    if isinstance(file_path, bytes):
        file_path = file_path.decode('utf-8')
    pos = AsciiPosition(line, column, file_path)
    result = pos.to_isabelle_position()
    return result.raw_offset
