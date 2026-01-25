"""Test REPL detection and error handling."""
from __future__ import annotations

from turtles.dsl import _get_user_frame, _check_not_in_repl, SourceNotAvailableError


class TestREPLDetection:
    """Test the REPL detection helper functions."""
    
    def test_get_user_frame_from_file(self):
        """Code running from a file should return the file path."""
        filename, lineno = _get_user_frame()
        assert filename.endswith('.py')
        assert lineno > 0
    
    def test_check_not_in_repl_from_file(self):
        """_check_not_in_repl should not raise when called from a file."""
        # Should not raise
        _check_not_in_repl("test operation")
    
    def test_source_not_available_error_is_exception(self):
        """SourceNotAvailableError should be a proper exception."""
        assert issubclass(SourceNotAvailableError, Exception)
        
        err = SourceNotAvailableError("test message")
        assert str(err) == "test message"


class TestCrossFileComposition:
    """Test that cross-file grammar composition works."""
    
    def test_import_and_extend_json(self):
        """Can define rules that use imported JSON rules."""
        from turtles import Rule, repeat, separator
        from turtles.examples.json import JSON
        
        class JSONL(Rule):
            lines: repeat[JSON, separator['\n']]  # noqa
        
        jsonl_input = '{"a": 1}\n{"b": 2}'
        result = JSONL(jsonl_input)
        
        assert len(result.lines) == 2
        assert result.lines[0].value.pairs[0].key.value == ["a"]
        assert result.lines[1].value.pairs[0].key.value == ["b"]
    
    def test_rule_union_across_files(self):
        """RuleUnion should work with rules from different files."""
        from turtles import Rule, char, repeat, at_least
        from turtles.examples.json import JString
        
        class Identifier(Rule):
            value: repeat[char['a-zA-Z_'], at_least[1]]  # noqa
        
        # Create a union of rules from different files
        StringOrId = JString | Identifier
        
        # Parse with imported rule
        result1 = StringOrId('"hello"')
        assert type(result1).__name__ == 'JString'
        
        # Parse with local rule
        result2 = StringOrId('hello')
        assert type(result2).__name__ == 'Identifier'
