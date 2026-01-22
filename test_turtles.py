"""Test pretty printing and source guard."""
from turtles import Rule, char, repeat, at_least, separator, either, optional, sequence
from turtles import get_all_rules

class MyParser(Rule):
    "Hello, "
    name: repeat[char['a-zA-Z'], at_least[1]]
    "!"

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

class NumId(Rule):
    id: either[char['0'] | sequence[char['1-9'], repeat[char['0-9']]]]

class Id(Rule):
    id: repeat[char['a-zA-Z0-9-'], at_least[1]]




class MyParser(Rule):
    "Hello, "
    name: repeat[char['a-zA-Z'], at_least[1]]
    "!"



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
# AST = either[Add, Mul, Pow, Group, Id, Num]
# Alternative: AST = either[Add, Mul, Pow, Group, Id, Num]


print("=== Pretty-printed grammars ===\n")
for rule in get_all_rules():
    print(rule)
    print()
