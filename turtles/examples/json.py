"""
Full JSON grammar as defined by RFC 8259.
Supports all JSON types: null, boolean, number, string, array, object.
"""
from turtles import Rule, char, repeat, at_least, exactly, separator, either, sequence, optional


# Whitespace
class Whitespace(Rule):
    repeat[char['\x20\t\n\r']]


class Comma(Rule):
    Whitespace
    ','
    Whitespace


# Null
class JNull(Rule):
    "null"


# Boolean
class JBool(Rule):
    value: either[r"true", r"false"]


# Number components
class Int(Rule):
    value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]


class Fractional(Rule):
    '.'
    value: repeat[char['0-9'], at_least[1]]


class Exponent(Rule):
    char['eE']
    sign: optional[char['+-']]
    value: repeat[char['0-9'], at_least[1]]


class JNumber(Rule):
    sign: optional[r'-']
    whole: Int
    fractional: optional[Fractional]
    exponent: optional[Exponent]


# String escape sequences
class SimpleEscape(Rule):
    ch: either[r"\\", r"\"", r"\/", r"\b", r"\f", r"\n", r"\r", r"\t"]


class HexEscape(Rule):
    ch: sequence[r"\u", repeat[char['0-9a-fA-F'], exactly[4]]]


Escape = SimpleEscape | HexEscape


# String (printable ASCII and Unicode, except quote and backslash, plus escapes)
class JString(Rule):
    '"'
    value: repeat[char['\x20-\x21\x23-\x5B\x5D-\U0010FFFF'] | Escape]
    '"'


# Array
class JArray(Rule):
    '['
    Whitespace
    items: repeat[JSONValue, separator[Comma]]
    Whitespace
    ']'


# Object
class Pair(Rule):
    key: JString
    Whitespace
    ':'
    Whitespace
    value: JSONValue


class JObject(Rule):
    '{'
    Whitespace
    pairs: repeat[Pair, separator[Comma]]
    Whitespace
    '}'


# Top-level JSON
class JSON(Rule):
    Whitespace
    value: JSONValue
    Whitespace


# Union of all JSON value types
JSONValue = JNull | JBool | JNumber | JString | JArray | JObject


# Convenience exports
__all__ = [
    'JSON',
    'JSONValue',
    'JNull',
    'JBool',
    'JNumber',
    'JString',
    'JArray',
    'JObject',
    'Pair',
    'Whitespace',
    'Comma',
    'Int',
    'Fractional',
    'Exponent',
    'Escape',
    'SimpleEscape',
    'HexEscape',
]
