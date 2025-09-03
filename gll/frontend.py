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






############# [Usage Example] #############
type Expr = Binop | Atom
class Binop(Rule):
    left: Expr
    op: Literal['+', '-', '/', ]
    right: Expr

class Range(Rule):
    Literal['(','[']|None
    left: Expr
    '..'
    right: Expr
    Literal[')',']']|None







################### sloppy json parser ######################
from easygrammar import Rule, makeparser

type Obj = Dict|List|str|int|Bool|Null

class WS(Rule):
    Literal[' ', '\n', '\t'] | None

class Null(Rule):
    'null'
class Bool(Rule):
    Literal['true','false']

class ListItem(Rule):
    WS
    item: Obj
    WS
    ','

class List(Rule):
    '['
    WS
    items: list[ListItem]
    WS
    ']'

class DictItem(Rule):
    WS
    key: str
    WS
    value: Obj
    WS
    ','

class Dict(Rule):
    '{'
    WS
    items: list[DictItem]
    WS
    '}'



parse = makeparser(Obj)
res: Obj = parse('{"Hello, ": "World!"}')





###########
class Digit(Rule):
    value: Literal[0,1,2,3,4,5,6,7,8,9]

class PhoneNumber(Rule):
    country: Literal[1] | None
    '('
    area: tuple[Digit, Digit, Digit]
    ')'
    prefix: tuple[Digit, Digit, Digit]
    '-'
    line: tuple[Digit, Digit, Digit]

    def __str__(self):
        s = ''
        s += f'{self.country} ' if self.country else ''
        s += f"({''.join(str(i.value) for i in self.area)})"
        s += f" {''.join(str(i.value) for i in self.prefix)}"
        s += f"-{''.join(str(i.value) for i in self.line)}"
        return s




"""
easygrammar

class Rule   (all nodes are derived from this)

Seq, Rep, Star, Plus, Opt


# TODO: make alias for `Annotated`. But potentially `Annotated` could be good
type ... = Annotated



[notes/tbd]
- handling ambiguities. Would be nice to just return all possible derivations as concrete objects in a list (perhaps can make use of sharing references to cut down on space usage). But definitely not so efficient...
-
"""
