from typing import dataclass_transform, Self, final
from abc import ABC, ABCMeta
import inspect
import ast

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
        except OSError as e:
            if str(e) == 'source code not available':
                # TODO: have a fallback that makes use of metaclass capturing named expressions in the class body
                raise ValueError(f'Rule subclass `{target_cls.__name__}` must be defined in a file (e.g. cannot create a grammar rule in the REPL). Source code inspection failed: {e}') from e
            raise e

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



class ClassA(Rule):
    '('
    a:int
    ')'

from typing import Annotated
class Char:
    def __init__(self, char: str): ...
class Test(Rule):
    a: Annotated[int, Char('('), Char(')')]
    def __init__(self, a:int): ...
a = Test('()')
a.a

class ClassB(Rule):
    ClassA("(5)")
    b:str

class ClassC:
    '('
    a: int
    ')'

c = ClassB('')
c.b

class t(Rule): ...

print(ClassA | ClassB)
print(ClassA | "ClassB")
print(t| 'ajhdgajhdgjag' | 'b' | ClassB)
print(ClassA | ("ClassB", "ClassC"))
# -> "Custom OR on classes: ClassA | ClassB"

# Example: demonstrate collected sequences for subclasses
print("ClassA sequence:", getattr(ClassA, "_sequence", None))
print("ClassB sequence:", getattr(ClassB, "_sequence", None))
