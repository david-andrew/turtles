"""
Tests for handling ambiguous grammars with precedence and associativity.
"""
import pytest
from pathlib import Path
from turtles import Rule, char, repeat, at_least, exactly, separator, either, sequence, optional, clear_registry_for_file
from turtles.easygrammar import _captured_locals

_THIS_FILE = str(Path(__file__).resolve())


@pytest.fixture(autouse=True)
def clear_test_state():
    """Clear state between tests."""
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)
    yield
    _captured_locals.clear()
    clear_registry_for_file(_THIS_FILE)


# =============================================================================
# Expression Grammar Fixtures
# =============================================================================

@pytest.fixture
def expr_grammar():
    """Create an expression grammar with precedence rules."""
    class Num(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    class Id(Rule):
        # First char must be letter/underscore, rest can include digits
        first: char['a-zA-Z_']
        rest: repeat[char['a-zA-Z_0-9']]

    class Add(Rule):
        left: Expr
        char['+-']
        right: Expr

    class Mul(Rule):
        left: Expr
        char['*/']
        right: Expr
    
    class Pow(Rule):
        left: Expr
        '^'
        right: Expr

    class Paren(Rule):
        '('
        inner: Expr
        ')'

    Expr = Add | Mul | Pow | Paren | Num | Id
    
    # Set precedence: Pow > Mul > Add (higher precedence = binds tighter)
    Expr.precedence = [Pow, Mul, Add]
    
    # Set associativity
    Expr.associativity = {Add: 'left', Mul: 'left', Pow: 'right'}

    return {
        'Expr': Expr,
        'Num': Num,
        'Id': Id,
        'Add': Add,
        'Mul': Mul,
        'Pow': Pow,
        'Paren': Paren,
    }


# =============================================================================
# Basic Parsing Tests
# =============================================================================

class TestBasicExpressions:
    """Test parsing basic expressions."""
    
    def test_parse_number(self, expr_grammar):
        Expr = expr_grammar['Expr']
        result = Expr("42")
        assert result._text == "42"
        assert result.value == "42"
    
    def test_parse_identifier(self, expr_grammar):
        Expr = expr_grammar['Expr']
        Id = expr_grammar['Id']
        result = Expr("foo")
        assert isinstance(result, Id)
        assert result._text == "foo"
        assert result.first == "f"
        assert result.rest == "oo"
    
    def test_parse_simple_add(self, expr_grammar):
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        result = Expr("1+2")
        assert isinstance(result, Add)
        assert result.left.value == "1"
        assert result.right.value == "2"
    
    def test_parse_simple_mul(self, expr_grammar):
        Expr = expr_grammar['Expr']
        Mul = expr_grammar['Mul']
        result = Expr("3*4")
        assert isinstance(result, Mul)
        assert result.left.value == "3"
        assert result.right.value == "4"
    
    def test_parse_simple_pow(self, expr_grammar):
        Expr = expr_grammar['Expr']
        Pow = expr_grammar['Pow']
        result = Expr("2^3")
        assert isinstance(result, Pow)
        assert result.left.value == "2"
        assert result.right.value == "3"
    
    def test_parse_parenthesized(self, expr_grammar):
        Expr = expr_grammar['Expr']
        Paren = expr_grammar['Paren']
        result = Expr("(42)")
        assert isinstance(result, Paren)
        assert result.inner.value == "42"


# =============================================================================
# Precedence Tests
# =============================================================================

class TestPrecedence:
    """Test that precedence rules are applied correctly."""
    
    def test_mul_binds_tighter_than_add(self, expr_grammar):
        """1+2*3 should parse as 1+(2*3), not (1+2)*3"""
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        Mul = expr_grammar['Mul']
        
        result = Expr("1+2*3")
        # Top level should be Add
        assert isinstance(result, Add), f"Expected Add, got {type(result).__name__}"
        # left should be Num(1)
        assert result.left.value == "1"
        # right should be Mul(2, 3)
        assert isinstance(result.right, Mul), f"Expected Mul on right, got {type(result.right).__name__}"
        assert result.right.left.value == "2"
        assert result.right.right.value == "3"
    
    def test_mul_binds_tighter_than_add_reversed(self, expr_grammar):
        """1*2+3 should parse as (1*2)+3"""
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        Mul = expr_grammar['Mul']
        
        result = Expr("1*2+3")
        # Top level should be Add
        assert isinstance(result, Add), f"Expected Add, got {type(result).__name__}"
        # left should be Mul(1, 2)
        assert isinstance(result.left, Mul), f"Expected Mul on left, got {type(result.left).__name__}"
        assert result.left.left.value == "1"
        assert result.left.right.value == "2"
        # right should be Num(3)
        assert result.right.value == "3"
    
    def test_pow_binds_tighter_than_mul(self, expr_grammar):
        """2*3^4 should parse as 2*(3^4)"""
        Expr = expr_grammar['Expr']
        Mul = expr_grammar['Mul']
        Pow = expr_grammar['Pow']
        
        result = Expr("2*3^4")
        assert isinstance(result, Mul), f"Expected Mul, got {type(result).__name__}"
        assert result.left.value == "2"
        assert isinstance(result.right, Pow), f"Expected Pow on right, got {type(result.right).__name__}"
        assert result.right.left.value == "3"
        assert result.right.right.value == "4"
    
    def test_complex_precedence(self, expr_grammar):
        """1+2*3^4 should parse as 1+(2*(3^4))"""
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        Mul = expr_grammar['Mul']
        Pow = expr_grammar['Pow']
        
        result = Expr("1+2*3^4")
        # Top: Add
        assert isinstance(result, Add)
        assert result.left.value == "1"
        # right: Mul
        assert isinstance(result.right, Mul)
        assert result.right.left.value == "2"
        # right.right: Pow
        assert isinstance(result.right.right, Pow)
        assert result.right.right.left.value == "3"
        assert result.right.right.right.value == "4"


# =============================================================================
# Parentheses Tests
# =============================================================================

class TestParentheses:
    """Test that parentheses override precedence."""
    
    def test_parens_override_precedence(self, expr_grammar):
        """(1+2)*3 should parse with Add inside Paren, then Mul"""
        Expr = expr_grammar['Expr']
        Mul = expr_grammar['Mul']
        Paren = expr_grammar['Paren']
        Add = expr_grammar['Add']
        
        result = Expr("(1+2)*3")
        assert isinstance(result, Mul), f"Expected Mul, got {type(result).__name__}"
        assert isinstance(result.left, Paren), f"Expected Paren on left, got {type(result.left).__name__}"
        assert isinstance(result.left.inner, Add)
        assert result.right.value == "3"
    
    def test_nested_parens(self, expr_grammar):
        """((1+2)) should parse correctly"""
        Expr = expr_grammar['Expr']
        Paren = expr_grammar['Paren']
        Add = expr_grammar['Add']
        
        result = Expr("((1+2))")
        assert isinstance(result, Paren)
        assert isinstance(result.inner, Paren)
        assert isinstance(result.inner.inner, Add)
    
    def test_parens_in_complex_expr(self, expr_grammar):
        """(1+2)*(3+4) should have two Paren children"""
        Expr = expr_grammar['Expr']
        Mul = expr_grammar['Mul']
        Paren = expr_grammar['Paren']
        
        result = Expr("(1+2)*(3+4)")
        assert isinstance(result, Mul)
        assert isinstance(result.left, Paren)
        assert isinstance(result.right, Paren)


# =============================================================================
# Associativity Tests (Currently Skipped)
# =============================================================================

class TestAssociativity:
    """Test associativity rules."""
    
    def test_add_left_associative(self, expr_grammar):
        """1+2+3 should parse as (1+2)+3 with left associativity"""
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        Num = expr_grammar['Num']
        
        result = Expr("1+2+3")
        # With left associativity: (1+2)+3
        # Top should be Add with left=Add(1,2) and right=3
        assert isinstance(result, Add), f"Expected Add, got {type(result).__name__}"
        assert isinstance(result.left, Add), f"Expected left to be Add, got {type(result.left).__name__}"
        assert result.left.left.value == "1"
        assert result.left.right.value == "2"
        assert result.right.value == "3"
    
    def test_pow_right_associative(self, expr_grammar):
        """2^3^4 should parse as 2^(3^4) with right associativity"""
        Expr = expr_grammar['Expr']
        Pow = expr_grammar['Pow']
        
        result = Expr("2^3^4")
        # With right associativity: 2^(3^4)
        # Top should be Pow with left=2 and right=Pow(3,4)
        assert isinstance(result, Pow), f"Expected Pow, got {type(result).__name__}"
        assert result.left.value == "2"
        assert isinstance(result.right, Pow), f"Expected right to be Pow, got {type(result.right).__name__}"
        assert result.right.left.value == "3"
        assert result.right.right.value == "4"


# =============================================================================
# Identifier Expressions
# =============================================================================

class TestIdentifierExpressions:
    """Test expressions with identifiers."""
    
    def test_id_add(self, expr_grammar):
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        Id = expr_grammar['Id']
        
        result = Expr("x+y")
        assert isinstance(result, Add)
        assert isinstance(result.left, Id)
        assert result.left._text == "x"
        assert isinstance(result.right, Id)
        assert result.right._text == "y"
    
    def test_complex_with_ids(self, expr_grammar):
        """x+y*z should parse as x+(y*z)"""
        Expr = expr_grammar['Expr']
        Add = expr_grammar['Add']
        Mul = expr_grammar['Mul']
        Id = expr_grammar['Id']
        
        result = Expr("x+y*z")
        assert isinstance(result, Add)
        assert isinstance(result.left, Id)
        assert result.left._text == "x"
        assert isinstance(result.right, Mul)
        assert result.right.left._text == "y"
        assert result.right.right._text == "z"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])