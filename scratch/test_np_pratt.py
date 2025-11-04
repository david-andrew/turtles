"""
TBD problems to solve
[x] finish handling grouping
[ ] support juxtapose
[ ] consider adding units + unit math!
[ ] dealing with <> group vs shift operators (tokenization hack, add context stack of how many <> groups are open, no shift operators allowed when non-zero)
[ ] if-else-if with proper handling of dangling else, etc.
    - similar to handling groups, if-else-if might be handled as a post step?
    - I'm realizing that after post steps, we need to go back to the reduction step b/c e.g. `(1+2)*3` when 1+2 is reduced, we would go to the grouping step, and then after the group is made, can we combine it with the 3
[ ] ambiguous precedence (e.g. `cos(x)^2` vs `a(x)^2`)
[ ] opchains (should be pretty straightforward with preprocessing pass)
[ ] eating interpolated strings. may have to introduce the idea of a context/state stack (which dictates the eat functions available)
    - e.g. quotes open the string context. inside of which braces can open a normal context, etc.
"""

import numpy as np
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Callable, dataclass_transform, Literal, cast
from enum import Enum, auto


import pdb


type OperatorLiteral = Literal["^", "*", "/", "+", "-", ";"]
type GroupLiteral = Literal["(", ")", "{", "}", "[", "]"]
class Assoc(Enum):
    # binops
    left = auto()
    right = auto()
    none = auto()

    # unary ops
    prefix = auto()
    postfix = auto()


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
    value: GroupLiteral
    def __str__(self) -> str:
        return self.value

# unfortunately, python typing doesn't support str[GroupLiteral], i.e. string made up only of GroupLiteral values
group_matchers: dict[GroupLiteral, str] = {
    '[': '])',
    '(': '])',
    '{': '}'
}

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
    if src.s[0] in "+-*/^;":
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
]

binops: set[OperatorLiteral] = {op for row in optable for op, assoc in row if assoc in (Assoc.right, Assoc.left, Assoc.none)}
prefixes: set[OperatorLiteral] = {op for row in optable for op, assoc in row if assoc == Assoc.prefix}
postfixes: set[OperatorLiteral] = {op for row in optable for op, assoc in row if assoc == Assoc.postfix}

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
def none_bp(i: int) -> tuple[int, int]:
    return (NO_BIND, NO_BIND)

bp_funcs: dict[Assoc, Callable[[int], tuple[int, int]]] = {
    Assoc.left: left_bp,
    Assoc.right: right_bp,
    Assoc.prefix: prefix_bp,
    Assoc.postfix: postfix_bp,
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


class SeqGroup(AST):
    items: list[AST]
    def __repr__(self):
        items_str = ', '.join([str(i) for i in self.items])
        return f'({items_str})'
    def eval(self) -> list[int|float]: return [i.eval() for i in self.items]

class Group(AST):
    item: AST
    def __repr__(self):
        return f'({self.item})'
    def eval(self):
        return self.item.eval()

class EmptyGroup(AST):
    def __repr__(self): return '()'
    def eval(self): return ()

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

@dataclass
class PrefixOp(AST):
    def eval(self): raise NotImplementedError
@dataclass
class PostfixOp(AST):
    def eval(self): raise NotImplementedError


def reduce_ops(tokens: list[Token|AST]) -> int:
    ast_idxs = [i for i, t in enumerate(tokens) if isinstance(t, AST)]
    if len(ast_idxs) == 0:
        return 0

    # for every AST, get the right_bp of the left thing, and the left_bp of the right thing
    adjacent_bps = []
    for idx in ast_idxs:
        left_t = tokens[idx-1] if idx-1>=0 else None
        right_t = tokens[idx+1] if idx+1<len(tokens) else None
        left_bp = -1
        right_bp = -1
        if left_t is not None and isinstance(left_t, OperatorT):
            _, left_bp = bindpow[left_t.value]
        if right_t is not None and isinstance(right_t, OperatorT):
            right_bp, _ = bindpow[right_t.value]
        adjacent_bps.append((left_bp, right_bp))

    adjacent_bps = np.array(adjacent_bps)
    diffs = np.diff(adjacent_bps)
    shift_mask = np.any(adjacent_bps > 0, axis=1) * (diffs != 0)[:,0]
    shift_dirs = np.sign(diffs)[:,0]


    shift_to = ast_idxs + shift_dirs

    # apply all the reductions
    reductions_applied = 0
    i = len(ast_idxs) - 1
    while i >= 0:
        if not shift_mask[i]:
            i -= 1
            continue
        idx = ast_idxs[i]
        ast = tokens[idx]
        assert isinstance(ast, AST), f"INTERNAL ERROR: expected ast to be an AST. got {ast}"
        target = shift_to[i]
        target_tok = tokens[target]
        assert isinstance(target_tok, (OperatorT)), f"INTERNAL ERROR: expected operator at target. got {tokens[target]}"  # (BinOp, PrefixOp, PostfixOp)
        if target_tok.value in binops:
            if idx < target:
                # right item was not ready yet
                i-=1
                continue
            elif idx > target:
                if i-1 < 0 or shift_to[i-1] != target:
                    # left item not ready or captured by the binop
                    i-=1
                    continue
                tokens[target-1:target+2] = [BinOp(*tokens[target-1:target+2])]
                i-=2
                reductions_applied += 1
                continue
            else:
                raise ValueError(f"INTERNAL ERROR: expected ast target idx to be different from ast's own idx. both are `{idx}`")
        else:
            raise NotImplementedError(f'need to handle non-binops. current was {ast=}, {target_tok=}')


    return reductions_applied

def make_groups(tokens: list[Token|AST]) -> int:
    reductions_applied = 0
    group_idxs = [i for i, t in enumerate(tokens) if isinstance(t, GroupT)]
    i = len(group_idxs) - 1
    while i >= 1:
        left_idx = group_idxs[i-1]
        right_idx = group_idxs[i]
        # all items between left and right should be ASTs
        if any(not isinstance(t, AST) for t in tokens[left_idx+1:right_idx]):
            # interior not fully reduced
            i -= 1
            continue
        left_t = tokens[left_idx]
        try:
            right_t = tokens[right_idx]
        except:
            pdb.set_trace()
            ...
        assert isinstance(left_t, GroupT), f'INTERNAL ERROR: left_t should be a GroupT. got {left_t}'
        assert isinstance(right_t, GroupT), f'INTERNAL ERROR: right_t should be a GroupT. got {right_t}'

        if left_t.value not in group_matchers:
            i -= 1
            continue
            # raise ValueError(f'INTERNAL ERROR: GroupT token not in  group_matchers (i.e. need to expand it... {left_t.value=}')
        if right_t.value not in group_matchers[left_t.value]:
            # left and right are not a match
            i -= 1
            continue

        # left and rigth match, and interior fully match!
        # TODO: need to actually select the group type based on the left/right tokens
        # (..)|[..]|[..)|(..]: range (i.e. delims with a single bare range AST inside)
        # (): Group
        # []: list
        # {}: scope
        # <>: typeparams
        if right_idx - left_idx > 2:
            reductions_applied += 1
            tokens[left_idx:right_idx+1] = [SeqGroup(tokens[left_idx+1:right_idx])]
            i -= 2
        elif right_idx - left_idx == 2:
            reductions_applied += 1
            tokens[left_idx:right_idx+1] = [Group(tokens[left_idx+1])]
            i -= 2
        elif right_idx - left_idx == 1:
            reductions_applied += 1
            tokens[left_idx:right_idx+1] = [EmptyGroup()]
            i -= 2
        else:
            raise ValueError(f"left and right group index don't make sense... {tokens[left_idx:right_idx+1]=}")

    return reductions_applied

def shunt_tokens(tokens: list[Token]) -> list[AST]:
    tokens: list[Token|AST] = cast(list[Token|AST], tokens)
    for i, t in enumerate(tokens):
        if isinstance(t, NumberT):
            tokens[i] = Atom(t.value)

    # TODO: probably just redo this as imperative loop (i.e. remove vectorization)
    while True:
        init_len = len(tokens)
        reductions_applied = reduce_ops(tokens)
        if reductions_applied == 0:
            reductions_applied += make_groups(tokens)
        # if reductions_applied == 0:
        #     reductions_applied += make_flows(tokens)
        # if reductions_applied == 0:
        #     break
        if len(tokens) == init_len:
            # no reductions applied by anything
            break

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


test_cases = [
    '(0)',
    '(1+2)*3',
]
