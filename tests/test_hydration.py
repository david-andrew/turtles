"""
Comprehensive test suite for grammar hydration.

Tests all DSL patterns to ensure capture extraction works correctly
for any grammar structure.
"""
import pytest
from pathlib import Path
from turtles import Rule, char, repeat, at_least, at_most, exactly, either, sequence, optional, separator, clear_registry_for_file
from turtles.easygrammar import _captured_locals

_THIS_FILE = str(Path(__file__).resolve())


@pytest.fixture(autouse=True)
def clear_test_state():
    """Clear the grammar registry for this file and captured locals between tests to avoid state pollution."""
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)
    yield
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)


# =============================================================================
# 1. Basic Terminal Patterns
# =============================================================================

class TestStringLiterals:
    """Test string literal matching and capture."""
    
    def test_simple_literal(self):
        class Hello(Rule):
            "hello"
        
        result = Hello("hello")
        assert result._text == "hello"
    
    def test_multiple_literals(self):
        class Greeting(Rule):
            "hello"
            " "
            "world"
        
        result = Greeting("hello world")
        assert result._text == "hello world"
    
    def test_captured_literal_choice(self):
        class Bool(Rule):
            value: either[r"true", r"false"]
        
        result_true = Bool("true")
        assert result_true.value == "true"
        
        result_false = Bool("false")
        assert result_false.value == "false"


class TestCharacterClasses:
    """Test character class matching and capture."""
    
    def test_single_char_class(self):
        class Digit(Rule):
            value: char['0-9']
        
        result = Digit("5")
        assert result.value == "5"
    
    def test_char_class_repeat(self):
        class Digits(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        result = Digits("12345")
        assert result.value == "12345"
    
    def test_multiple_char_classes(self):
        class AlphaNum(Rule):
            first: char['a-zA-Z']
            rest: repeat[char['a-zA-Z0-9']]
        
        result = AlphaNum("abc123")
        assert result.first == "a"
        assert result.rest == "bc123"
    
    def test_greeting(self):
        class Greeting(Rule):
            "Hello, "
            name: repeat[char['a-zA-Z'], at_least[1]]
            "!"
        
        result = Greeting("Hello, World!")
        assert result.name == "World"
        result = Greeting("Hello, Alice!")
        assert result.name == "Alice"


class TestAnonymousVsCaptured:
    """Test that anonymous elements don't appear in captures."""
    
    def test_anonymous_literal(self):
        class Quoted(Rule):
            '"'
            value: repeat[char['a-z']]
            '"'
        
        result = Quoted('"hello"')
        assert result.value == "hello"
        assert not hasattr(result, '_anonymous')
    
    def test_anonymous_char_class(self):
        class Exponent(Rule):
            char['eE']
            sign: optional[char['+-']]
            value: repeat[char['0-9'], at_least[1]]
        
        # Without sign
        result = Exponent("e10")
        assert result.sign == []
        assert result.value == "10"
        
        # With sign
        result_plus = Exponent("E+5")
        assert result_plus.sign == "+"
        assert result_plus.value == "5"


# =============================================================================
# 2. Repetition Patterns
# =============================================================================

class TestRepetition:
    """Test various repetition patterns."""
    
    def test_zero_or_more(self):
        class Letters(Rule):
            value: repeat[char['a-z']]
        
        result_some = Letters("abc")
        assert result_some.value == "abc"
        
        result_none = Letters("")
        assert result_none.value == ""
    
    def test_one_or_more(self):
        class Digits(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        result = Digits("123")
        assert result.value == "123"
    
    def test_at_most(self):
        class Limited(Rule):
            value: repeat[char['a-z'], at_most[3]]
        
        result = Limited("ab")
        assert result.value == "ab"
    
    def test_exactly(self):
        class HexByte(Rule):
            value: repeat[char['0-9a-fA-F'], exactly[2]]
        
        result = HexByte("FF")
        assert result.value == "FF"
    
    def test_separator_simple(self):
        class CSVNum(Rule):
            value: repeat[char['0-9'], at_least[1]]
        
        class CSVNumbers(Rule):
            items: repeat[CSVNum, separator[',']]
        
        result = CSVNumbers("1,2,3")
        assert len(result.items) == 3
        assert result.items[0].value == "1"
        assert result.items[1].value == "2"
        assert result.items[2].value == "3"
    
    def test_separator_complex(self):
        class SepComma(Rule):
            " "
            ","
            " "
        
        class SepItem(Rule):
            value: repeat[char['a-z'], at_least[1]]
        
        class SepItems(Rule):
            items: repeat[SepItem, separator[SepComma]]
        
        result = SepItems("foo , bar , baz")
        assert len(result.items) == 3
        assert result.items[0].value == "foo"
        assert result.items[1].value == "bar"
        assert result.items[2].value == "baz"
    
    def test_repeat_of_terminals_is_string(self):
        class TermWord(Rule):
            letters: repeat[char['a-z'], at_least[1]]
        
        result = TermWord("hello")
        assert isinstance(result.letters, str)
        assert result.letters == "hello"
    
    def test_repeat_of_rules_is_list(self):
        class ListWord(Rule):
            letters: repeat[char['a-z'], at_least[1]]
        
        class ListWords(Rule):
            words: repeat[ListWord, separator[' ']]
        
        result = ListWords("foo bar baz")
        assert isinstance(result.words, list)
        assert len(result.words) == 3


# =============================================================================
# 3. Choice/Alternative Patterns
# =============================================================================

class TestChoice:
    """Test choice/alternative patterns."""
    
    def test_terminal_alternatives(self):
        class Keyword(Rule):
            value: either[r"if", r"else", r"while"]
        
        assert Keyword("if").value == "if"
        assert Keyword("else").value == "else"
        assert Keyword("while").value == "while"
    
    def test_rule_alternatives(self):
        class AltNum(Rule):
            digits: repeat[char['0-9'], at_least[1]]
        
        class AltId(Rule):
            letters: repeat[char['a-z'], at_least[1]]
        
        AltExprValue = AltNum | AltId
        
        class AltExpr(Rule):
            value: AltExprValue
        
        num_result = AltExpr("123")
        assert isinstance(num_result.value, AltNum)
        assert num_result.value.digits == "123"
        
        id_result = AltExpr("abc")
        assert isinstance(id_result.value, AltId)
        assert id_result.value.letters == "abc"
    
    def test_rule_union_direct(self):
        class UnionNum(Rule):
            digits: repeat[char['0-9'], at_least[1]]
        
        class UnionId(Rule):
            letters: repeat[char['a-z'], at_least[1]]
        
        UnionValue = UnionNum | UnionId
        
        num_result = UnionValue("123")
        assert isinstance(num_result, UnionNum)
        
        id_result = UnionValue("abc")
        assert isinstance(id_result, UnionId)
    
    def test_anonymous_choice(self):
        class Sign(Rule):
            char['+-']
            value: repeat[char['0-9'], at_least[1]]
        
        result_plus = Sign("+5")
        assert result_plus.value == "5"
        
        result_minus = Sign("-3")
        assert result_minus.value == "3"


# =============================================================================
# 4. Optional Patterns
# =============================================================================

class TestOptional:
    """Test optional patterns."""
    
    def test_optional_present(self):
        class SignedNum(Rule):
            sign: optional[char['+-']]
            value: repeat[char['0-9'], at_least[1]]
        
        result = SignedNum("+42")
        assert result.sign == "+"
        assert result.value == "42"
    
    def test_optional_absent(self):
        class SignedNum(Rule):
            sign: optional[char['+-']]
            value: repeat[char['0-9'], at_least[1]]
        
        result = SignedNum("42")
        assert result.sign == []
        assert result.value == "42"
    
    def test_optional_rule_present(self):
        class MaybeTagged(Rule):
            tag: optional[Tag]
            value: repeat[char['a-z'], at_least[1]]
        
        class Tag(Rule):
            '['
            name: repeat[char['A-Z'], at_least[1]]
            ']'
        
        result = MaybeTagged("[FOO]bar")
        assert isinstance(result.tag, Tag)
        assert result.tag.name == "FOO"
        assert result.value == "bar"
    
    def test_optional_rule_absent(self):
        class MaybeTagged(Rule):
            tag: optional[Tag]
            value: repeat[char['a-z'], at_least[1]]
        
        class Tag(Rule):
            '['
            name: repeat[char['A-Z'], at_least[1]]
            ']'
        
        result = MaybeTagged("bar")
        assert result.tag == []
        assert result.value == "bar"
    
    def test_multiple_optionals(self):
        class Number(Rule):
            sign: optional[char['+-']]
            whole: repeat[char['0-9'], at_least[1]]
            frac: optional[Frac]
            exp: optional[Exp]
        
        class Frac(Rule):
            '.'
            digits: repeat[char['0-9'], at_least[1]]
        
        class Exp(Rule):
            char['eE']
            sign: optional[char['+-']]
            digits: repeat[char['0-9'], at_least[1]]
        
        # Just integer
        r1 = Number("42")
        assert r1.sign == []
        assert r1.whole == "42"
        assert r1.frac == []
        assert r1.exp == []
        
        # With sign
        r2 = Number("-42")
        assert r2.sign == "-"
        assert r2.whole == "42"
        
        # With fraction
        r3 = Number("3.14")
        assert r3.whole == "3"
        assert isinstance(r3.frac, Frac)
        assert r3.frac.digits == "14"
        
        # With exponent
        r4 = Number("1e10")
        assert r4.whole == "1"
        assert isinstance(r4.exp, Exp)
        assert r4.exp.digits == "10"
        
        # Full number
        r5 = Number("-3.14e+10")
        assert r5.sign == "-"
        assert r5.whole == "3"
        assert r5.frac.digits == "14"
        assert r5.exp.sign == "+"
        assert r5.exp.digits == "10"


# =============================================================================
# 5. Sequence Patterns
# =============================================================================

class TestSequence:
    """Test sequence patterns."""
    
    def test_explicit_sequence(self):
        class Int(Rule):
            value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
        
        result_zero = Int("0")
        assert result_zero.value == "0"
        
        result_num = Int("123")
        assert result_num.value == "123"
    
    def test_anonymous_between_captures(self):
        class KeyValue(Rule):
            key: repeat[char['a-z'], at_least[1]]
            ':'
            value: repeat[char['0-9'], at_least[1]]
        
        result = KeyValue("foo:123")
        assert result.key == "foo"
        assert result.value == "123"
    
    def test_multiple_captures(self):
        class Version(Rule):
            major: repeat[char['0-9'], at_least[1]]
            '.'
            minor: repeat[char['0-9'], at_least[1]]
            '.'
            patch: repeat[char['0-9'], at_least[1]]
        
        result = Version("1.2.3")
        assert result.major == "1"
        assert result.minor == "2"
        assert result.patch == "3"


# =============================================================================
# 6. Rule References
# =============================================================================

class TestRuleReferences:
    """Test rule references and recursion."""
    
    def test_forward_reference(self):
        class FwdInner(Rule):
            value: repeat[char['a-z'], at_least[1]]
        
        class FwdOuter(Rule):
            '('
            inner: FwdInner
            ')'
        
        result = FwdOuter("(hello)")
        assert isinstance(result.inner, FwdInner)
        assert result.inner.value == "hello"
    
    def test_backward_reference(self):
        class BwdInner(Rule):
            value: repeat[char['a-z'], at_least[1]]
        
        class BwdOuter(Rule):
            '('
            inner: BwdInner
            ')'
        
        result = BwdOuter("(hello)")
        assert isinstance(result.inner, BwdInner)
        assert result.inner.value == "hello"
    
    def test_recursive_rule(self):
        class RecNested(Rule):
            '('
            inner: optional[RecNested]
            ')'
        
        result1 = RecNested("()")
        assert result1.inner == []
        
        result2 = RecNested("(())")
        assert isinstance(result2.inner, RecNested)
        assert result2.inner.inner == []
        
        result3 = RecNested("((()))")
        assert isinstance(result3.inner.inner, RecNested)


# =============================================================================
# 7. Mixin Types
# =============================================================================

class TestMixinTypes:
    """Test mixin type behavior."""
    
    def test_int_mixin(self):
        class NumId(Rule, int):
            id: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
        
        result = NumId("42")
        assert result == 42
        assert isinstance(result, int)
        assert result + 1 == 43
    
    def test_str_mixin(self):
        class Identifier(Rule, str):
            id: repeat[char['a-zA-Z0-9_'], at_least[1]]
        
        result = Identifier("hello_world")
        assert result == "hello_world"
        assert isinstance(result, str)
        assert result.upper() == "HELLO_WORLD"


# =============================================================================
# 8. Edge Cases (Current Pain Points)
# =============================================================================

class TestEdgeCases:
    """Test edge cases that have caused problems."""
    
    def test_anonymous_terminal_before_capture(self):
        """The 'e' should NOT appear as the sign."""
        class ExpAnon(Rule):
            char['eE']
            sign: optional[char['+-']]
            value: repeat[char['0-9'], at_least[1]]
        
        result = ExpAnon("e10")
        assert result.sign == []
        assert result.value == "10"
    
    def test_compound_either_capture(self):
        """Capture on an either of terminals should produce string."""
        class IntCompound(Rule):
            value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
        
        result_zero = IntCompound("0")
        assert result_zero.value == "0"
        
        result_num = IntCompound("42")
        assert result_num.value == "42"
    
    def test_whitespace_filtering(self):
        """Anonymous whitespace rules should not appear in captures."""
        class WSF(Rule):
            repeat[char[' \t']]
        
        class KeyF(Rule):
            name: repeat[char['a-z'], at_least[1]]
        
        class ValueF(Rule):
            digits: repeat[char['0-9'], at_least[1]]
        
        class PairF(Rule):
            key: KeyF
            WSF
            ':'
            WSF
            value: ValueF
        
        result = PairF("foo : 123")
        assert isinstance(result.key, KeyF)
        assert result.key.name == "foo"
        assert isinstance(result.value, ValueF)
        assert result.value.digits == "123"
    
    def test_whitespace_in_list_captures(self):
        """Whitespace should not appear in list captures."""
        class WSL(Rule):
            repeat[char[' \t']]
        
        class SepL(Rule):
            WSL
            ','
            WSL
        
        class ItemL(Rule):
            value: repeat[char['a-z'], at_least[1]]
        
        class ItemsL(Rule):
            '['
            WSL
            items: repeat[ItemL, separator[SepL]]
            WSL
            ']'
        
        result = ItemsL("[ foo , bar , baz ]")
        assert len(result.items) == 3
        for item in result.items:
            assert isinstance(item, ItemL)
    
    def test_empty_optional_not_in_tree_string(self):
        """Empty optionals should not appear in tree_string output."""
        from turtles import tree_string
        
        class NumberTS(Rule):
            sign: optional[char['+-']]
            value: repeat[char['0-9'], at_least[1]]
        
        result = NumberTS("42")
        tree_str = tree_string(result)
        assert "sign" not in tree_str
        assert "value: 42" in tree_str
    
    def test_deeply_nested_captures(self):
        """Captures work at various nesting depths."""
        class InnerN(Rule):
            value: repeat[char['a-z'], at_least[1]]
        
        class MiddleN(Rule):
            '['
            inner: InnerN
            ']'
        
        class OuterN(Rule):
            '('
            middle: MiddleN
            ')'
        
        result = OuterN("([hello])")
        assert result.middle.inner.value == "hello"


# =============================================================================
# 9. JSON Grammar (Integration Test)
# =============================================================================

def test_json_null():
    """Test JSON null parsing."""
    from turtles.examples.json_toy import JNull
    
    result = JNull("null")
    assert result._text == "null"

def test_json_bool():
    """Test JSON bool parsing."""
    from turtles.examples.json_toy import JBool
    
    assert JBool("true").value == "true"
    assert JBool("false").value == "false"

def test_json_number():
    """Test JSON number parsing."""
    from turtles.examples.json_toy import JNumber  # full JSON number is more complex
    
    assert JNumber("123").value == "123"

def test_json_string():
    """Test JSON string parsing."""
    from turtles.examples.json_toy import JString # full JSON string is more complex
    
    assert JString('"hello"').value == "hello"

def test_json_simple_array():
    """Test JSON array with simple values."""
    from turtles.examples.json_toy import JNumber, JArray
    
    result = JArray("[1,2,3]")
    assert len(result.items) == 3
    assert isinstance(result.items[0], JNumber)
    assert result.items[0].value == "1"
    assert isinstance(result.items[1], JNumber)
    assert result.items[1].value == "2"
    assert isinstance(result.items[2], JNumber)
    assert result.items[2].value == "3"

def test_json_simple_object():
    """Test JSON object with simple values."""
    from turtles.examples.json_toy import JObject

    result = JObject('{"a":1,"b":2}')
    assert len(result.pairs) == 2
    assert result.pairs[0].key.value == "a"
    assert result.pairs[0].value.value == "1"
    assert result.pairs[1].key.value == "b"
    assert result.pairs[1].value.value == "2"

def test_json_full_grammar():
    """Test full JSON grammar with union types."""

    from turtles.examples.json_toy import JSONValue, JObject, JString, JNull, JArray, JNumber, JBool
    # Test various values
    assert isinstance(JSONValue("null"), JNull)
    assert isinstance(JSONValue("true"), JBool)
    assert isinstance(JSONValue("123"), JNumber)
    assert isinstance(JSONValue('"hello"'), JString)
    
    # Test array
    arr = JSONValue("[1,2,3]")
    assert isinstance(arr, JArray)
    assert len(arr.items) == 3
    
    # Test object
    obj = JSONValue('{"a":1}')
    assert isinstance(obj, JObject)
    assert len(obj.pairs) == 1
    assert obj.pairs[0].key.value == "a"
    assert obj.pairs[0].value.value == "1"


# =============================================================================
# 10. Full JSON with Whitespace (Integration Test)
# =============================================================================

def test_full_json_number_integer():
    """Test full JSON number - integer only."""
    class JInt1(Rule):
        value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
    
    class JFrac1(Rule):
        '.'
        value: repeat[char['0-9'], at_least[1]]
    
    class JExp1(Rule):
        char['eE']
        sign: optional[char['+-']]
        value: repeat[char['0-9'], at_least[1]]
    
    class JNum1(Rule):
        sign: optional[char['-']]
        whole: JInt1
        frac: optional[JFrac1]
        exp: optional[JExp1]
    
    result = JNum1('42')
    assert result.whole.value == "42"
    assert result.frac == []
    assert result.exp == []

def test_full_json_number_with_fraction():
    """Test full JSON number with fraction."""
    class JInt2(Rule):
        value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
    
    class JFrac2(Rule):
        '.'
        value: repeat[char['0-9'], at_least[1]]
    
    class JExp2(Rule):
        char['eE']
        sign: optional[char['+-']]
        value: repeat[char['0-9'], at_least[1]]
    
    class JNum2(Rule):
        sign: optional[char['-']]
        whole: JInt2
        frac: optional[JFrac2]
        exp: optional[JExp2]
    
    result = JNum2('3.14')
    assert result.whole.value == "3"
    assert isinstance(result.frac, JFrac2)
    assert result.frac.value == "14"

def test_full_json_number_with_exponent():
    """Test full JSON number with exponent."""
    class JInt3(Rule):
        value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
    
    class JFrac3(Rule):
        '.'
        value: repeat[char['0-9'], at_least[1]]
    
    class JExp3(Rule):
        char['eE']
        sign: optional[char['+-']]
        value: repeat[char['0-9'], at_least[1]]
    
    class JNum3(Rule):
        sign: optional[char['-']]
        whole: JInt3
        frac: optional[JFrac3]
        exp: optional[JExp3]
    
    result = JNum3('1e10')
    assert isinstance(result.exp, JExp3)
    assert result.exp.sign == []
    assert result.exp.value == "10"

def test_full_json_number_complete():
    """Test full JSON number with all parts."""
    class JInt4(Rule):
        value: either['0', sequence[char['1-9'], repeat[char['0-9']]]]
    
    class JFrac4(Rule):
        '.'
        value: repeat[char['0-9'], at_least[1]]
    
    class JExp4(Rule):
        char['eE']
        sign: optional[char['+-']]
        value: repeat[char['0-9'], at_least[1]]
    
    class JNum4(Rule):
        sign: optional[char['-']]
        whole: JInt4
        frac: optional[JFrac4]
        exp: optional[JExp4]
    
    result = JNum4('-3.14e+10')
    assert result.sign == "-"
    assert result.whole.value == "3"
    assert result.frac.value == "14"
    assert result.exp.sign == "+"
    assert result.exp.value == "10"

def test_json_with_whitespace():
    """Test JSON parsing with whitespace."""
    class Whitespace(Rule):
        repeat[char[' \t\n\r']]
    
    class JNumber(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    class JString(Rule):
        '"'
        value: repeat[char['a-zA-Z0-9_']]
        '"'
    
    class Pair(Rule):
        key: JString
        Whitespace
        ':'
        Whitespace
        value: JNumber
    
    class Comma(Rule):
        Whitespace
        ','
        Whitespace
    
    class JObject(Rule):
        '{'
        Whitespace
        pairs: repeat[Pair, separator[Comma]]
        Whitespace
        '}'
    
    result = JObject('{ "a" : 1 }')
    assert len(result.pairs) == 1
    assert result.pairs[0].key.value == "a"
    assert result.pairs[0].value.value == "1"


def test_toy_json():
    from turtles.examples.json_toy import JSONValue, JObject, JArray, JString, JNumber, JBool, JNull

    src = '{"A":{"a":null},"B":[true,false,1,2,3],"C":[{"d":[4,5,6]}]}'

    result = JSONValue(src)


    assert isinstance(result, JObject)
    assert len(result.pairs) == 3
    assert isinstance(result.pairs[0].key, JString)
    assert result.pairs[0].key == '"A"'
    assert isinstance(result.pairs[0].value, JObject)
    assert len(result.pairs[0].value.pairs) == 1
    assert result.pairs[0].value.pairs[0].key == '"a"'
    assert result.pairs[0].value.pairs[0].value == JNull
    assert result.pairs[1].key == '"B"'
    assert isinstance(result.pairs[1].value, JArray)
    assert len(result.pairs[1].value.items) == 5
    assert isinstance(result.pairs[1].value.items[0], JBool)
    assert result.pairs[1].value.items[0].value == "true"
    assert isinstance(result.pairs[1].value.items[1], JBool)
    assert result.pairs[1].value.items[1].value == "false"
    assert isinstance(result.pairs[1].value.items[2], JNumber)
    assert result.pairs[1].value.items[2].value == "1"
    assert isinstance(result.pairs[1].value.items[3], JNumber)
    assert result.pairs[1].value.items[3].value == "2"
    assert isinstance(result.pairs[1].value.items[4], JNumber)
    assert result.pairs[1].value.items[4].value == "3"
    assert result.pairs[2].key == '"C"'
    assert isinstance(result.pairs[2].value, JArray)
    assert len(result.pairs[2].value.items) == 1
    assert isinstance(result.pairs[2].value.items[0], JObject)
    assert len(result.pairs[2].value.items[0].pairs) == 1
    assert result.pairs[2].value.items[0].pairs[0].key == '"d"'
    assert isinstance(result.pairs[2].value.items[0].pairs[0].value, JArray)
    assert len(result.pairs[2].value.items[0].pairs[0].value.items) == 3
    assert isinstance(result.pairs[2].value.items[0].pairs[0].value.items[0], JNumber)
    assert result.pairs[2].value.items[0].pairs[0].value.items[0].value == "4"
    assert isinstance(result.pairs[2].value.items[0].pairs[0].value.items[1], JNumber)
    assert result.pairs[2].value.items[0].pairs[0].value.items[1].value == "5"
    assert isinstance(result.pairs[2].value.items[0].pairs[0].value.items[2], JNumber)
    assert result.pairs[2].value.items[0].pairs[0].value.items[2].value == "6"


def test_full_json():
    from turtles.examples.json import JSON, JObject, JString, JNull, JArray, JNumber, JBool

    src = '''
    {
      "A": { "a" : null },
      "B": [true, false, 1, 2.0, 3.14159],
      "C": [
        { "d": [4e9,5E-323,6.123e+10, [null, true, {"e": false}]] }
      ],
      "λ你好": "λ世界"
    }
    '''
    
    result = JSON(src)

    assert isinstance(result.value, JObject)
    assert len(result.value.pairs) == 4
    assert isinstance(result.value.pairs[0].key, JString)
    assert result.value.pairs[0].key == '"A"'
    assert isinstance(result.value.pairs[0].value, JObject)
    assert len(result.value.pairs[0].value.pairs) == 1
    assert result.value.pairs[0].value.pairs[0].key == '"a"'
    assert result.value.pairs[0].value.pairs[0].value == JNull
    assert result.value.pairs[1].key == '"B"'
    assert isinstance(result.value.pairs[1].value, JArray)
    assert len(result.value.pairs[1].value.items) == 5
    assert isinstance(result.value.pairs[1].value.items[0], JBool)
    assert result.value.pairs[1].value.items[0].value == "true"
    assert isinstance(result.value.pairs[1].value.items[1], JBool)
    assert result.value.pairs[1].value.items[1].value == "false"
    assert isinstance(result.value.pairs[1].value.items[2], JNumber)
    assert result.value.pairs[1].value.items[2] == '1'
    assert result.value.pairs[1].value.items[3].whole == '2'
    assert result.value.pairs[1].value.items[3].fractional == '.0'
    assert result.value.pairs[1].value.items[4].whole == '3'
    assert result.value.pairs[1].value.items[4].fractional == '.14159'
    assert result.value.pairs[2].key == '"C"'
    assert isinstance(result.value.pairs[2].value, JArray)
    assert len(result.value.pairs[2].value.items) == 1
    assert isinstance(result.value.pairs[2].value.items[0], JObject)
    assert len(result.value.pairs[2].value.items[0].pairs) == 1
    assert result.value.pairs[2].value.items[0].pairs[0].key == '"d"'
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value, JArray)
    assert len(result.value.pairs[2].value.items[0].pairs[0].value.items) == 4
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value.items[0], JNumber)
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[0].whole == '4'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[0].exponent == 'e9'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[1].whole == '5'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[1].exponent.sign == '-'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[1].exponent.value == '323'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[2].whole == '6'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[2].fractional.value == '123'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[2].exponent.sign == '+'
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[2].exponent.value == '10'
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value.items[3], JArray)
    assert len(result.value.pairs[2].value.items[0].pairs[0].value.items[3].items) == 3
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[0], JNull)
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[1], JBool)
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[1].value == "true"
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[2], JObject)
    assert len(result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[2].pairs) == 1
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[2].pairs[0].key == '"e"'
    assert isinstance(result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[2].pairs[0].value, JBool)
    assert result.value.pairs[2].value.items[0].pairs[0].value.items[3].items[2].pairs[0].value.value == "false"
    assert result.value.pairs[3].key == '"λ你好"'
    assert isinstance(result.value.pairs[3].value, JString)
    assert result.value.pairs[3].value == '"λ世界"'




def test_semver():
    from turtles.examples.semver import SemVer

    result = SemVer('1.2.3-alpha+3.14')

    assert result.major == '1'
    assert result.minor == '2'
    assert result.patch == '3'
    assert result.prerelease is not None
    assert result.prerelease.ids == ['alpha']
    assert result.build is not None
    assert result.build.ids == ['3', '14']





if __name__ == "__main__":
    pytest.main([__file__, "-v"])
