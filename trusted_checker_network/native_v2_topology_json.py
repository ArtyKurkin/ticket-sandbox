"""Bounded topology JSON scanner; decimals remain exact tokens, never floats."""
from dataclasses import dataclass
import re
from .native_v2_contracts import ContractViolation2

MAX_BYTES = 1048576
MAX_DEPTH = 32
MAX_NODES = 65536
MAX_ROWS = 1024
MAX_ARRAY = 1024
MAX_STRING_BYTES = 512


@dataclass(frozen=True, slots=True)
class ExactDecimal2:
    """Unsigned fixed-point token, bounded digits/scale; preserves trailing zeros."""
    token: str

    def __post_init__(self):
        if type(self.token) is not str or re.fullmatch(r'[0-9]{1,10}\.[0-9]{1,6}', self.token) is None:
            _fail('v2_topology_decimal_invalid')
        if len(self.token.split('.')[0]) > 1 and self.token[0] == '0':
            _fail('v2_topology_decimal_invalid')

    @property
    def millionths(self):
        whole, fraction = self.token.split('.')
        return int(whole) * 1000000 + int(fraction.ljust(6, '0'))


def _fail(reason='v2_topology_json_invalid'):
    raise ContractViolation2(reason)


class _Parser:
    def __init__(self, text):
        self.text, self.at, self.nodes = text, 0, 0

    def count(self):
        if self.nodes >= MAX_NODES:
            _fail('v2_topology_json_nodes_limit')
        self.nodes += 1

    def whitespace(self):
        while self.at < len(self.text) and self.text[self.at] in ' \t\r\n':
            self.at += 1

    def take(self, char):
        self.whitespace()
        if self.at >= len(self.text) or self.text[self.at] != char:
            _fail()
        self.at += 1

    def string(self):
        self.take('"')
        chars, size = [], 0
        escapes = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
        while self.at < len(self.text):
            ch = self.text[self.at]
            self.at += 1
            if ch == '"':
                return ''.join(chars)
            if ord(ch) < 32:
                _fail()
            if ch == '\\':
                if self.at >= len(self.text):
                    _fail()
                code = self.text[self.at]
                self.at += 1
                if code == 'u':
                    value = self.hex4()
                    if 0xD800 <= value <= 0xDBFF:
                        if self.text[self.at:self.at + 2] != '\\u':
                            _fail()
                        self.at += 2
                        low = self.hex4()
                        if not 0xDC00 <= low <= 0xDFFF:
                            _fail()
                        value = 0x10000 + (value - 0xD800) * 1024 + low - 0xDC00
                    elif 0xDC00 <= value <= 0xDFFF:
                        _fail()
                    ch = chr(value)
                elif code in escapes:
                    ch = escapes[code]
                else:
                    _fail()
            size += len(ch.encode('utf-8'))
            if size > MAX_STRING_BYTES:
                _fail('v2_topology_json_string_limit')
            chars.append(ch)  # Bound is checked before retaining the character.
        _fail()

    def hex4(self):
        token = self.text[self.at:self.at + 4]
        if len(token) != 4 or any(ch not in '0123456789abcdefABCDEF' for ch in token):
            _fail()
        self.at += 4
        return int(token, 16)

    def number(self):
        start = self.at
        if self.text[self.at] == '-':
            self.at += 1
        digits = self.at
        while self.at < len(self.text) and '0' <= self.text[self.at] <= '9':
            self.at += 1
            if self.at - digits > 19:
                _fail('v2_topology_json_integer_invalid')
        if self.at == digits or (self.at - digits > 1 and self.text[digits] == '0'):
            _fail()
        if self.at < len(self.text) and self.text[self.at] == '.':
            self.at += 1
            fraction = self.at
            while self.at < len(self.text) and '0' <= self.text[self.at] <= '9':
                self.at += 1
                if self.at - fraction > 6:
                    _fail('v2_topology_decimal_invalid')
            value = ExactDecimal2(self.text[start:self.at])
            if self.at < len(self.text) and self.text[self.at] in 'eE':
                _fail('v2_topology_decimal_invalid')
            return value
        if self.at < len(self.text) and self.text[self.at] in 'eE':
            _fail('v2_topology_decimal_invalid')
        value = int(self.text[start:self.at])
        if not -(2**63) <= value <= 2**63 - 1:
            _fail('v2_topology_json_integer_invalid')
        return value

    def value(self, depth=1, path=()):
        if depth > MAX_DEPTH:
            _fail('v2_topology_json_depth_limit')
        self.count()  # Values, containers and object keys each consume one node.
        self.whitespace()
        if self.at >= len(self.text):
            _fail()
        ch = self.text[self.at]
        if ch == '"':
            return self.string()
        if ch == '{':
            self.at += 1
            result = {}
            self.whitespace()
            if self.at < len(self.text) and self.text[self.at] == '}':
                self.at += 1
                return result
            while True:
                self.count()
                key = self.string()
                if key in result:
                    _fail('v2_topology_json_duplicate_key')
                self.take(':')
                result[key] = self.value(depth + 1, path + (key,))
                self.whitespace()
                if self.at < len(self.text) and self.text[self.at] == '}':
                    self.at += 1
                    return result
                self.take(',')
        if ch == '[':
            self.at += 1
            result = []
            limit = MAX_ROWS if not path else MAX_ARRAY
            self.whitespace()
            if self.at < len(self.text) and self.text[self.at] == ']':
                self.at += 1
                return result
            while True:
                if len(result) >= limit:
                    _fail('v2_topology_json_array_limit')
                result.append(self.value(depth + 1, path + (len(result),)))
                self.whitespace()
                if self.at < len(self.text) and self.text[self.at] == ']':
                    self.at += 1
                    return result
                self.take(',')
        if ch == '-' or '0' <= ch <= '9':
            return self.number()
        if self.text.startswith('null', self.at):
            self.at += 4
            return None
        for token, value in (('true', True), ('false', False)):
            if self.text.startswith(token, self.at):
                self.at += len(token)
                return value
        if self.text.startswith(('NaN', 'Infinity', '-Infinity'), self.at):
            _fail('v2_topology_json_integer_invalid')
        _fail()


def bounded_topology_json2(raw):
    """Exact bytes only; check size before UTF-8 decoding and tree allocation.

    At most MAX_BYTES of input text is decoded. Containers/nodes, strings and
    integer tokens are bounded before their potentially large allocations.
    These bounds apply to this parser's work, not memory already held by caller.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail('v2_topology_json_size_invalid')
    if raw.startswith(b'\xef\xbb\xbf'):
        _fail('v2_topology_json_encoding_invalid')
    try:
        text = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        _fail('v2_topology_json_encoding_invalid')
    parser = _Parser(text)
    result = parser.value()
    parser.whitespace()
    if parser.at != len(text):
        _fail()
    return result
