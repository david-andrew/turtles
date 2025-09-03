"""
Mostly just detailing how I think a frontend should work, but need to figure out how to actually implement it this way
"""
from dataclasses import dataclass
from typing import dataclass_transform, Literal
from abc import ABC

@dataclass_transform()
class Rule(ABC):
    """initialize a token subclass as a dataclass"""
    def __init_subclass__(cls: 'type[Rule]', **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(cls)#, repr=False)

    # def __repr__(self) -> str:
    #     dict_str = ", ".join([f"{k}=`{v}`" for k, v in self.__dict__.items()])
    #     return f"{self.__class__.__name__}({dict_str})"


############ Examples proposed by chatgpt #############
from typing import Annotated, Optional, Union
from niceparse import (
    Rule, makeparser,                     # core
    Char, Range, By, Plus, Star, Repeat,  # scannerless atoms & repetition
    SepBy, Label,                         # structure & diagnostics
    Join, AsInt, AsFloat, UnescapeJson, Map  # transforms
)



################### [Semantic versioning] ###############
class Int(Rule):
    # int := '0' | NZDigit Digit*
    i: Annotated[int,
        ("0" | (Char['1-9'], Star[Char['0-9']])),
        Join, AsInt
    ]
    def __str__(self) -> str: return str(self.i)

class Id(Rule):
    # id := (letters|'-')+ | Int   (spec allows leading zeros only for non-int)
    id: Annotated[Union[str, Int],
        (Plus[Char['a-zA-Z0-9-']], Join) | Int
    ]
    def __str__(self) -> str: return str(self.id)

class Prerelease(Rule):
    "-"
    ids: Annotated[list[Id], SepBy(Id, by=By["."])]
    def __str__(self) -> str: return "-" + ".".join(map(str, self.ids))

class Build(Rule):
    "+"
    ids: Annotated[list[Id], SepBy(Id, by=By["."])]
    def __str__(self) -> str: return "+" + ".".join(map(str, self.ids))

class SemVer(Rule):
    major: Annotated[Int,     Label("major")]
    "."
    minor: Annotated[Int,     Label("minor")]
    "."
    patch: Annotated[Int,     Label("patch")]
    prerelease: Optional[Prerelease]
    build: Optional[Build]

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}{self.prerelease or ''}{self.build or ''}"

semver = makeparser(SemVer, ws="manual")  # manual whitespace, like your sketch

# Typed usage:
t0: SemVer = semver("0.0.0")
t1: SemVer = semver("1.2.3-alpha.1+build.1")




################### [JSON] ###############
# Atoms
Digit   = Char["0-9"]
NZDigit = Char["1-9"]
Hex     = Char["0-9a-fA-F"]

class JNull(Rule):
    "null"

class JBool(Rule):
    # capture terminal and map
    value: Annotated[bool, ("true" | "false"), Map({"true": True, "false": False})]

class JNumber(Rule):
    # number := '-'? ('0' | NZDigit Digit*) ('.' Digit+)? ([eE] [+-]? Digit+)?
    value: Annotated[float,
        (("-"?,), ("0" | (NZDigit, Star[Digit])), ((".", Digit+)?), ((Char["eE"], Char["+-"]?, Digit+)?) ),
        Join, AsFloat
    ]

class JString(Rule):
    # string := '"' ( unescaped | '\' (simple | 'u' Hex^4) )* '"'
    value: Annotated[str,
        ('"', Star[
            (Char['\x20-\x21\x23-\x5B\x5D-\u10FFFF'] |
             ('\\', (Char['"\\/bfnrt'] | ('u', Hex, Hex, Hex, Hex))))
        ], '"'),
        Join, UnescapeJson
    ]

JSONValue = Union[JNull, JBool, JNumber, JString, "JArray", "JObject"]

class Pair(Rule):
    key: JString
    ":"
    val: "JSONValue"

class JArray(Rule):
    "["
    items: Annotated[list[JSONValue], SepBy("JSONValue", by=By[","])]
    "]"

class JObject(Rule):
    "{"
    pairs: Annotated[list[Pair], SepBy(Pair, by=By[","])]
    "}"

json = makeparser(JSONValue, ws="token")  # skip whitespace between tokens

doc = '{"ok": true, "nums":[1,2,3.5], "nested": {"a": null, "b": "hi"}}'
ast: JSONValue = json(doc)




############### [Arithmetic] ###############
# E -> E '+' T | E '-' T | T
# T -> T '*' F | T '/' F | F
# F -> '(' E ')' | Number

class Number(Rule):
    value: Annotated[float, Plus[Digit], Join, AsFloat]

Expr = Union["Add", "Sub", "Mul", "Div", Number]

class Add(Rule):
    left: "Expr"
    "+"
    right: "Expr"  # classic left recursion; GLL handles it

class Sub(Rule):
    left: "Expr"
    "-"
    right: "Expr"

class Mul(Rule):
    left: "Expr"
    "*"
    right: "Expr"

class Div(Rule):
    left: "Expr"
    "/"
    right: "Expr"

class Parens(Rule):
    "("
    inner: "Expr"
    ")"

Expr = Union[Add, Sub, Mul, Div, Parens, Number]
expr = makeparser(Expr, ws="token")

tree: Expr = expr("1 + 2 * (3 + 4) - 5")





















######## older ideas #########

# ############# [Usage Example] #############
# type Expr = Binop | Atom
# class Binop(Rule):
#     left: Expr
#     op: Literal['+', '-', '/', ]
#     right: Expr

# class Range(Rule):
#     Literal['(','[']|None
#     left: Expr
#     '..'
#     right: Expr
#     Literal[')',']']|None



# ################### sloppy json parser ######################
# from easygrammar import Rule, makeparser

# type Obj = Dict|List|str|int|Bool|Null

# class WS(Rule):
#     Literal[' ', '\n', '\t'] | None

# class Null(Rule):
#     'null'
# class Bool(Rule):
#     Literal['true','false']

# class ListItem(Rule):
#     WS
#     item: Obj
#     WS
#     ','

# class List(Rule):
#     '['
#     WS
#     items: list[ListItem]
#     WS
#     ']'

# class DictItem(Rule):
#     WS
#     key: str
#     WS
#     value: Obj
#     WS
#     ','

# class Dict(Rule):
#     '{'
#     WS
#     items: list[DictItem]
#     WS
#     '}'



# parse = makeparser(Obj)
# res: Obj = parse('{"Hello, ": "World!"}')





# ###########
# class Digit(Rule):
#     value: Literal[0,1,2,3,4,5,6,7,8,9]

# class PhoneNumber(Rule):
#     country: Literal[1] | None
#     '('
#     area: tuple[Digit, Digit, Digit]
#     ')'
#     prefix: tuple[Digit, Digit, Digit]
#     '-'
#     line: tuple[Digit, Digit, Digit]

#     def __str__(self):
#         s = ''
#         s += f'{self.country} ' if self.country else ''
#         s += f"({''.join(str(i.value) for i in self.area)})"
#         s += f" {''.join(str(i.value) for i in self.prefix)}"
#         s += f"-{''.join(str(i.value) for i in self.line)}"
#         return s



# from easygrammar import Rule, makeparser, Annotated, SepBy, Plus, Star, Char

# class Int(Rule):
#    # 0 or non-zero unsigned
#    i: Annotated[int, (Char['0'] | (Char['1-9'], Star[Char['0-9']]))]
#    def __str__(self): return str(self.i)

# class Id(Rule):
#    id: Plus[Char['a-zA-Z0-9-']] | Int
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






# """
# easygrammar

# class Rule   (all nodes are derived from this)

# Seq, Rep, Star, Plus, Opt


# # TODO: make alias for `Annotated`. But potentially `Annotated` could be good
# type ... = Annotated



# [notes/tbd]
# - handling ambiguities. Would be nice to just return all possible derivations as concrete objects in a list (perhaps can make use of sharing references to cut down on space usage). But definitely not so efficient...
# -
# """



