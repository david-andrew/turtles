"""
TBD problems to solve
- finish handling grouping
- dealing with <> group vs shift operators (tokenization hack, add context stack of how many <> groups are open, no shift operators allowed when non-zero)
- if-else-if with proper handling of dangling else, etc.
    - similar to handling groups, if-else-if might be handled as a post step?
    - I'm realizing that after post steps, we need to go back to the reduction step b/c e.g. `(1+2)*3` when 1+2 is reduced, we would go to the grouping step, and then after the group is made, can we combine it with the 3
- ambiguous precedence (e.g. `cos(x)^2` vs `a(x)^2`)
- opchains (should be pretty straightforward with preprocessing pass)
- eating interpolated strings. may have to introduce the idea of a context/state stack (which dictates the eat functions available)
    - e.g. quotes open the string context. inside of which braces can open a normal context, etc.
"""

import numpy as np
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Callable, dataclass_transform, Literal
from enum import Enum, auto


import pdb


type OperatorLiteral = Literal["^", "*", "/", "+", "-"]
class Assoc(Enum):
    left = auto()
    right = auto()
    prefix = auto()
    postfix = auto()
    none = auto()
    group = auto()


@dataclass_transform()
class Token(ABC):
    """initialize a token subclass as a dataclass"""
    def __init_subclass__(cls: 'type[Token]', **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(cls, repr=False)

    def __repr__(self) -> str:
        dict_str = ", ".join([f"{k}=`{v}`" for k, v in self.__dict__.items()])
        return f"{self.__class__.__name__}({dict_str})"

class NumberT(Token):
    value: int
    def __str__(self) -> str:
        return str(self.value)

class OperatorT(Token):
    value: OperatorLiteral
    def __str__(self) -> str:
        return self.value

class GroupT(Token):
    value: Literal["(", ")", "{", "}", "[", "]"]
    def __str__(self) -> str:
        return self.value

class WhitespaceT(Token):
    ...
    # value: Literal[" ", "\t", "\n"]

# class Juxtapose(Token):
#     ...


@dataclass
class SourceBox:
    s: str

def eat_line_comment(src:SourceBox) -> WhitespaceT|None:
    if src.s.startswith("%"):
        i = 0
        while i < len(src.s) and src.s[i] != "\n":
            i += 1
        src.s = src.s[i+1:]
        return WhitespaceT()
    return None

def eat_block_comment(src:SourceBox) -> WhitespaceT|None:
    if src.s.startswith("%{"): # closes with }%
        i = 2
        stack = 1
        while stack > 0:
            if src.s[i:i+2] == "%{":
                stack += 1
                i += 2
            elif src.s[i:i+2] == "}%":
                stack -= 1
                i += 2
            else:
                i += 1
        src.s = src.s[i:]
        return WhitespaceT()
    return None

def eat_whitespace(src:SourceBox) -> WhitespaceT|None:
    i = 0
    while i < len(src.s) and src.s[i] in " \t\n":
        i += 1
    if i > 0:
        src.s = src.s[i:]
        return WhitespaceT()
    return None

def eat_number(src:SourceBox) -> NumberT|None:
    if src.s[0] in "0123456789":
        i = 0
        while i < len(src.s) and src.s[i] in "0123456789":
            i += 1
        num = src.s[:i]
        src.s = src.s[i:]
        return NumberT(value=int(num))
    return None

def eat_operator(src:SourceBox) -> OperatorT|None:
    if src.s[0] in "+-*/^":
        op = src.s[0]
        src.s = src.s[1:]
        return OperatorT(value=op)
    return None

def eat_group(src:SourceBox) -> GroupT|None:
    if src.s[0] in "({[]})":
        group = src.s[0]
        src.s = src.s[1:]
        return GroupT(value=group)
    return None

eat_fns = [
    eat_whitespace,
    eat_number,
    eat_operator,
    eat_group,
]
def tokenize(raw_src:str) -> list[Token]:
    src = SourceBox(s=raw_src)
    tokens = []

    while len(src.s) > 0:
        for eat_fn in eat_fns:
            if tok:=eat_fn(src):
                tokens.append(tok)
                break
        else:
            raise ValueError(f"unknown token: `{src.s[0]}`. remaining: `{src.s}`")

    return tokens




# user defined operator precedence table
# precedence from highest to lowest
optable: list[list[tuple[OperatorLiteral, Assoc]]] = [
    [("^", Assoc.right)],
    [("*", Assoc.left), ("/", Assoc.left)],
    [("+", Assoc.left), ("-", Assoc.left)],
    [(';', Assoc.postfix)],
    [('(', Assoc.group), (')', Assoc.group), ('{', Assoc.group), ('}', Assoc.group), ('[', Assoc.group), (']', Assoc.group)]
]

BASE_BIND_POWER = 1   #TBD, but 0 probably for groups ()
NO_BIND = -1
def left_bp(i: int) -> tuple[int, int]: 
    return (BASE_BIND_POWER+2*i, BASE_BIND_POWER+2*i+1)
def right_bp(i: int) -> tuple[int, int]: 
    return (BASE_BIND_POWER+2*i+1, BASE_BIND_POWER+2*i)
def prefix_bp(i: int) -> tuple[int, int]: 
    return (BASE_BIND_POWER+2*i, NO_BIND)
def postfix_bp(i: int) -> tuple[int, int]: 
    return (NO_BIND, BASE_BIND_POWER+2*i)
def group_bp(i: int) -> tuple[int, int]: 
    return (NO_BIND, NO_BIND)
def none_bp(i: int) -> tuple[int, int]: 
    return (NO_BIND, NO_BIND)

bp_funcs: dict[Assoc, Callable[[int], tuple[int, int]]] = {
    Assoc.left: left_bp,
    Assoc.right: right_bp,
    Assoc.prefix: prefix_bp,
    Assoc.postfix: postfix_bp,
    Assoc.group: group_bp,
    Assoc.none: none_bp,
}

# build the pratt binding power table
bindpow: dict[OperatorLiteral, tuple[int, int]] = {
    op: bp_funcs[assoc](i)
    for i, row in enumerate(reversed(optable))
        for op, assoc in row
}


@dataclass_transform()
class AST(ABC):
    def __init_subclass__(cls: 'type[AST]', **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(cls, repr=False)
    
    @abstractmethod
    def eval(self) -> int|float: ...

class Atom(AST):
    val: int|float
    def __repr__(self) -> str: return str(self.val)
    def eval(self) -> int|float: return self.val

@dataclass
class BinOp(AST):
    left: AST
    op: OperatorT
    right: AST

    def __repr__(self) -> str:
        return f"({self.op} {self.left} {self.right})"
    
    def eval(self) -> int|float:
        left = self.left.eval()
        right = self.right.eval()
        op = self.op.value
        if op == "^":
            return left ** right
        elif op == "*":
            return left * right
        elif op == "/":
            return left / right
        elif op == "+":
            return left + right
        elif op == "-":
            return left - right
        else:
            raise ValueError(f"unknown operator: '{op}'. {self=}")

def shunt_tokens(tokens: list[Token]) -> list[AST]:
    for i, t in enumerate(tokens):
        if isinstance(t, NumberT):
            tokens[i] = Atom(t.value)
    
    # TODO: probably just redo this as imperative loop (i.e. remove vectorization)
    while True: #any(isinstance(t, OperatorT) for t in tokens):
        op_indices = np.array([i for i, t in enumerate(tokens) if isinstance(t, (OperatorT, GroupT))])
        left_pad = [] if isinstance(tokens[0], (OperatorT, GroupT)) else [NO_BIND, NO_BIND]
        right_pad = [] if isinstance(tokens[len(tokens)-1], (OperatorT, GroupT)) else [NO_BIND, NO_BIND]
        bind_pows = np.array(left_pad + [i for t in tokens if isinstance(t, (OperatorT, GroupT)) for i in bindpow[t.value]] + right_pad)[1:-1]
        bind_pows = bind_pows.reshape(len(bind_pows)//2, 2)
        pdb.set_trace()
        shunt_dir = np.sign(np.diff(bind_pows))[..., 0]
        # shunt_dir = (bind_pows[:,0] > bind_pows[:,1]).astype(int)

        # anywhere there is a false followed by a true
        group_indices = np.where(np.diff(shunt_dir) == 1)[0] + 1

        # apply reductions (reverse order so the indices don't get messed up)
        for i in reversed(group_indices):
            op_idx = op_indices[i-1]  # -1 because atom, not operator on left or right side of expr. TODO: better handling of this
            tokens[op_idx-1:op_idx+2] = [BinOp(*tokens[op_idx-1:op_idx+2])]
        
        pdb.set_trace()
     
    if not all(isinstance(t, AST) for t in tokens):
        raise ValueError(f"token shunting failed. {tokens=}")
    
    return tokens


def parse(tokens: list[Token]) -> list[AST]:
    # TODO: other post-tokenization passes (e.g. juxtapose, opchains, etc.)
    # filter whitespace
    tokens = [t for t in tokens if not isinstance(t, WhitespaceT)]
    return shunt_tokens(tokens)

if __name__ == "__main__":
    DEBUG = True
    
    if DEBUG: print(bindpow)

    from easyrepl import REPL
    for s in REPL(history_file='.chat'):
        tokens = tokenize(s)
        exprs = parse(tokens)
        for e in exprs:
            if DEBUG: print(e)
            print(e.eval())

    # expr_str = "2 ^ 3 ^ 4 ^ 5 + 5 * 4"# 1+2+3+4"
    # print(tokenize("1 + 2 * 3"))
    # print(bindpow)
    # print(exprs:=shunt_tokens(tokenize(expr_str)))
    # for e in exprs:
    #     print(e.eval())