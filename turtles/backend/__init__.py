"""
Parsing backends for the turtles library.

The default backend is GLL (Generalized LL), which can handle any context-free
grammar including ambiguous and left-recursive grammars.
"""
from .gll import (
    GLLParser,
    CompiledGrammar,
    DisambiguationRules,
    ParseTree,
    ParseError,
    parse,
    set_backend,
    get_backend,
)

__all__ = [
    'GLLParser',
    'CompiledGrammar', 
    'DisambiguationRules',
    'ParseTree',
    'ParseError',
    'parse',
    'set_backend',
    'get_backend',
]
