from typing import dataclass_transform, Self, final, overload, Annotated, Protocol, Any, Literal
from abc import ABC, ABCMeta, abstractmethod
import inspect
import ast

import pdb

class RuleMeta(ABCMeta):
    def __or__(cls: 'type[Rule]', other: 'type[Rule]|str|tuple') -> 'type[Rule]':
        # this runs on ClassA | ClassB
        # TODO: Rule1 | Rule2 should generate a new Rule
        if isinstance(other, str):
            print(f"Custom OR on classes: {cls.__name__} | {repr(other)}")
            return cls
        if isinstance(other, tuple):
            print(f"Custom OR on classes: {cls.__name__} | {repr(other)}")
            return cls
        print(f"Custom OR on classes: {cls.__name__} | {other.__name__}")
        return cls
    def __ror__(cls: 'type[Rule]', other: 'type[Rule]|str|tuple') -> 'type[Rule]':
        return cls | other


    def __call__(cls, raw: str, /) -> Self:
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

RuleLike = type[Rule] | tuple['RuleLike', ...] | str

class Infinity: ...
infinity = Infinity()

# TODO: proper typing and implementation
def repeat(rule:RuleLike, /, *, separator:str='', at_least:int=0, at_most:int|Infinity=infinity, exactly:int=None) -> type[Rule]:
    # TODO: whatever representation for a repeat rule...
    ...

def either(*rules:RuleLike) -> type[Rule]:
    # TODO
    ...

def optional(rule:RuleLike) -> type[Rule]:
    # TODO
    ...

def sequence(*rules:RuleLike) -> type[Rule]:
    # TODO
    ...

def char(pattern:str, /) -> type[Rule]:
    # TODO
    ...



repeat()