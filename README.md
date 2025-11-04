# Turtles
Parsing made easy in python. Also serves as a more human readable replacement for regex

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

result = Hello('something else')  # would raise a parse failure
```

todo: explain more...
- basic structure of rule classes, named vs unnamed, captured vs uncaptured members, etc.
- combining rules `A | B`, nesting, recursion, etc.
- helper functions `sequence`, `repeat`, `char`, `optional`, `either`

## Backend
WIP. goal is to support multiple parser backends. probably start with `lark`. Also probably include a pure python GLL backend