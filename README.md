# Turtles
[![PyPI version](https://img.shields.io/pypi/v/turtles.svg)](https://pypi.org/project/turtles/)
[![Python versions](https://img.shields.io/pypi/pyversions/turtles.svg)](https://pypi.org/project/turtles/)
[![CI](https://github.com/david-andrew/turtles/actions/workflows/test.yml/badge.svg)](https://github.com/david-andrew/turtles/actions/workflows/test.yml)

Turtles is a small Python DSL for writing parsers that feel like dataclasses:
you define a grammar as a collection of `Rule` classes, parse some input, and get back a hydrated object
you can inspect, transform, or serialize.

This is especially useful when you have a custom format (or “mostly structured” text) and want a real parser instead of a giant regex, or handrolled parser.

> NOTE: Implementation is still evolving. Please open an issue if you hit unexpected behavior.

## Install

```bash
pip install turtles
```

> Requires Python 3.12+. If you’re on Python <3.14, it’s recommended to add `from __future__ import annotations` at the top of your grammar modules so you can forward-reference rules (and define rules in any order).

## Quickstart

Define a grammar (in a `.py` file), parse input, and use the structured result.

```python
from turtles import Rule, char, repeat, at_least, separator

# define rules for our grammar
class Int(Rule, int):
    value: repeat[char["0-9"], at_least[1]]

class Float(Rule, float):
    whole: Int
    "."
    frac: Int

Number = Float | Int

class KV(Rule):
    key: repeat[char["a-zA-Z_"], at_least[1]]
    "="
    value: Number

class Row(Rule):
    items: repeat[KV, separator[" "], at_least[1]]


# parse some input with the grammar
src = "temp=21.5 humidity=45 retries=0"
row = Row(src)

# Work with hydrated objects
assert row.items[0].key == "temp"
assert row.items[0].value == 21.5

# Convert the whole parse result to plain Python containers
data = row.as_dict()
assert data == {
    "items": [
        {"key": "temp", "value": 21.5},
        {"key": "humidity", "value": 45},
        {"key": "retries", "value": 0},
    ]
}

# # Helpful while iterating on a grammar
print(repr(row))
# Row
# └── items: [3 items]
#     ├── [0]: KV
#     │   ├── key: temp
#     │   └── value: Float
#     │       ├── whole: Int
#     │       │   └── value: 21
#     │       └── frac: Int
#     │           └── value: 5
#     ├── [1]: KV
#     │   ├── key: humidity
#     │   └── value: Int
#     │       └── value: 45
#     └── [2]: KV
#         ├── key: retries
#         └── value: Int
#             └── value: 0
```

### Important notes

- Rules must be defined in a **real source file** (not a REPL / `exec`) because Turtles inspects source to build the grammar.
- Named fields (e.g. `key: ...`) become attributes on the hydrated result.
- Unnamed fields are anonymous and only used to guide parsing, but are omitted from the result.
- `optional[...]` and `Rule | None` captures are omitted from `.as_dict()` when absent.
- Repeats of terminals become strings; repeats of Rules become lists of hydrated Rule instances.

## Type Mixins

Rules can inherit from Python's built-in types (`int`, `str`, `float`, `bool`) to make parsed values behave like native types:

```python
from turtles import Rule, char, repeat, at_least, sequence

class Integer(Rule, int):
    value: '0' | sequence[char['1-9'], repeat[char['0-9']]]

result = Integer("42")
assert result == 42              # Compares as int
assert isinstance(result, int)   # Type checks pass
assert result + 8 == 50          # Arithmetic works
assert result.as_dict() == 42    # as_dict() returns the int value

# Fields are still accessible
assert result.value == "42"
```

This is useful when you want parsed numeric or string values to integrate seamlessly with Python code.

## Custom Converters

For more complex transformations, define a `__convert__` method to transform parsed results into any Python type:

```python
from turtles import Rule, char, repeat, at_least

class Point(Rule):
    x: repeat[char['0-9'], at_least[1]]
    ','
    y: repeat[char['0-9'], at_least[1]]
    
    def __convert__(self):
        return (int(self.x), int(self.y))

result = Point("10,20")
assert result == (10, 20)         # Compares as tuple
assert result.__class__ is tuple  # Type is tuple
assert result.as_dict() == (10, 20)

# Original fields still accessible
assert result.x == "10"
assert result.y == "20"
```

The converter runs after hydration, so all fields are populated before `__convert__` is called. You can convert to any type: tuples, dataclasses, named tuples, custom classes, etc.

```python
from dataclasses import dataclass
from turtles import Rule, char, repeat, at_least

@dataclass
class Coordinate:
    x: int
    y: int

class CoordRule(Rule):
    x: repeat[char['0-9'], at_least[1]]
    ','
    y: repeat[char['0-9'], at_least[1]]
    
    def __convert__(self):
        return Coordinate(int(self.x), int(self.y))

result = CoordRule("5,10")
assert result == Coordinate(5, 10)
```

## Parse errors

Turtles automatically outputs user-friendly modern-style error messages whenever an input fails to parse

```python
from turtles import ParseError

try:
    Row("not_a_kv_pair")
except ParseError as e:
    print(e)
```

Example output:

```text
Error: incomplete KV: missing key

    ╭─[test.py:1:1]
  1 | not_a_kv_pair
    · ┬           ╱╲
    · │           ╰─ expected "="
    · ╰─ Row started here
    ╰───
  help: The input appears incomplete. Try adding "=".
```

## Example grammars

The `turtles/examples/` directory contains complete grammar examples:

| File | Description |
|------|-------------|
| `semver.py` | Semantic versioning (`SemVer("1.2.3-alpha.1+build.5")`) |
| `json_toy.py` | Minimal JSON subset (good for learning) |
| `json.py` | Full RFC 8259 JSON grammar |
| `csv.py` | RFC 4180 CSV grammar |

The test suite is also a great source of patterns:

| File | Coverage |
|------|----------|
| `tests/test_hydration.py` | Field captures, repeats, optionals, unions, mixins, converters |
| `tests/test_as_dict.py` | Serialization with `.as_dict()` |
| `tests/test_csv.py` | Real-world CSV parsing scenarios |

> Contributions welcome! Open a PR with new example grammars.

## More Examples

### Semantic Versions

```python
from turtles import Rule, repeat, char, separator, sequence, at_least

class NumId(Rule):
    id: '0' | sequence[char['1-9'], repeat[char['0-9']]]

class Id(Rule):
    id: repeat[char['a-zA-Z0-9-'], at_least[1]]

class Prerelease(Rule):
    "-"
    ids: repeat[Id, separator['.'], at_least[1]]

class Build(Rule):
    "+"
    ids: repeat[Id, separator['.'], at_least[1]]

class SemVer(Rule):
    major: NumId
    "."
    minor: NumId
    "."
    patch: NumId
    prerelease: Prerelease | None
    build: Build | None


result = SemVer('1.2.3-alpha+build.5')

assert result.major.id == '1'
assert result.minor.id == '2'
assert result.patch.id == '3'
assert result.prerelease.ids[0].id == 'alpha'
assert result.build.ids[0].id == 'build'
assert result.build.ids[1].id == '5'
```


### Toy JSON Parser

```python
from turtles import Rule, char, repeat, at_least, separator

class Whitespace(Rule):
    repeat[char[' \t\n\r']]

class Comma(Rule):
    Whitespace
    ','
    Whitespace

class JNull(Rule):
    "null"

class JBool(Rule):
    value: "true" | "false"

class JNumber(Rule):
    value: repeat[char['0-9'], at_least[1]]

class JString(Rule):
    '"'
    value: repeat[char["A-Za-z0-9 !#$%&'()*+,-./:;<=>?@^_`{|}~"]]
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

# Rule union - JSONValue can be any of these types
JSONValue = JNull | JBool | JNumber | JString | JArray | JObject


src = '{ "A": { "a": null }, "B": [ true, false, 1, 2, 3 ] }'
result = JSONValue(src)

assert isinstance(result, JObject)
assert len(result.pairs) == 2
assert result.pairs[0].key.value == "A"
assert isinstance(result.pairs[1].value, JArray)

# Tree visualization
print(repr(result))

# Convert to plain Python containers
result.as_dict()
```

> **Note:** This is a simplified grammar. See `turtles/examples/json.py` for a complete RFC 8259 implementation with floats, escapes, and full unicode support.


## DSL Reference

| Construct | Description | Example |  BNF Equivalent |
|-----------|-----|-------------|---------|
| `"literal"` | Match exact string | `"hello"` | `"hello"` | 
| `char['a-z']` | Character class | `char['0-9A-Fa-f']` | `[0-9A-FA-F]` |
| `repeat[X]` | Zero or more | `repeat[char['0-9']]` | `[0-9]*` |
| `repeat[X, at_least[n]]` | At least n | `repeat[char['a-z'], at_least[1]]` |  `[a-z]+` / `[a-z]{1,}` |
| `repeat[X, at_most[n]]` | At most n | `repeat[Int, at_most[10]]` |  `Int{0,10}` |
| `repeat[X, exactly[n]]` | Exactl n | `repeat[Int, exactly[3]]` |  `Int{3,3}` |
| `repeat[X, separator[Y]]` | Separated list | `repeat[Item, separator[',']]` |  `Item (',' Item)*` |
| `optional[X]` | Zero or one | `optional[Sign]` |  `Sign?` |
| `X \| None` | Optional rule | `prefix: Sign \| None` |  `Sign?` |
| `A \| B \| C` |  Rule union | `Value = Int \| Float \| String` | `Int \| Float \| String` |
| `sequence[A, B]` | Explicit sequence | `sequence[char['1-9'], repeat[char['0-9']]]` |  `[1-9] [0-9]` |
| `field: X` |  Named capture | `value: repeat[char['0-9']]` | — |
| `Rule, int` | Type mixin | `class Num(Rule, int): ...` | — |
| `__convert__` | Custom converter | `def __convert__(self): return int(self.x)` | — |

## Backend

Turtles uses a GLL (Generalized LL) parser backend.
GLL is a general parsing algorithm for **arbitrary context-free grammars**, including grammars with ambiguity and left recursion, while still keeping the implementation reasonably small.

At a high level, parsing works like this:

1. The `Rule` class body is inspected and compiled into a context-free grammar.
1. The GLL parser runs against the input and produces a compact shared parse forest.
1. Turtles extracts a parse tree (with optional disambiguation rules like precedence/associativity) and **hydrates** it back into instances of your `Rule` classes.

Read more: https://dotat.at/tmp/gll.pdf

## Looking for the old Turtles?
⚠️ The turtles project has been rebooted. `v2.0.0` and onward will not be compatible with the original `v1.0.0` release. If you are looking for the original project, see [Roguelazer/turtles](https://github.com/Roguelazer/turtles). 
