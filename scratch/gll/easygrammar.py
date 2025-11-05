from types import NoneType, NotImplementedType, UnionType
from typing import Self, final, Protocol, Any, Union, overload, Annotated as Coerce
from abc import ABC, ABCMeta, abstractmethod
import inspect
import ast

import pdb

class RuleMeta(ABCMeta):
    @overload
    def __or__[T:Rule](cls: type[T], other:type[None]) -> type[Optional[T]]: ...
    @overload
    def __or__[T:Rule, U:Rule](cls: type[T], other: type[U]) -> type[Either[T|U]]: ...
    def __or__[T:Rule, U:Rule](cls: type[T], other: type[U]|type[None]) -> type[Either[T|U]]|type[Optional[T]]: ...

    # TODO: something about the typing here prevents Rule|None from working, and it just becomes Any
    # @overload
    # def __or__[T:Rule](cls: type[T], other: None) -> type[Optional[T]]: ...
    # @overload
    # def __or__[T:Rule, U:Rule](cls: type[T], other: type[U]|str|tuple) -> type[Either[T, U]]: ...
    # def __or__[T:Rule, U:Rule](cls: type[T], other: type[U]|str|tuple|None) -> type[Either[T, U]|Optional[T]]:
    #     # this runs on ClassA | ClassB
    #     # TODO: Rule1 | Rule2 should generate a new Rule
    #     if isinstance(other, str):
    #         print(f"Custom OR on classes: {cls.__name__} | {repr(other)}")
    #         return cls
    #     if isinstance(other, tuple):
    #         print(f"Custom OR on classes: {cls.__name__} | {repr(other)}")
    #         return cls
    #     if other is None:
    #         return type.__or__(cls, other)
    #         # return NotImplemented
    #         # print(f"Custom OR on classes: {cls.__name__} | None")
    #         # return cls
    #     print(f"Custom OR on classes: {cls.__name__} | {other.__name__}")
    #     return cls
    # @overload
    # def __ror__[T:Rule](cls: type[T], other:type[None]) -> type[Optional[T]]: ... 
    # @overload
    # def __ror__[T:Rule, U:Rule](cls: type[T], other: type[U]) -> type[Either[T|U]]: ...
    # def __ror__[T:Rule, U:Rule](cls: type[T], other: type[U]|type[None]) -> type[Either[T|U]]|type[Optional[T]]:
        # ...
        # return cls | other
    def __ror__(cls, other):
        return cls | other

    def __call__[T:Rule](cls: type[T], raw: str, /) -> T:
        # TODO: whole process of parsing the input string
        # TODO: would it be possible to pass in a generic sequence (e.g. list[Token]), i.e. easy ability to separate scanner and parser?
        # print(f"Custom call on classes: {cls.__name__} | {raw}")

        # create an instance of the class (without calling __init__)
        obj = cls.__new__(cls, cls.__name__)

        # define all of the members of the instance (based on the parse shape). e.g.
        obj.a = 42  #DEBUG
        obj.b = 43  #DEBUG

        return obj


# @dataclass_transform()
class Rule(ABC, metaclass=RuleMeta):
    """initialize a token subclass as a dataclass"""
    # this is just a placeholder for type-checking. The actual implementation is in the __call__ method.
    @final
    def __init__(self, raw:str, /):
        ...

    @staticmethod
    def _collect_sequence_for_class(target_cls: type) -> list:
        """Return ordered (expr/decl) tuples found in the class body of target_cls."""
        try:
            source_file = inspect.getsourcefile(target_cls) or inspect.getfile(target_cls)
        except OSError as e:
            if str(e) == 'source code not available':
                # TODO: have a fallback that makes use of metaclass capturing named expressions in the class body
                raise ValueError(f'Rule subclass `{target_cls.__name__}` must be defined in a file (e.g. cannot create a grammar rule in the REPL). Source code inspection failed: {e}') from e
            raise e


        if not source_file:
            raise ValueError(f'Rule subclass `{target_cls.__name__}` must be defined in a file (e.g. cannot create a grammar rule in the REPL). Source code inspection failed: {e}') from e
        with open(source_file, "r") as fh:
            file_source = fh.read()

        module_ast = ast.parse(file_source)
        _, class_start_lineno = inspect.getsourcelines(target_cls)

        target_class_node = None
        for node in ast.walk(module_ast):
            if isinstance(node, ast.ClassDef) and node.name == target_cls.__name__ and node.lineno == class_start_lineno:
                target_class_node = node
                break

        if target_class_node is None:
            # fallback: first class with matching name
            for node in ast.walk(module_ast):
                if isinstance(node, ast.ClassDef) and node.name == target_cls.__name__:
                    target_class_node = node
                    break

        if target_class_node is None:
            return []

        sequence = []
        for stmt in target_class_node.body:
            # capture bare string expressions (including the leading docstring if used that way)
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                sequence.append(("expr", stmt.value.value))
                continue

            # capture variable annotations: a:int, b:str, etc.
            if isinstance(stmt, ast.AnnAssign):
                var_name = None
                if isinstance(stmt.target, ast.Name):
                    var_name = stmt.target.id
                # best-effort to reconstruct the annotation text
                annotation_text = ast.get_source_segment(file_source, stmt.annotation)
                if annotation_text is None:
                    try:
                        annotation_text = ast.unparse(stmt.annotation)  # py>=3.9
                    except Exception:
                        annotation_text = None
                sequence.append(("decl", var_name, annotation_text))
                continue

        return sequence


    def __init_subclass__(cls: 'type[Rule]', **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        # ensure that __init__ in this base class was not overridden
        # TODO: can this point to where the __init__ was overridden?
        if cls.__init__ != Rule.__init__:
            raise ValueError(f"Rule subclass `{cls.__name__}` must not override __init__ in the base class.")

        # capture the ordered sequence of class-body expressions and declarations
        sequence = Rule._collect_sequence_for_class(cls)
        setattr(cls, "_sequence", sequence)


    # def __repr__(self) -> str:
    #     dict_str = ", ".join([f"{k}=`{v}`" for k, v in self.__dict__.items()])
    #     return f"{self.__class__.__name__}({dict_str})"


# class Rule(RuleBase):
#     def __init__(self, raw:str): ...



# # class RuleFactoryMeta(ABCMeta): ...
# class RuleFactory(ABC):#, metaclass=RuleFactoryMeta): ...
#     @abstractmethod
#     def __new__(cls, *args, **kwargs) -> type[Rule]: ...

# class Repeat(RuleFactory):
#     @overload
#     def __new__(cls, *, exactly:int) -> type[Rule]: ...
#     @overload
#     def __new__(cls, *, at_least:int|None=None, at_most:int|None=None) -> type[Rule]: ...
#     def __new__(cls, *, at_least:int|None=None, at_most:int|None=None, exactly:int|None=None) -> type[Rule]:
#         if exactly is not None:
#             if at_least is not None:
#                 raise ValueError('`exactly` and `at_least` are mutually exclusive.')
#             if at_most is not None:
#                 raise ValueError('`exactly` and `at_most` are mutually exclusive.')
#             at_least=exactly
#             at_most=exactly
#         else:
#             if at_least is None:
#                 at_least=0
#             if at_most is None:
#                 at_most=float('inf')

#         pdb.set_trace()

#         return Rule

# Repeat()

# class ClassA(Rule):
#     '('
#     a:int
#     ')'

# protocol for helper functions
class HelperFunction(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> type[Rule]: ...


class Infinity: ...
infinity = Infinity()

# RuleLike: TypeAlias = type[Rule] | tuple['RuleLike', ...] | str


class Char(Rule):
    # TODO: this might be shaped differently
    char: str
class Either[T:Rule](Rule):
    item: T
class Repeat[T:Rule](Rule):
    items: list[T]
class Optional[T:Rule](Rule):
    item: T|None
class Sequence[*Ts](Rule):
    items: tuple[*Ts]

# TBD how this will work
class _Ambiguous[T:Rule](Rule):
    alternatives: list[T]


def char(s:str) -> type[Char]:
    #TODO: whatever implementation needed...
    return Char

def either[T:Rule](*args:type[T]) -> type[Either[T]]:
    #TODO: whatever implementation needed...
    return Either[T]

@overload
def repeat[T:Rule](arg:type[T],  /, *, separator:str='', exactly:int) -> type[Repeat[T]]: ...
@overload
def repeat[T:Rule](arg:type[T],  /, *, separator:str='', at_least:int=0, at_most:int|Infinity=infinity) -> type[Repeat[T]]: ...
def repeat[T:Rule](arg:type[T],  /, *, separator:str='', at_least:int=0, at_most:int|Infinity=infinity, exactly:int|None=None) -> type[Repeat[T]]:
    #TODO: whatever implementation needed...
    return Repeat[T]


def optional[T:Rule](arg:type[T]) -> type[Optional[T]]:
    #TODO: whatever implementation needed...
    return Optional[T]

@overload
def sequence[A:Rule](a:type[A], /) -> type[Sequence[A]]: ...
@overload
def sequence[A:Rule, B:Rule](a:type[A], b:type[B], /) -> type[Sequence[A, B]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule](a:type[A], b:type[B], c:type[C], /) -> type[Sequence[A, B, C]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule](a:type[A], b:type[B], c:type[C], d:type[D], /) -> type[Sequence[A, B, C, D]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], /) -> type[Sequence[A, B, C, D, E]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], /) -> type[Sequence[A, B, C, D, E, F]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], /) -> type[Sequence[A, B, C, D, E, F, G]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], /) -> type[Sequence[A, B, C, D, E, F, G, H]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], /) -> type[Sequence[A, B, C, D, E, F, G, H, I]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule, U:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], u:type[U], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule, U:Rule, V:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], u:type[U], v:type[V], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule, U:Rule, V:Rule, W:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], u:type[U], v:type[V], w:type[W], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule, U:Rule, V:Rule, W:Rule, X:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], u:type[U], v:type[V], w:type[W], x:type[X], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule, U:Rule, V:Rule, W:Rule, X:Rule, Y:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], u:type[U], v:type[V], w:type[W], x:type[X], y:type[Y], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y]]: ...
@overload
def sequence[A:Rule, B:Rule, C:Rule, D:Rule, E:Rule, F:Rule, G:Rule, H:Rule, I:Rule, J:Rule, K:Rule, L:Rule, M:Rule, N:Rule, O:Rule, P:Rule, Q:Rule, R:Rule, S:Rule, T:Rule, U:Rule, V:Rule, W:Rule, X:Rule, Y:Rule, Z:Rule](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S], t:type[T], u:type[U], v:type[V], w:type[W], x:type[X], y:type[Y], z:type[Z], /) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z]]: ...
@overload
def sequence[T:Rule](*args:type[T]) -> type[Sequence[*tuple[T, ...]]]: ... # give up and just say it's a tuple of unions of all the possible args
def sequence(*args):
    #TODO: whatever implementation needed...
    return Sequence#[*tuple[T, ...]]

def test():
    class A(Rule):
        'a'
    class B(Rule):
        'b'
    class C(Rule):
        'c'
    class D(Rule):
        'd'
    a = repeat(A, separator='.', at_least=1)
    b = a('aaaa')
    c = b.items[0]
    r = sequence(A,B,D,D)
    r('').items
    rule1 = either(A, repeat(B, exactly=5, separator='.'), optional(B))
    rule1('b.b.b.b.b').item

    rule2 = sequence(A, B, repeat(B), repeat(sequence(A, B)), A)
    rule2('abbbbbbababababa').items[2].items[1]



    rule3 = either(A, B, C)
    apple = rule3('a').item
    if isinstance(apple, A):
        apple
    elif isinstance(apple, B):
        apple
    elif isinstance(apple, C):
        apple







































# T = TypeVar('T', bound=RuleLike)
# Ts = TypeVarTuple('Ts')#, bound=RuleLike) # TODO: some way of setting bounds on the Ts. perhaps runtime validation
# class Repeat(Rule, Generic[T]):
#     items: list[T]
# class Either(Rule, Generic[Unpack[Ts]]):
#     item: Unpack[Ts]
# class Optional(Rule, Generic[T]):
#     item: T|None
# class Sequence(Rule, Generic[Unpack[Ts]]):
#     items: tuple[Unpack[Ts]]
# class Char(Rule): ...



# def repeat(rule:type[T], /, *, separator:str='', at_least:int=0, at_most:int|Infinity=infinity, exactly:int=None) -> type[Repeat[T]]:
#     # TODO: whatever representation for a repeat rule...
#     ...

#     return Repeat[T]


# apple = repeat('a', exactly=4)
# apple('aaaa').items


# def either(*rules:Unpack[Ts]) -> type[Either[Ts]]:
#     # TODO
#     ...
#     return Either[Ts]
# class A(Rule): ...
# class B(Rule): ...
# apple = either(A, B)('a')
# apple.item

# def optional(rule:type[T]) -> type[Optional[T]]:
#     # TODO
#     ...
#     return Optional[T]

# def sequence(*rules:Unpack[Ts]) -> type[Sequence[Ts]]:
#     # TODO
#     ...
#     return Sequence[Ts]

# def char(pattern:str, /) -> type[Rule]:
#     # TODO
#     ...
#     return Char
