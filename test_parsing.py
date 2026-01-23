# from __future__ import annotations

from turtles import (
    Rule, char,
    repeat, either, sequence, optional, 
    at_least, at_most, exactly, separator,
)

def test_hello():
    class MyParser(Rule):
        "Hello, "
        name: repeat[char['a-zA-Z'], at_least[1]]
        "!"

    result = MyParser('Hello, World!')
    assert result.name == 'World'


def test_semver():
    class SemVer(Rule):
        major: NumId
        "."
        minor: NumId
        "."
        patch: NumId
        prerelease: Prerelease|None
        build: Build|None

    class Prerelease(Rule):
        "-"
        ids: repeat[Id, separator['.'], at_least[1]]

    class Build(Rule):
        "+"
        ids: repeat[Id, separator['.'], at_least[1]]

    # Note about mixins: basically it is just a post process step that converts the parsed string to that type. `int` can just take the value directly, though other types (e.g. bool) would need a dedicated parse function.
    #      then the converted value exists in parallel to the rule dataclass object. E.g. NumId behaves like NumId & int
    class NumId(Rule, int):
        id: either[char['0'] | sequence[char['1-9'], repeat[char['0-9']]]]

    class Id(Rule, str):
        id: repeat[char['a-zA-Z0-9-'], at_least[1]]
    

    result = SemVer('1.2.3-alpha+3.14')
    assert result.major == 1
    assert result.minor == 2
    assert result.patch == 3
    assert result.prerelease is not None
    assert result.prerelease.ids == ['alpha']
    assert result.build is not None
    assert result.build.ids == ['3', '14']


def test_expressions():
    class Add(Rule):
        left: AST
        char[r'+\-']
        right: AST
    class Mul(Rule):
        left: AST
        char['*/']
        right: AST
    class Pow(Rule):
        left: AST
        '^'
        right: AST
    class Group(Rule):
        '('
        expr: AST
        ')'
    class Id(Rule):
        id: repeat[char['a-zA-Z0-9_'], at_least[1]]
    class Num(Rule):
        num: repeat[char['0-9'], at_least[1]]

    AST = Add | Mul | Pow | Group | Id | Num
    # TODO: need a way to specify precedence and associativity in the DSL
    """
    perhaps something like this (but open to alternatives)
    AST.precedence = [Pow, Mul, Add] 
    Add.associativity = 'left'  # perhaps actually associativity is specified as tags in the rule class?
    Mul.associativity = 'left'
    Pow.associativity = 'right'
    """

    result = AST('1+2*3^4')
    assert isinstance(result, Add)
    assert isinstance(result.left, Num)
    assert result.left == '1'
    assert isinstance(result.right, Mul)
    assert isinstance(result.right.left, Num)
    assert result.right.left == '2'
    assert isinstance(result.right.right, Pow)
    assert isinstance(result.right.right.left, Num)
    assert result.right.right.left == '3'
    assert isinstance(result.right.right.right, Num)
    assert result.right.right.right == '4'

    result.left



# def test_expressions2():

# Expression parsing with left recursion
class Num(Rule):
    num: repeat[char['0-9'], at_least[1]]
class Add(Rule):
    left: Expr
    char['+-']
    right: Expr
Expr = Add | Num
Expr.precedence = [Add]
Expr.associativity = {Add: 'left'}
result = Expr("1+2")  # Returns Add instance
print(result)


# # possible example of a minimal parser without needing to make a class
# word_parser = repeat[char['a-zA-Z'], at_least[1]]
# result = word_parser('apple')

# # TBD exactly how comparing would work, but I want it to be flexible/convenient for the user
# assert result.items == ['a', 'p', 'p', 'l', 'e']
# assert result == 'apple'


# if __name__ == "__main__":
#     # test_hello()
#     # test_semver()
#     # test_expressions()
#     test_expressions2()