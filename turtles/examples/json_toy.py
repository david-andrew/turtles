"""
Toy JSON grammar demonstrating rudimentary JSON parsing.

Missing Features:
- whitespace between elements and around the top level item
- float or scientific notation numbers
- invalid integer numbers with leading zeros
- sign prefix (`+`/`-`) for numbers 
- strings don't support escapes, nor the vast majority of valid unicode characters
"""
from turtles import Rule, char, repeat, at_least, either, separator

class JNull(Rule):
    "null"

class JBool(Rule):
    value: either[r"true", r"false"]

class JNumber(Rule):
    value: repeat[char['0-9'], at_least[1]]

class JString(Rule):
    '"'
    value: repeat[char[r"A-Za-z0-9 !#$%&'()*+,\-./:;<=>?@[]^_`{|}~"]]
    '"'

class JArray(Rule):
    '['
    items: repeat[JSONValue, separator[',']]
    ']'

class Pair(Rule):
    key: JString
    ':'
    value: JSONValue

class JObject(Rule):
    '{'
    pairs: repeat[Pair, separator[',']]
    '}'

JSONValue = JNull | JBool | JNumber | JString | JArray | JObject


__all__ = [
    'JSONValue',
    'JObject',
    'JArray',
    'JString',
    'JNumber',
    'JBool',
    'JNull',
]