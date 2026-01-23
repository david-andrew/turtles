# Turtles
Parsing made easy in python. Also serves as a more human readable replacement for regex.

## Frontend
Parser grammars are defined analogously to dataclasses, and then the parse result is returned in the same structure.

```python
from turtles import Rule, char, repeat, at_least

class MyParser(Rule):
    "Hello, "
    name: repeat[char['a-zA-Z'], at_least[1]]
    "!"

result = MyParser('Hello, World!')
print(result.name)  # 'World'


# invalid input
result = MyParser('something else')
# Error: ParseError: expected "Hello, " at position 0
# 
#     ╭─[<input>:1:1]
#   1 | something else
#     · ────┬────
#     ·     ╰─ expected literal string 'Hello, ' to begin input
#     ╰───
#   help: the input should start with the literal string "Hello, "
# 
```

todo: explain more...
- basic structure of rule classes, named vs unnamed, captured vs uncaptured members, etc.
- combining rules `A | B`, nesting, recursion, etc.
- helper functions `sequence`, `repeat`, `char`, `optional`, `either`

Example of grammar for parsing semantic versions:
```python
from turtles import Rule, repeat, char, separator, at_least

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
    id: repeat[char['a-zA-Z0-9'], at_least[1]]

# parse a semver
result = SemVer('1.2.3-alpha+3.14')

# results are in a convenient format
result.major # NumId(id='1')
result.minor # NumId(id='2')
result.patch # NumId(id='3')
result.prerelease # Prerelease(ids=['alpha'])
result.build # Build(ids=['3', '14'])
```


Toy JSON parser
```python
class JNull(Rule):
    "null"

class JBool(Rule):
    value: either["true", "false"]

class JNumber(Rule):
    value: repeat[char['0-9'], at_least[1]]

class JString(Rule):
    '"'
    value: repeat[char['a-zA-Z0-9_']]
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


result = JSONValue('{"A":{"a":null},"B":[true,false,1,2,3],"C":[{"d":[4,5,6]}]}')
print(repr(result)) # print out the parse result displaying the tree structure
assert isinstance(result, JObject)
assert len(result.pairs) == 3
assert result.pairs[0].key == '"A"'
# etc. etc.
```

## Backend
WIP. goal is to support multiple parser backends. probably start with `lark`. Also probably include a pure python GLL backend

## Looking for the old Turtles?
⚠️ The turtles project has been rebooted. `v2.0.0` and onward will not be compatible with the original `v1.0.0` release. If you are looking for the original project, see [Roguelazer/turtles](https://github.com/Roguelazer/turtles). 