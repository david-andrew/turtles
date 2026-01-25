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
from turtles import Rule, char, repeat, at_least, optional, separator


class Int(Rule):
    value: repeat[char["0-9"], at_least[1]]


class Float(Rule):
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


row = Row("temp=21.5 humidity=45 retries=0")

# Work with hydrated objects
assert row.items[0].key == "temp"
assert row.items[0].value.as_dict() == {"whole": {"value": "21"}, "frac": {"value": "5"}}

# Convert the whole parse result to plain Python containers
data = row.as_dict()
assert data == {
    "items": [
        {"key": "temp", "value": {"whole": {"value": "21"}, "frac": {"value": "5"}}},
        {"key": "humidity", "value": {"value": "45"}},
        {"key": "retries", "value": {"value": "0"}},
    ]
}

# Helpful while iterating on a grammar
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

### A couple important notes

- Rules must be defined in a **real source file** (not a REPL / `exec`) because Turtles inspects source to build the grammar.
- Named fields (e.g. `key: ...`) become attributes on the hydrated result.
- Unnamed fields are anonymous and only used to guide parsing, but are omitted from the result.
- `optional[...]` and `Rule | None` captures are omitted from `.as_dict()` when absent.
- Repeats of terminals become strings; repeats of Rules become lists of hydrated Rule instances.

### Parse errors

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

## Example grammars (in this repo)

- `turtles/examples/semver.py`: semantic version parsing (`SemVer("1.2.3-alpha.1+build.5")`)
- `turtles/examples/json_toy.py`: a small JSON subset (good for learning the DSL)
- `turtles/examples/json.py`: a fuller RFC 8259 JSON grammar
- `turtles/examples/csv.py`: RFC 4180 compliant CSV grammar (untested)

> Feel free to open a pull request with any example grammars that might be valuable additions

The test suite is also a great source of patterns:

- `tests/test_hydration.py`: coverage for hydration/captures across DSL constructs
- `tests/test_as_dict.py`: examples of `.as_dict()` on ad-hoc + example grammars

## Examples
### Semantic Versions
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

# convert to plain Python containers
result.as_dict()
```


### Toy JSON parser
```python
from turtles import Rule, char, repeat, at_least, either, separator

class Whitespace(Rule):
    repeat[char['\x20\t\n\r']]

class Comma(Rule):
    Whitespace
    ','
    Whitespace

class JNull(Rule):
    "null"

class JBool(Rule):
    value: either[r"true", r"false"]

class JNumber(Rule):
    value: repeat[char['0-9'], at_least[1]]

class JString(Rule):
    '"'
    value: repeat[char[r"A-Za-z0-9 !#$%&'()*+,\-./:;<=>?@[]^_`{|}~"]]
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

JSONValue = JNull | JBool | JNumber | JString | JArray | JObject


src = '{ "A": { "a": null }, "B": [ true, false, 1, 2, 3 ], "C": [ { "d": [ 4, 5, 6 ] } ] }'
result = JSONValue(src)
print(repr(result)) # print out the parse result displaying the tree structure
assert isinstance(result, JObject)
assert len(result.pairs) == 3
assert result.pairs[0].key == '"A"'
assert isinstance(result.pairs[1].value, JArray)
# etc. etc.

# convert to plain Python containers
result.as_dict()
```
> NOTE: this grammar is missing a lot of features from a full json grammar:
> - doesn't support for float or scientific notation numbers
> - allows invalid integer numbers with leading zeros
> - doesn't support sign prefix (`+`/`-`) for numbers 
> - doesn't support string escapes, nor the vast majority of valid unicode characters


## Backend
Turtles uses a GLL (Generalized LL) parser backend.
GLL is a general parsing algorithm for **arbitrary context-free grammars**, including grammars with ambiguity and left recursion, while still keeping the implementation reasonably small.

At a high level, parsing works like this:

1. The `Rule` class body is inspected and compiled into a context-free grammar.
1. The GLL parser runs against the input and produces a compact shared parse forest.
1. Turtles extracts a parse tree (with optional disambiguation rules like precedence/associativity) and **hydrates** it back into instances of your `Rule` classes.

Read more: 

## Looking for the old Turtles?
⚠️ The turtles project has been rebooted. `v2.0.0` and onward will not be compatible with the original `v1.0.0` release. If you are looking for the original project, see [Roguelazer/turtles](https://github.com/Roguelazer/turtles). 
