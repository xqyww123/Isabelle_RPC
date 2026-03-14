import os


class IsabellePosition:
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
