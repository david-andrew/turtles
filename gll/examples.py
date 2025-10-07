from easygrammar import Rule, Annotated, repeat, char, either, optional, sequence



######################  [Misc]  ######################

class ClassA(Rule):
    '('
    a:int
    ')'


class Test(Rule):
    a: Annotated[int, ('(', ')')]
    def __init__(self, a:int): ...
a = Test('()')
a.a

class ClassB(Rule):
    # ClassA("(5)")
    b:str

class ClassC:
    '('
    a: int
    ')'

c = ClassB('')
c.b

class t(Rule): ...

print(ClassA | ClassB)
print(ClassA | "ClassB")
print(t| 'ajhdgajhdgjag' | 'b' | ClassB)
print(ClassA | ("ClassB", "ClassC"))
# -> "Custom OR on classes: ClassA | ClassB"

# Example: demonstrate collected sequences for subclasses
print("ClassA sequence:", getattr(ClassA, "_sequence", None))
print("ClassB sequence:", getattr(ClassB, "_sequence", None))





######################  [Semantic versioning]  ######################

# class Int(Rule):
#    # 0 or non-zero unsigned
#    i: Annotated[int, (Char('0') | (Char('1-9'), Star(Char('0-9'))))]
#    def __str__(self): return str(self.i)

# class Id(Rule):
#    id: Plus(Char('a-zA-Z0-9-')) | Int
#    def __str__(self): return str(self.id)

# class Prerelease(Rule):
#    '-'
#    ids: Annotated[list[Id], SepBy(Id, by='.')]
#    def __str__(self): return f"-{'.'.join(map(str, self.ids))}"

# class Build(Rule):
#    '+'
#    ids: Annotated[list[Id], SepBy(Id, by='.')]
#    def __str__(self): return f"+{'.'.join(map(str, self.ids))}"

# class SemVer(Rule):
#    major: Int
#    '.'
#    minor: Int
#    '.'
#    patch: Int
#    prerelease: Prerelease | None
#    build: Build | None

#    def __str__(self):
#        return f"{self.major}.{self.minor}.{self.patch}{self.prerelease or ''}{self.build or ''}"

# semver = makeparser(SemVer, allow_ws=False)  # manual whitespace by default

# # Happy paths
# t0: SemVer = semver("0.0.0")
# t1 = semver("1.2.3-alpha.1+build.1")
# t2 = semver("1.0.0-rc.1+exp.sha.5114f85")
# t3 = semver("1.0.0+build.1")

# # Non-throwing parse
# r = semver("1.2.x", throw=False)  # -> SemVer | ParseError



"""
<valid semver> ::= <version core>
                 | <version core> "-" <pre-release>
                 | <version core> "+" <build>
                 | <version core> "-" <pre-release> "+" <build>
<version core> ::= <major> "." <minor> "." <patch>
<major> ::= <numeric identifier>
<minor> ::= <numeric identifier>
<patch> ::= <numeric identifier>
<pre-release> ::= <dot-separated pre-release identifiers>
<dot-separated pre-release identifiers> ::= <pre-release identifier>
                                          | <pre-release identifier> "." <dot-separated pre-release identifiers>
<build> ::= <dot-separated build identifiers>
<dot-separated build identifiers> ::= <build identifier>
                                    | <build identifier> "." <dot-separated build identifiers>
<pre-release identifier> ::= <alphanumeric identifier>
                           | <numeric identifier>
<build identifier> ::= <alphanumeric identifier>
                     | <digits>
<alphanumeric identifier> ::= <non-digit>
                            | <non-digit> <identifier characters>
                            | <identifier characters> <non-digit>
                            | <identifier characters> <non-digit> <identifier characters>
<numeric identifier> ::= "0"
                       | <positive digit>
                       | <positive digit> <digits>
<identifier characters> ::= <identifier character>
                          | <identifier character> <identifier characters>
<identifier character> ::= <digit>
                         | <non-digit>
<non-digit> ::= <letter>
              | "-"
<digits> ::= <digit>
           | <digit> <digits>
<digit> ::= "0"
          | <positive digit>
<positive digit> ::= "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
<letter> ::= "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J"
           | "K" | "L" | "M" | "N" | "O" | "P" | "Q" | "R" | "S" | "T"
           | "U" | "V" | "W" | "X" | "Y" | "Z" | "a" | "b" | "c" | "d"
           | "e" | "f" | "g" | "h" | "i" | "j" | "k" | "l" | "m" | "n"
           | "o" | "p" | "q" | "r" | "s" | "t" | "u" | "v" | "w" | "x"
           | "y" | "z"
"""




Id = {
    'id': repeat(char('a-zA-Z0-9-'), at_least=1)
}

class Id(Rule):
    id: Annotated[str, repeat(char('a-zA-Z0-9-'), at_least=1)]
    def __str__(self): return str(self.id)

class NumId(Rule):
    id: Annotated[str, either('0', (char('1-9'), repeat(char('0-9'))))]
    def __str__(self): return str(self.id)

class Build(Rule):
    "+"
    ids: Annotated[list[Id], repeat(Id, separator='.', at_least=1)]
    def __str__(self): return f"+{'.'.join(map(str, self.ids))}"

class Prerelease(Rule):
    "-"
    ids: Annotated[list[Id], repeat(Id, separator='.', at_least=1)]
    def __str__(self): return f"-{'.'.join(map(str, self.ids))}"

class SemVer(Rule):
    major: NumId
    "."
    minor: NumId
    "."
    patch: NumId
    prerelease: Prerelease|None
    build: Build|None




"""
Notes:
- deferred type annotations are a pain.
  ---> especially if you want to use them in one of the type constructor functions (repeat, either, optional, sequence, etc.)
  ---> because they are regular functions, the type has to exist at function call time, which means the type has to have been declared above the current spot
- nut if we go back to everything be generic type annotations, we loose the ability to pass arguments by name, e.g. repeat(R, separator='.', at_least=1, ...)
"""

#######################  [Arithmetic]  ########################



#######################  [JSON]  ########################


