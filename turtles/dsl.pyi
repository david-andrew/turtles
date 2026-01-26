"""
Type stubs for dsl.py

These stubs provide better type inference for the grammar marker classes.
At runtime, the actual classes in dsl.py are used for introspection.

The main types that necessitated the .pyi file are:
- optional[T]     -> T | None
- sequence[*Ts]   -> tuple[*Ts]
- repeat[T]       -> list[T]
- either[*Ts]     -> Union[*Ts]
- RuleUnion[*Ts]  -> Union[*Ts]

everything else should just match the original implementation
"""
from __future__ import annotations

from abc import ABC, ABCMeta
from typing import Any, ClassVar, Union, TypeVar

# Re-export the grammar types
from .grammar import GrammarRule
from .gll import CompiledGrammar

# TypeVar for metaclass __call__ return type
_R = TypeVar('_R', bound='Rule')

# === Type aliases for grammar markers ===
# These make the type checker see the "unwrapped" types

# optional[T] is seen as T | None
type optional[T] = T | None

# sequence[*Ts] is seen as tuple[*Ts]
type sequence[*Ts] = tuple[*Ts]

# repeat[T] is seen as list[T]
type repeat[T] = list[T]

# either[*Ts] is seen as Union[*Ts]
type either[*Ts] = Union[*Ts]

# RuleUnion is seen as Union[*Ts] for type annotations
type RuleUnion[*Ts] = Union[*Ts]

# TODO: would be nice if we didn't have to duplicate this definition
type AsDictResult = str | int | float | bool | dict[str, AsDictResult] | list[AsDictResult]

# === Actual classes ===

class SourceNotAvailableError(Exception): ...

class RuleMeta(ABCMeta):
    # Note: __or__ and __ror__ are intentionally NOT stubbed here.
    # At runtime they return RuleUnion for grammar introspection,
    # but for type checking we want Python's default behavior where
    # Float | Int creates a proper union type usable in annotations.
    def __call__(cls: type[_R], raw: str, /) -> _R: ...

class Rule(ABC, metaclass=RuleMeta):
    _text: str
    _start: int
    _end: int
    _compiled_grammar: ClassVar[CompiledGrammar | None]
    _grammar: ClassVar[list[GrammarRule] | None]
    
    def __init__(self, raw: str, /) -> None: ...
    def __init_subclass__(cls, **kwargs: Any) -> None: ...
    def as_dict(self) -> AsDictResult: ...
    @classmethod
    def _get_grammar(cls) -> list[GrammarRule]: ...


class char(Rule): ...
class separator[T]: ...
class at_least: ...
class at_most: ...
class exactly: ...

# class _ambiguous[T](Rule):
#     alternatives: list[T]


def tree_string(node: Rule) -> str: ...
