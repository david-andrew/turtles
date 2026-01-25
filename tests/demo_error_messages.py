#!/usr/bin/env python3
"""
Comprehensive demo of parse error messages.

Run with: uv run python tests/demo_error_messages.py
"""
from __future__ import annotations

from turtles import Rule, char, repeat, at_least, either, separator, optional, ParseError


# =============================================================================
# JSON Grammar for demos (with whitespace handling)
# =============================================================================

# Whitespace - optional spaces/tabs/newlines
class WS(Rule):
    _: repeat[char[' \t\n\r']]  # noqa

class JNull(Rule):
    "null"

class JTrue(Rule):
    "true"

class JFalse(Rule):
    "false"

class JNumber(Rule):
    sign: optional[either["+", "-"]]  # noqa
    integer: repeat[char['0-9'], at_least[1]]
    fraction: optional['.', repeat[char['0-9'], at_least[1]]]  # noqa

class JString(Rule):
    '"'
    value: repeat[either[  # noqa
        char['a-zA-Z0-9_ :/.@#$%^&*()\\-'],
        r'\"',
        r'\\',
    ]]
    '"'

# Forward declare for recursion
JValue = JNull | JTrue | JFalse | JNumber | JString

class JArrayItem(Rule):
    _ws1: WS
    value: JValue
    _ws2: WS

class JArray(Rule):
    "["
    _ws: WS
    items: repeat[JArrayItem, separator[","]]  # noqa
    "]"

class JPair(Rule):
    _ws1: WS
    key: JString
    _ws2: WS
    ":"
    _ws3: WS
    value: JValue
    _ws4: WS

class JObject(Rule):
    "{"
    _ws: WS
    pairs: repeat[JPair, separator[","]]  # noqa
    "}"

# Update JValue to include arrays and objects
JValue = JNull | JTrue | JFalse | JNumber | JString | JArray | JObject


# =============================================================================
# Demo Functions
# =============================================================================

def print_header(num: int, title: str):
    print()
    print("=" * 70)
    print(f"Demo {num}: {title}")
    print("=" * 70)


def demo_simple_literal():
    """Basic literal mismatch."""
    print_header(1, "Simple literal mismatch")
    
    class Hello(Rule):
        "hello"
        " "
        "world"
    
    try:
        Hello("hello earth")
    except ParseError as e:
        print(str(e))


def demo_char_class():
    """Character class mismatch."""
    print_header(2, "Character class mismatch")
    
    class Identifier(Rule):
        value: repeat[char['a-zA-Z_'], at_least[1]]
    
    try:
        Identifier("123invalid")
    except ParseError as e:
        print(str(e))


def demo_choice_alternatives():
    """Multiple alternatives, none match."""
    print_header(3, "Choice alternatives")
    
    class Keyword(Rule):
        value: either[r"if", r"else", r"while", r"for", r"return"]  # noqa
    
    try:
        Keyword("switch")
    except ParseError as e:
        print(str(e))


def demo_multiline_simple():
    """Error on second line of input."""
    print_header(4, "Error on line 2")
    
    class Word(Rule):
        value: repeat[char['a-z'], at_least[1]]  # noqa
    
    class TwoWords(Rule):
        first: Word
        "\n"
        second: Word
    
    try:
        TwoWords("hello\n12345")
    except ParseError as e:
        print(str(e))


def demo_incomplete_input():
    """Input ends unexpectedly."""
    print_header(5, "Incomplete input")
    
    class Tuple(Rule):
        "("
        a: repeat[char['0-9'], at_least[1]]
        ","
        b: repeat[char['0-9'], at_least[1]]
        ","
        c: repeat[char['0-9'], at_least[1]]
        ")"
    
    try:
        Tuple("(1,2,")
    except ParseError as e:
        print(str(e))


def demo_json_missing_colon():
    """JSON object with missing colon."""
    print_header(6, "JSON missing colon")
    
    json_input = '{"name" "value"}'
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_missing_comma():
    """JSON object with missing comma between pairs."""
    print_header(7, "JSON missing comma")
    
    json_input = '{"a":1 "b":2}'
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_multiline_error_early():
    """Error early in a multiline JSON."""
    print_header(8, "Multiline JSON - error on line 2")
    
    json_input = """{
  "name" "John",
  "age": 30,
  "city": "NYC"
}"""
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_multiline_error_middle():
    """Error in the middle of a multiline JSON."""
    print_header(9, "Multiline JSON - error on line 4")
    
    json_input = """{
  "name": "John",
  "age": 30,
  "city" "NYC",
  "zip": 10001
}"""
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_multiline_error_late():
    """Error near the end of a multiline JSON."""
    print_header(10, "Multiline JSON - error near end")
    
    json_input = """{
  "name": "John",
  "age": 30,
  "city": "NYC",
  "active": tru
}"""
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_nested_array_error():
    """Error inside a nested array."""
    print_header(11, "Nested array error")
    
    json_input = """[1, 2, 3, four, 5]"""
    
    try:
        JArray(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_deep_nesting_error():
    """Error deep in nested structure."""
    print_header(12, "Deep nesting error")
    
    json_input = """{
  "level1": {
    "level2": {
      "level3": {
        "value": bad
      }
    }
  }
}"""
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_unclosed_string():
    """Unclosed string literal."""
    print_header(13, "Unclosed string")
    
    json_input = '{"message": "hello world}'
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_unclosed_brace():
    """Missing closing brace."""
    print_header(14, "Missing closing brace")
    
    json_input = """{
  "name": "John",
  "age": 30
"""
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_json_large_document():
    """Error in a larger JSON document."""
    print_header(15, "Large document error")
    
    json_input = """{
  "users": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
    {"id": 3, "name": "Charlie", "email": charlie@example.com},
    {"id": 4, "name": "Diana", "email": "diana@example.com"}
  ],
  "count": 4,
  "page": 1
}"""
    
    try:
        JObject(json_input)
    except ParseError as e:
        print(str(e))


def demo_config_file_error():
    """Error in a config-like structure."""
    print_header(16, "Config file style error")
    
    class CfgKey(Rule):
        value: repeat[char['a-zA-Z_'], at_least[1]]
    
    class CfgNumber(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    class CfgWord(Rule):
        value: repeat[char['a-zA-Z'], at_least[1]]  # noqa
    
    CfgValue = CfgNumber | CfgWord
    
    class CfgLine(Rule):
        key: CfgKey
        "="
        value: CfgValue
    
    class CfgFile(Rule):
        lines: repeat[CfgLine, separator["\n"]]  # noqa
    
    config_input = """host=localhost
port=8080
debug=true
timeout=@invalid
retries=3"""
    
    try:
        CfgFile(config_input)
    except ParseError as e:
        print(str(e))


def demo_expression_error():
    """Error in a mathematical expression."""
    print_header(17, "Expression parsing error")
    
    class Num(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    class Op(Rule):
        value: either["+", "-", "*", "/"]  # noqa
    
    class Expr(Rule):
        first: Num
        rest: repeat[Op, Num]  # noqa
    
    try:
        Expr("10 + 20 % 5")
    except ParseError as e:
        print(str(e))


if __name__ == "__main__":
    demo_simple_literal()
    demo_char_class()
    demo_choice_alternatives()
    demo_multiline_simple()
    demo_incomplete_input()
    demo_json_missing_colon()
    demo_json_missing_comma()
    demo_json_multiline_error_early()
    demo_json_multiline_error_middle()
    demo_json_multiline_error_late()
    demo_json_nested_array_error()
    demo_json_deep_nesting_error()
    demo_json_unclosed_string()
    demo_json_unclosed_brace()
    demo_json_large_document()
    demo_config_file_error()
    demo_expression_error()
    
    print()
    print("=" * 70)
    print("All demos complete!")
    print("=" * 70)
