"""Bounded JSON tokenizer/parser for offline nft v2, not a host read surface."""
from .native_v2_contracts import ContractViolation2

MAX_BYTES = 262144
MAX_DEPTH = 32
MAX_NODES = 32768
MAX_OBJECTS = 128
MAX_EXPRESSIONS = 64
MAX_STRING_BYTES = 256


def _fail(reason='v2_json_invalid'):
    raise ContractViolation2(reason)


class _Parser:
    def __init__(self, text):
        self.text, self.at, self.nodes = text, 0, 0

    def count(self):
        if self.nodes >= MAX_NODES:
            _fail('v2_json_nodes_limit')
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
                _fail('v2_json_string_limit')
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
                _fail('v2_json_integer_invalid')
        if self.at == digits or (self.at - digits > 1 and self.text[digits] == '0'):
            _fail()
        if self.at < len(self.text) and self.text[self.at] in '.eE':
            _fail('v2_json_integer_invalid')
        value = int(self.text[start:self.at])
        if not -(2**63) <= value <= 2**63 - 1:
            _fail('v2_json_integer_invalid')
        return value

    def value(self, depth=1, path=()):
        if depth > MAX_DEPTH:
            _fail('v2_json_depth_limit')
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
                    _fail('v2_json_duplicate_key')
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
            limit = MAX_OBJECTS if path == ('nftables',) else MAX_EXPRESSIONS if path and path[-1] == 'expr' else MAX_NODES
            self.whitespace()
            if self.at < len(self.text) and self.text[self.at] == ']':
                self.at += 1
                return result
            while True:
                if len(result) >= limit:
                    _fail('v2_json_array_limit')
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
        # No boolean-valued field exists in this closed nft grammar.
        if self.text.startswith(('true', 'false', 'NaN', 'Infinity', '-Infinity'), self.at):
            _fail('v2_json_integer_invalid')
        _fail()


def bounded_json2(raw):
    """Exact bytes only; check size before UTF-8 decoding and tree allocation.

    At most MAX_BYTES of input text is decoded. Containers/nodes, strings and
    integer tokens are bounded before their potentially large allocations.
    These bounds apply to this parser's work, not memory already held by caller.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail('v2_json_size_invalid')
    if raw.startswith(b'\xef\xbb\xbf'):
        _fail('v2_json_encoding_invalid')
    try:
        text = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        _fail('v2_json_encoding_invalid')
    parser = _Parser(text)
    result = parser.value()
    parser.whitespace()
    if parser.at != len(text):
        _fail()
    return result
