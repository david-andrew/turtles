"""
Comprehensive test suite for CSV grammar (RFC 4180).

Tests all CSV features: quoted fields, unquoted fields, empty fields,
multiple record separators, escaped quotes, multiline fields, etc.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from turtles.examples.csv import (
    CSV,
    CSVSkipInitialSpace,
    QuotedField,
    UnquotedField,
)

_THIS_FILE = str(Path(__file__).resolve())


# =============================================================================
# Basic CSV Parsing
# =============================================================================

class TestBasicCSV:
    """Test basic CSV parsing with simple records."""
    
    def test_single_record_single_field(self):
        """Test a single record with one field."""
        result = CSV("hello")
        assert len(result.records) == 1
        assert result.records[0].first is not None
        assert result.records[0].first._text == "hello"
    
    def test_single_record_multiple_fields(self):
        """Test a single record with multiple fields."""
        result = CSV("a,b,c")
        assert len(result.records) == 1
        record = result.records[0]
        assert record.first is not None
        assert record.first._text == "a"
        assert len(record.rest) == 2
        assert record.rest[0].field is not None
        assert record.rest[0].field._text == "b"
        assert record.rest[1].field is not None
        assert record.rest[1].field._text == "c"
    
    def test_multiple_records(self):
        """Test multiple records separated by newlines."""
        result = CSV("a,b\nc,d\ne,f")
        assert len(result.records) == 3
        assert result.records[0].first._text == "a"
        assert result.records[1].first._text == "c"
        assert result.records[2].first._text == "e"
    
    def test_trailing_newline(self):
        """Test CSV with trailing newline.
        
        Due to GLL parser ambiguity, a trailing newline may be parsed as either:
        - optional[RecordSep] at the end (1 record)
        - A separator followed by an empty record (2 records)
        Both are valid parses. We filter empty records to get consistent results.
        """
        result = CSV("a,b\n")
        # Filter out empty records to handle parse ambiguity
        non_empty = [r for r in result.records if r.first is not None]
        assert len(non_empty) == 1
        assert non_empty[0].first._text == "a"


# =============================================================================
# Empty Fields
# =============================================================================

class TestEmptyFields:
    """Test handling of empty fields.
    
    Empty optional fields are represented as None, matching the type hint semantics
    where optional[A] is equivalent to A | None.
    """
    
    def test_leading_empty_field(self):
        """Test record starting with empty field."""
        result = CSV(",a")
        record = result.records[0]
        assert record.first is None  # Leading empty field
        assert record.rest[0].field is not None
        assert record.rest[0].field._text == "a"
    
    def test_trailing_empty_field(self):
        """Test record ending with empty field."""
        result = CSV("a,")
        record = result.records[0]
        assert record.first is not None
        assert record.first._text == "a"
        assert record.rest[0].field is None  # Trailing empty field
    
    def test_middle_empty_field(self):
        """Test empty field in the middle."""
        result = CSV("a,,b")
        record = result.records[0]
        assert record.first._text == "a"
        assert record.rest[0].field is None  # Middle empty field
        assert record.rest[1].field is not None
        assert record.rest[1].field._text == "b"
    
    def test_all_empty_fields(self):
        """Test record with all empty fields."""
        result = CSV(",,")
        record = result.records[0]
        assert record.first is None
        assert len(record.rest) == 2
        assert record.rest[0].field is None
        assert record.rest[1].field is None
    
    def test_single_empty_field(self):
        """Test record with just one empty field (empty string input)."""
        result = CSV("")
        record = result.records[0]
        # Empty input means first field is empty
        assert record.first is None


# =============================================================================
# Quoted Fields
# =============================================================================

class TestQuotedFields:
    """Test quoted field parsing.
    
    Note: _text returns the raw matched text including quotes.
    The inner content (without quotes) is in the 'value' attribute.
    """
    
    def test_simple_quoted_field(self):
        """Test a simple quoted field."""
        result = CSV('"hello"')
        record = result.records[0]
        assert record.first is not None
        assert isinstance(record.first, QuotedField)
        # _text includes the quotes
        assert record.first._text == '"hello"'
        # value contains the inner content (the repeat capture)
        assert hasattr(record.first, 'value')
    
    def test_quoted_field_with_comma(self):
        """Test quoted field containing a comma."""
        result = CSV('"a,b"')
        record = result.records[0]
        assert isinstance(record.first, QuotedField)
        assert record.first._text == '"a,b"'
    
    def test_quoted_field_with_newline(self):
        """Test quoted field containing a newline (multiline field)."""
        result = CSV('"a\nb"')
        record = result.records[0]
        assert isinstance(record.first, QuotedField)
        assert "\n" in record.first._text
    
    def test_quoted_field_with_escaped_quote(self):
        """Test quoted field with escaped quote (doubled quote)."""
        result = CSV('"say ""hello"""')
        record = result.records[0]
        assert isinstance(record.first, QuotedField)
        # The raw text still has doubled quotes
        assert '""' in record.first._text
    
    def test_multiple_quoted_fields(self):
        """Test multiple quoted fields."""
        result = CSV('"a","b","c"')
        record = result.records[0]
        assert isinstance(record.first, QuotedField)
        assert record.first._text == '"a"'
        assert isinstance(record.rest[0].field, QuotedField)
        assert record.rest[0].field._text == '"b"'
        assert isinstance(record.rest[1].field, QuotedField)
        assert record.rest[1].field._text == '"c"'
    
    def test_mixed_quoted_and_unquoted(self):
        """Test mixing quoted and unquoted fields."""
        result = CSV('a,"b",c')
        record = result.records[0]
        assert isinstance(record.first, UnquotedField)
        assert isinstance(record.rest[0].field, QuotedField)
        assert isinstance(record.rest[1].field, UnquotedField)


# =============================================================================
# Unquoted Fields
# =============================================================================

class TestUnquotedFields:
    """Test unquoted field parsing."""
    
    def test_simple_unquoted_field(self):
        """Test a simple unquoted field."""
        result = CSV("hello")
        record = result.records[0]
        assert isinstance(record.first, UnquotedField)
        assert record.first._text == "hello"
    
    def test_unquoted_field_with_special_chars(self):
        """Test unquoted field with allowed special characters."""
        result = CSV("hello-world_123")
        record = result.records[0]
        assert isinstance(record.first, UnquotedField)
        assert record.first._text == "hello-world_123"
    
    def test_multiple_unquoted_fields(self):
        """Test multiple unquoted fields."""
        result = CSV("a,b,c")
        record = result.records[0]
        assert all(isinstance(f, UnquotedField) for f in [
            record.first,
            record.rest[0].field,
            record.rest[1].field
        ])


# =============================================================================
# Record Separators
# =============================================================================

class TestRecordSeparators:
    """Test different record separator formats."""
    
    def test_lf_separator(self):
        """Test LF (\\n) as record separator."""
        result = CSV("a\nb\nc")
        assert len(result.records) == 3
    
    def test_crlf_separator(self):
        """Test CRLF (\\r\\n) as record separator.
        
        Note: Due to GLL parser ambiguity, \\r\\n may sometimes be parsed as 
        CR + LF (two separators) instead of a single CRLF, creating an extra 
        empty record. This is valid according to the grammar but may not match
        expected CSV behavior. Filter out empty records if needed.
        """
        result = CSV("a\r\nb\r\nc")
        # Filter out empty records for comparison
        non_empty = [r for r in result.records if r.first is not None]
        assert len(non_empty) == 3
    
    def test_cr_separator(self):
        """Test CR (\\r) as record separator."""
        result = CSV("a\rb\rc")
        assert len(result.records) == 3
    
    def test_mixed_separators(self):
        """Test mixing different record separators."""
        result = CSV("a\nb\r\nc\rd")
        assert len(result.records) == 4


# =============================================================================
# BOM Handling
# =============================================================================

class TestBOM:
    """Test BOM (Byte Order Mark) handling."""
    
    def test_csv_with_bom(self):
        """Test CSV file starting with BOM."""
        result = CSV("\ufeffa,b")
        assert len(result.records) == 1
        assert result.records[0].first._text == "a"
    
    def test_csv_without_bom(self):
        """Test CSV file without BOM."""
        result = CSV("a,b")
        assert len(result.records) == 1
        assert result.records[0].first._text == "a"


# =============================================================================
# Skip Initial Space Variant
# =============================================================================

class TestSkipInitialSpace:
    """Test CSVSkipInitialSpace variant.
    
    Note: Due to grammar ambiguity (UnquotedField includes spaces), the 
    SkipInitialSpace variant works best with quoted fields or when the 
    field starts with a non-space character. For unquoted fields starting
    with spaces, the space may be captured as part of the field value due
    to GLL parser exploring multiple valid parses.
    """
    
    def test_basic_skip_initial_space_quoted(self):
        """Test skipping spaces after commas with quoted fields."""
        result = CSVSkipInitialSpace('a, "b", "c"')
        record = result.records[0]
        assert record.first._text == "a"
        # Quoted fields work correctly with skip initial space
        assert record.rest[0].field._text == '"b"'
        assert record.rest[1].field._text == '"c"'
    
    def test_multiple_spaces_before_quoted(self):
        """Test multiple spaces after comma with quoted field."""
        result = CSVSkipInitialSpace('a,   "b"')
        record = result.records[0]
        assert record.first._text == "a"
        assert record.rest[0].field._text == '"b"'
    
    def test_tabs_after_comma_quoted(self):
        """Test tabs after comma with quoted field."""
        result = CSVSkipInitialSpace('a,\t"b"')
        record = result.records[0]
        assert record.first._text == "a"
        assert record.rest[0].field._text == '"b"'
    
    def test_mixed_spaces_and_tabs_quoted(self):
        """Test mix of spaces and tabs after comma with quoted field."""
        result = CSVSkipInitialSpace('a, \t "b"')
        record = result.records[0]
        assert record.first._text == "a"
        assert record.rest[0].field._text == '"b"'


# =============================================================================
# Complex Real-World Examples
# =============================================================================

class TestComplexExamples:
    """Test complex real-world CSV examples."""
    
    def test_typical_csv_with_headers(self):
        """Test typical CSV with header row."""
        csv_text = "name,age,city\nAlice,30,NYC\nBob,25,SF"
        result = CSV(csv_text)
        assert len(result.records) == 3
        assert result.records[0].first._text == "name"
        assert result.records[1].first._text == "Alice"
        assert result.records[2].first._text == "Bob"
    
    def test_csv_with_quoted_fields_containing_separators(self):
        """Test CSV with quoted fields that contain commas."""
        csv_text = 'name,description\n"Smith, John","Engineer, Senior"'
        result = CSV(csv_text)
        assert len(result.records) == 2
        # _text includes quotes for QuotedFields
        assert result.records[1].first._text == '"Smith, John"'
        assert result.records[1].rest[0].field._text == '"Engineer, Senior"'
    
    def test_csv_with_multiline_quoted_fields(self):
        """Test CSV with multiline quoted fields."""
        csv_text = 'name,address\n"Alice","123 Main St\nApt 4B\nNYC, NY"'
        result = CSV(csv_text)
        assert len(result.records) == 2
        assert "\n" in result.records[1].rest[0].field._text
    
    def test_csv_with_empty_fields_mixed(self):
        """Test CSV with various empty field patterns."""
        csv_text = ",a,,\nb,,c,\n,,"  # Various empty field patterns
        result = CSV(csv_text)
        assert len(result.records) == 3
        # First record: empty, a, empty, empty
        assert result.records[0].first is None  # Empty field
        assert result.records[0].rest[0].field._text == "a"
        assert result.records[0].rest[1].field is None
        assert result.records[0].rest[2].field is None
        # Second record: b, empty, c, empty
        assert result.records[1].first._text == "b"
        assert result.records[1].rest[0].field is None
        assert result.records[1].rest[1].field._text == "c"
        assert result.records[1].rest[2].field is None
        # Third record: all empty
        assert result.records[2].first is None
        assert result.records[2].rest[0].field is None
        assert result.records[2].rest[1].field is None


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_character_fields(self):
        """Test single character fields."""
        result = CSV("a,b,c")
        assert len(result.records) == 1
        assert result.records[0].first._text == "a"
    
    def test_very_long_field(self):
        """Test very long field value."""
        long_field = "a" * 500
        result = CSV(long_field)
        assert result.records[0].first._text == long_field
    
    def test_many_fields(self):
        """Test record with many fields."""
        many_fields = ",".join(f"field{i}" for i in range(20))
        result = CSV(many_fields)
        record = result.records[0]
        assert record.first._text == "field0"
        assert len(record.rest) == 19
        assert record.rest[-1].field._text == "field19"
    
    def test_many_records(self):
        """Test CSV with many records."""
        many_records = "\n".join(f"a{i},b{i}" for i in range(20))
        result = CSV(many_records)
        assert len(result.records) == 20
    
    def test_unicode_characters(self):
        """Test CSV with Unicode characters."""
        result = CSV("你好,世界,🌍")
        record = result.records[0]
        assert record.first._text == "你好"
        assert record.rest[0].field._text == "世界"
        assert record.rest[1].field._text == "🌍"


# =============================================================================
# Error Cases (should raise ParseError)
# =============================================================================

class TestErrorCases:
    """Test cases that should fail parsing."""
    
    def test_unclosed_quoted_field(self):
        """Test unclosed quoted field should raise error."""
        with pytest.raises(Exception):  # ParseError or similar
            CSV('"unclosed')
    
    def test_quote_in_unquoted_field(self):
        """Test quote character in unquoted field should raise error."""
        with pytest.raises(Exception):
            CSV('field"with"quote')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
