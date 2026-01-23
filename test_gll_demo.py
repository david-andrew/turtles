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


# =============================================================================
# Example 4: Semantic Version Parser
# =============================================================================

def demo_version():
    """Version parsing grammar inside function."""
    
    class Version(Rule):
        major: repeat[char['0-9'], at_least[1]]
        '.'
        minor: repeat[char['0-9'], at_least[1]]
        '.'
        patch: repeat[char['0-9'], at_least[1]]
    
    print("=" * 60)
    print("Example 4: Semantic Version Parser")
    print("=" * 60)
    print(Version)
    # print("Grammar: Version ::= major:[0-9]+ '.' minor:[0-9]+ '.' patch:[0-9]+")
    print()
    
    for test in ["1.0.0", "2.3.4", "10.20.30"]:
        result = Version(test)
        print(f"  '{test}' -> major={result.major}, minor={result.minor}, patch={result.patch}")
        repr_result(result)
    print()


# =============================================================================
# Example 5: Identifier Parser
# =============================================================================

def demo_identifier():
    """Identifier grammar inside function."""
    
    class Identifier(Rule):
        first: char['a-zA-Z_']
        rest: repeat[char['a-zA-Z0-9_']]
    
    print("=" * 60)
    print("Example 5: Identifier Parser")
    print("=" * 60)
    print(Identifier)
    # print("Grammar: Identifier ::= [a-zA-Z_] [a-zA-Z0-9_]*")
    print()
    
    for test in ["x", "foo", "my_var", "_private", "camelCase123"]:
        result = Identifier(test)
        print(f"  '{test}' -> first='{result.first}', rest='{result.rest}'")
        repr_result(result)
    print()


# =============================================================================
# Example 6: Nested Function Scopes
# =============================================================================

def demo_nested():
    """Show that even nested function scopes work."""
    
    def inner_scope():
        class Inner(Rule):
            tag: repeat[char['a-z'], at_least[1]]
        
        return Inner("hello")
    
    print("=" * 60)
    print("Example 6: Nested Function Scopes")
    print("=" * 60)
    print("Rules can be defined in nested functions too!")
    print()
    
    result = inner_scope()
    print(f"  Inner rule from nested function: tag='{result.tag}'")
    repr_result(result)
    print()


# =============================================================================
# Example 7: JSON Parsers
# =============================================================================

def demo_simple_json():
    """JSON parser"""

    class JNull(Rule):
        "null"

    class JBool(Rule):
        value: either["true", "false"]

    class JNumber(Rule):
        value: repeat[char['0-9'], at_least[1]]

    class JString(Rule):
        '"'
        value: repeat[char[r" !#$%&'()*+,\-./0-9:;<=>?@A-Z[]^_`a-z{|}~"]]
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

    print("=" * 60)
    print("Example 7: Simple JSON Parser")
    print("=" * 60)
    print(JSONValue)
    print(JNull)
    print(JBool)
    print(JNumber)
    print(JString)
    print(JArray)
    print(JObject)
    print(Pair)
    print()

    for test in [
        "null", "true", "false", "123", '"hello"', '[1,2,3]', '{"a":1,"b":2}',
        "[]", "{}", '[1,2,3]', '{"a":1,"b":2,"c":3}',
        '{"glossary":{"title":"example glossary","GlossDiv":{"title":"S","GlossList":{"GlossEntry":{"ID":"SGML","SortAs":"SGML","GlossTerm":"Standard Generalized Markup Language","Acronym":"SGML","Abbrev":"ISO 8879:1986","GlossDef":{"para":"A meta-markup language, used to create markup languages such as DocBook.","GlossSeeAlso":["GML","XML"]},"GlossSee":"markup"}}}}}',
    ]:
        result = JSONValue(test)
        print(f"  '{test}' -> {type(result).__name__}: {result}")
        repr_result(result)
        print()
    print()




def demo_full_json():
    """Full JSON parser"""
    class Whitespace(Rule):
        repeat[char['\x20\t\n\r']]

    class Comma(Rule):
        Whitespace
        ','
        Whitespace

    class JNull(Rule):
        "null"

    class JBool(Rule):
        value: either["true", "false"]

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


    class SimpleEscape(Rule):
        ch: either[r"\\", r"\"", r"\/", r"\b", r"\f", r"\n", r"\r", r"\t"]
    
    class HexEscape(Rule):
        ch: sequence[r"\u", repeat[char['0-9a-fA-F'], exactly[4]]]
    
    Escape = SimpleEscape | HexEscape

    class JString(Rule):
        '"'
        value: repeat[char['\x20-\x21\x23-\x5B\x5D-\U0010FFFF'] | Escape]
        '"'

    class JArray(Rule):
        '['
        Whitespace
        items: repeat[JSONValue, separator[Comma]]
        Whitespace
        ']'

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
    
    class JSON(Rule):
        Whitespace
        value: JSONValue
        Whitespace

    JSONValue = JNull | JBool | JNumber | JString | JArray | JObject


    print("=" * 60)
    print("Example 7: Full JSON Parser")
    print("=" * 60)
    print(JSONValue)
    print(JSON)
    print(Whitespace)
    print(Comma)
    print(JNull)
    print(JBool)
    print(JNumber)
    print(JString)
    print(JArray)
    print(JObject)
    print(Pair)
    print()

    for test in [
        'null', 'true', 'false', '123', '"hello"', '[1, 2, 3]', '{"a":1, "b":2}',
        '-123', '1.23', '1.23e4', '1.23e-4', '1.23e+4', '1E9', '2e-9', '1E+9',
        '""', '"simple"', '"with space"', r'"quote \""', r'"backslash \\"', r'"slash \/"', r'"controls: \b\f\n\r\t"',
        r'"unicode: \u0041\u03BB"', '"raw unicode: λ你好"',
        '[]', '[ 1, 2, 3 ]', '[null, true, false, 1, 2, 3]', '[1, [2, 3], {"a":4}]', 
        '{}', '{"a" : 1}', '{"a": 1, "b": [true, false], "c": {"d": "x"}}', '{ "a" : [1, 2, 3], "b" : { "c": null } }',
        '{ "glossary": { "title": "example glossary", "GlossDiv": { "title": "S", "GlossList": { "GlossEntry": { "ID": "SGML", "SortAs": "SGML", "GlossTerm": "Standard Generalized Markup Language", "Acronym": "SGML", "Abbrev": "ISO 8879:1986", "GlossDef": { "para": "A meta-markup language, used to create markup languages such as DocBook.", "GlossSeeAlso": ["GML", "XML"] }, "GlossSee": "markup" } } } } }',
    ]:
        result = JSON(test)
        print(f"  '{test}' -> {type(result).__name__}: {result}")
        repr_result(result)
        print()
    print()



# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print()
    print("GLL Parser Demonstration")
    print("========================")
    print()
    print("All grammars are defined INSIDE their test functions!")
    print("This shows the improved scoping support for rule discovery.")
    print()
    
    demo_greeting()
    demo_number()
    demo_expressions()
    demo_version()
    demo_identifier()
    demo_nested()
    demo_simple_json()
    demo_full_json()
    
    print("=" * 60)
    print("All demonstrations completed successfully!")
    print("=" * 60)
