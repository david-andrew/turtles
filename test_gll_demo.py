"""
Demonstration of the GLL Parser in turtles.

This file shows the parser working with:
1. Simple literal matching
2. Character classes and repetition
3. Rule references
4. Left-recursive grammars (expression parsing)
5. Disambiguation via precedence and associativity
6. Semantic version parsing

NOTE: Rules are defined INSIDE functions to demonstrate that the parser
correctly discovers locally-scoped rules. This wasn't possible before!
"""
from textwrap import indent
from turtles import Rule, RuleUnion, char, repeat, at_least, exactly, separator, either, sequence, optional


def repr_result(result, indent_str='  '):
    print(indent(repr(result), indent_str))

# =============================================================================
# Example 1: Simple Greeting Parser
# =============================================================================

def demo_greeting():
    """Rules defined inside a function work!"""
    
    class Greeting(Rule):
        "Hello, "
        name: repeat[char['a-zA-Z'], at_least[1]]
        "!"
    
    print("=" * 60)
    print("Example 1: Simple Greeting Parser")
    print("=" * 60)
    print(Greeting)
    # print("Grammar: Greeting ::= 'Hello, ' name:[a-zA-Z]+ '!'")
    # print("(Rules defined INSIDE this function)")
    print()
    
    result = Greeting("Hello, World!")
    print(f"  Input: 'Hello, World!'")
    print(f"  Parsed: {result}")
    print(f"  name = '{result.name}'")
    repr_result(result)
    print()
    
    result = Greeting("Hello, Alice!")
    print(f"  Input: 'Hello, Alice!'")
    print(f"  name = '{result.name}'")
    repr_result(result)
    print()


# =============================================================================
# Example 2: Number Parser
# =============================================================================

def demo_number():
    """Another function-scoped grammar."""
    
    class Number(Rule):
        digits: repeat[char['0-9'], at_least[1]]
    
    print("=" * 60)
    print("Example 2: Number Parser")
    print("=" * 60)
    print(Number)
    # print("Grammar: Number ::= digits:[0-9]+")
    print()
    
    for test in ["42", "12345", "0"]:
        result = Number(test)
        print(f"  Input: '{test}' -> digits='{result.digits}'")
        repr_result(result)
    print()


# =============================================================================
# Example 3: Math Expressions with Left Recursion
# =============================================================================

def demo_expressions():
    """Expression grammar with left recursion - all defined inside function."""
    
    class Num(Rule):
        value: repeat[char['0-9'], at_least[1]]

    class Add(Rule):
        left: Expr
        char['+-']
        right: Expr

    class Mul(Rule):
        left: Expr
        char['*/']
        right: Expr

    class Paren(Rule):
        '('
        inner: Expr
        ')'

    # Create the union - this also works inside a function!
    Expr = Add | Mul | Paren | Num

    # Disambiguation
    Expr.precedence = [Mul, Add]
    Expr.associativity = {Add: 'left', Mul: 'left'}

    print("=" * 60)
    print("Example 3: Math Expressions (Left-Recursive Grammar)")
    print("=" * 60)
    print(Expr)
    print(Add)
    print(Mul)
    print(Paren)
    print(Num)
    print()
    print("Note: All rules AND the RuleUnion defined inside this function!")
    print()
    
    test_cases = ["42", "1+2", "3*4", "1+2*3", "(1+2)*3", "1+2+3"]
    
    for test in test_cases:
        result = Expr(test)
        print(f"  '{test}' -> {type(result).__name__}: {result}")
        # print(indent(tree_string(result), '  '))
        repr_result(result)
        print()
    print()




