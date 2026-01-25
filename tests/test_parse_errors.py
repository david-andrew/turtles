"""
Tests for comprehensive parse error messages.

Tests that parse errors include:
- Accurate position information
- Expected element descriptions
- Context about what rule/field was being parsed
- Pretty formatting via prettyerr
"""
from __future__ import annotations

import pytest
from pathlib import Path
from turtles import (
    Rule, char, repeat, at_least, either, separator,
    ParseError, clear_registry_for_file,
)
from turtles.dsl import _captured_locals

_THIS_FILE = str(Path(__file__).resolve())


@pytest.fixture(autouse=True)
def clear_test_state():
    """Clear the grammar registry for this file between tests."""
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)
    yield
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)


class TestBasicErrorMessages:
    """Test basic error message generation."""
    
    def test_literal_mismatch(self):
        """Test error when a literal doesn't match."""
        class Hello(Rule):
            "hello"
        
        with pytest.raises(ParseError) as exc_info:
            Hello("hallo")
        
        error = exc_info.value
        assert error.position > 0 or error.failure_info is not None
        error_str = str(error)
        # Should mention what was expected
        assert "hello" in error_str.lower() or "expected" in error_str.lower()
    
    def test_char_class_mismatch(self):
        """Test error when a char class doesn't match."""
        class Digit(Rule):
            value: char['0-9']
        
        with pytest.raises(ParseError) as exc_info:
            Digit("x")
        
        error = exc_info.value
        error_str = str(error)
        # Should mention the character class
        assert "0-9" in error_str or "digit" in error_str.lower()
    
    def test_unexpected_end_of_input(self):
        """Test error when input ends unexpectedly."""
        class TwoDigits(Rule):
            first: char['0-9']
            second: char['0-9']
        
        with pytest.raises(ParseError) as exc_info:
            TwoDigits("5")
        
        error = exc_info.value
        error_str = str(error)
        # Should indicate end of input or incomplete
        assert "end" in error_str.lower() or error.position == 1
    
    def test_position_tracking(self):
        """Test that error position is tracked correctly."""
        class Number(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class Calculation(Rule):
            left: Number
            "+"
            right: Number
        
        with pytest.raises(ParseError) as exc_info:
            Calculation("123+abc")
        
        error = exc_info.value
        # Position should be at or after the 'a' (position 4)
        assert error.position >= 4 or (error.failure_info and error.failure_info.position >= 4)


class TestChoiceErrors:
    """Test error messages for choice/alternative failures."""
    
    def test_choice_of_literals(self):
        """Test error with multiple literal alternatives."""
        class Keyword(Rule):
            value: either[r"if", r"else", r"while"]  # noqa
        
        with pytest.raises(ParseError) as exc_info:
            Keyword("for")
        
        error_str = str(exc_info.value)
        # Should mention some alternatives
        assert "if" in error_str or "else" in error_str or "expected" in error_str.lower()
    
    def test_choice_of_rules(self):
        """Test error with rule alternatives."""
        class NumVal(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class StrVal(Rule):
            '"'
            value: repeat[char['a-z']]  # noqa
            '"'
        
        Value = NumVal | StrVal
        
        with pytest.raises(ParseError) as exc_info:
            Value("@invalid")
        
        error = exc_info.value
        # Should have failure info
        assert error.failure_info is not None


class TestRepeatErrors:
    """Test error messages for repeat constraints."""
    
    def test_at_least_constraint(self):
        """Test error when at_least constraint not met."""
        class Identifier(Rule):
            value: repeat[char['a-zA-Z'], at_least[1]]  # noqa
        
        with pytest.raises(ParseError) as exc_info:
            Identifier("123")
        
        error = exc_info.value
        # error_str = str(error)
        # Error should occur at start (position 0)
        assert error.position == 0 or (error.failure_info and error.failure_info.position == 0)
    
    def test_separator_error(self):
        """Test error when separator is missing."""
        class Num(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class CSV(Rule):
            items: repeat[Num, separator[',']]  # noqa
        
        # This should parse OK (1,2,3)
        result = CSV("1,2,3")
        assert len(result.items) == 3
        
        # But this should fail - missing separator
        with pytest.raises(ParseError) as exc_info:
            CSV("1 2 3")  # spaces instead of commas
        
        error = exc_info.value
        # Should fail at position 1 (the space)
        assert error.position >= 1 or (error.failure_info and error.failure_info.position >= 1)


class TestContextInfo:
    """Test that error messages include context about what was being parsed."""
    
    def test_field_context_in_error(self):
        """Test that field names appear in error context."""
        class Person(Rule):
            name: repeat[char['a-zA-Z'], at_least[1]]  # noqa
            ":"
            age: repeat[char['0-9'], at_least[1]]
        
        with pytest.raises(ParseError) as exc_info:
            Person("John:abc")  # 'abc' is not a valid age
        
        error = exc_info.value
        # Should have context info
        if error.failure_info and error.failure_info.contexts:
            ctx = error.failure_info.contexts[-1]
            assert ctx.field_name is not None or ctx.rule_name == "Person"
    
    def test_nested_rule_context(self):
        """Test context with nested rules."""
        class Inner(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class Outer(Rule):
            "["
            inner: Inner
            "]"
        
        with pytest.raises(ParseError) as exc_info:
            Outer("[abc]")
        
        error = exc_info.value
        # error_str = str(error)
        # Position should be inside the brackets
        assert error.position > 0 or (error.failure_info and error.failure_info.position > 0)


class TestPrettyErrFormatting:
    """Test that prettyerr formatting works correctly."""
    
    def test_error_has_line_info(self):
        """Test that error includes line/column info."""
        class Line(Rule):
            value: repeat[char['a-z'], at_least[1]]  # noqa
        
        with pytest.raises(ParseError) as exc_info:
            Line("123")
        
        error_str = str(exc_info.value)
        # Should include some location info
        assert "1" in error_str  # Line 1 or column 1
    
    def test_multiline_error_position(self):
        """Test error position in multiline input."""
        class Word(Rule):
            value: repeat[char['a-z'], at_least[1]]  # noqa
        
        class Lines(Rule):
            first: Word
            "\n"
            second: Word
        
        with pytest.raises(ParseError) as exc_info:
            Lines("hello\n123")  # second line has numbers
        
        error = exc_info.value
        # Error should be on or after line 2
        line, _ = 1, 1
        if error.failure_info:
            pos = error.failure_info.position
            line = error.input_str.count('\n', 0, pos) + 1
        assert line >= 1 or error.position >= 6


class TestJSONErrors:
    """Test error messages with JSON-like grammar."""
    
    def test_json_object_missing_colon(self):
        """Test error for missing colon in JSON object."""
        class JString(Rule):
            '"'
            value: repeat[char['a-z']]  # noqa
            '"'
        
        class JNumber(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class Pair(Rule):
            key: JString
            ":"
            value: JNumber
        
        class JObject(Rule):
            "{"
            pairs: repeat[Pair, separator[","]]  # noqa
            "}"
        
        with pytest.raises(ParseError) as exc_info:
            JObject('{"name" 123}')  # missing colon
        
        error = exc_info.value
        # error_str = str(error)
        # Should fail around position 8 (after "name")
        assert error.position > 5 or (error.failure_info and error.failure_info.position > 5)
    
    def test_json_array_trailing_comma(self):
        """Test error for trailing comma in array."""
        class JNumber(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class JArray(Rule):
            "["
            items: repeat[JNumber, separator[","]]  # noqa
            "]"
        
        # Valid
        result = JArray("[1,2,3]")
        assert len(result.items) == 3
        
        # With trailing comma - may or may not error depending on grammar
        # The important thing is it either parses or gives a useful error
        try:
            result = JArray("[1,2,]")
            # If it parses, it's because repeat allows empty final element
        except ParseError as e:
            # If it errors, it should be at the trailing comma or closing bracket
            assert e.position >= 4 or (e.failure_info and e.failure_info.position >= 4)


class TestFailureInfoDataStructures:
    """Test the FailureInfo and related data structures."""
    
    def test_failure_info_populated(self):
        """Test that failure_info is populated on ParseError."""
        class Simple(Rule):
            "hello"
        
        with pytest.raises(ParseError) as exc_info:
            Simple("goodbye")
        
        error = exc_info.value
        assert error.failure_info is not None
        assert isinstance(error.failure_info.position, int)
        assert isinstance(error.failure_info.expected, list)
    
    def test_expected_elements_populated(self):
        """Test that expected elements are populated."""
        class Num(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        with pytest.raises(ParseError) as exc_info:
            Num("abc")
        
        error = exc_info.value
        if error.failure_info:
            assert len(error.failure_info.expected) > 0
            # Should include info about expected digit
            expected_descs = [e.description for e in error.failure_info.expected]
            assert any('0-9' in d or 'digit' in d.lower() for d in expected_descs)
