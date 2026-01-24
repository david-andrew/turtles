"""
TODO: write out tests for handling ambiguous grammars
"""

from turtles import Rule, char, repeat, at_least, exactly, separator, either, sequence, optional

def todo_expr_example():
    class Num(Rule):
        value: repeat[char['0-9'], at_least[1]]
    
    class Id(Rule):
        id: sequence[char['a-zA-Z_'], repeat[char['a-zA-Z0-9_']]]

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

    # Create the union - this also works inside a function!
    Expr = Add | Mul | Pow | Paren | Num | Id

    # Set Disambiguation Rules
    Expr.precedence = [Pow, Mul, Add]
    Expr.associativity = {Add: 'left', Mul: 'left', Pow: 'right'} #TODO: associativity is currently not working (has no effect)

    # Test cases
    test_cases = ["42", "1+2", "3*4", "1+2*3", "1*2+3", "(1+2)*3", "1+2+3", "1^2^3", "1+2*3^4", "x+y*z^w"]
    
    # TODO: have test cases look for correct precedence and associativity in tree results
    for test in test_cases:
        result = Expr(test)
        print(f"  '{test}' -> {type(result).__name__}: {result}")
        print(repr(result))
        print()
    print()

if __name__ == "__main__":
    todo_expr_example()