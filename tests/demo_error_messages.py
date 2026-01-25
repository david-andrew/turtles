#!/usr/bin/env python3
"""
Demo script showing the new parse error messages.

Run with: uv run python tests/demo_error_messages.py
"""
from __future__ import annotations

from turtles import Rule, char, repeat, at_least, either, separator, ParseError


def demo_basic_literal_error():
    """Show error when a literal doesn't match."""
    print("=" * 60)
    print("Demo 1: Literal mismatch")
    print("=" * 60)
    
    class Hello(Rule):
        "hello"
        " "
        "world"
    
    try:
        Hello("hello earth")
    except ParseError as e:
        print(str(e))
    print()


def demo_char_class_error():
    """Show error when a character class doesn't match."""
    print("=" * 60)
    print("Demo 2: Character class mismatch")
    print("=" * 60)
    
    class Number(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    try:
        Number("abc123")
    except ParseError as e:
        print(str(e))
    print()


def demo_choice_error():
    """Show error when none of the alternatives match."""
    print("=" * 60)
    print("Demo 3: Choice alternatives")
    print("=" * 60)
    
    class Keyword(Rule):
        value: either[r"if", r"else", r"while", r"for"]  # noqa
    
    try:
        Keyword("switch")
    except ParseError as e:
        print(str(e))
    print()


def demo_json_error():
    """Show error in JSON-like parsing."""
    print("=" * 60)
    print("Demo 4: JSON object error")
    print("=" * 60)
    
    class JString(Rule):
        '"'
        value: repeat[char['a-zA-Z0-9_']]  # noqa
        '"'
    
    class JNumber(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    JValue = JString | JNumber
    
    class Pair(Rule):
        key: JString
        ":"
        value: JValue
    
    class JObject(Rule):
        "{"
        pairs: repeat[Pair, separator[","]]  # noqa
        "}"
    
    try:
        # Missing colon
        JObject('{"name" 123}')
    except ParseError as e:
        print(str(e))
    print()


def demo_multiline_error():
    """Show error with multiline input."""
    print("=" * 60)
    print("Demo 5: Multiline input error")
    print("=" * 60)
    
    class Line(Rule):
        value: repeat[char['a-z'], at_least[1]]  # noqa
    
    class TwoLines(Rule):
        first: Line
        "\n"
        second: Line
    
    try:
        TwoLines("hello\n12345")
    except ParseError as e:
        print(str(e))
    print()


def demo_incomplete_input():
    """Show error when input ends unexpectedly."""
    print("=" * 60)
    print("Demo 6: Incomplete input")
    print("=" * 60)
    
    class Pair(Rule):
        "("
        left: repeat[char['0-9'], at_least[1]]
        ","
        right: repeat[char['0-9'], at_least[1]]
        ")"
    
    try:
        Pair("(123,")
    except ParseError as e:
        print(str(e))
    print()


if __name__ == "__main__":
    # Clear registry between demos
    demo_basic_literal_error()
    demo_char_class_error()
    demo_choice_error()
    demo_json_error()
    demo_multiline_error()
    demo_incomplete_input()
    
    print("=" * 60)
    print("All demos complete!")
    print("=" * 60)
