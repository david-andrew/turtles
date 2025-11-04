# Turtles
Parsing made easy in python. Also serves as a more human readable replacement for regex.

## Frontend
Parser grammars are defined analogously to dataclasses, and then the parse result is returned in the same structure.

```python
from turtles import Rule, char

class MyParser(Rule):
    "Hello, "
    name: repeat(char('a-zA-Z'), at_least=1)
    "!"

result = MyParser('Hello, World!')
print(result.name)  # 'World'

result = MyParser('something else')  # would raise a parse failure
```

todo: explain more...
- basic structure of rule classes, named vs unnamed, captured vs uncaptured members, etc.
- combining rules `A | B`, nesting, recursion, etc.
- helper functions `sequence`, `repeat`, `char`, `optional`, `either`

Example of grammar for parsing semantic versions:
```python
from turtles import Rule, repeat, char 

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
    ids: repeat(Id, separator='.', at_least=1)
    def __str__(self): return f"-{'.'.join(map(str, self.ids))}"

class Build(Rule):
    "+"
    ids: repeat(Id, separator='.', at_least=1)
    def __str__(self): return f"+{'.'.join(map(str, self.ids))}"

class NumId(Rule):
    id: either('0', (char('1-9'), repeat(char('0-9'))))
    def __str__(self): return str(self.id)

class Id(Rule):
    id: repeat(char('a-zA-Z0-9-'), at_least=1)
    def __str__(self): return str(self.id)

# parse a semver
result = SemVer('1.2.3-alpha+3.14')

# results are in a convenient format
result.major # NumId(id='1')
result.minor # NumId(id='2')
result.patch # NumId(id='3')
result.prerelease # Prerelease(ids=['alpha'])
result.build # Build(ids=['3', '14'])
```

## Backend
WIP. goal is to support multiple parser backends. probably start with `lark`. Also probably include a pure python GLL backend