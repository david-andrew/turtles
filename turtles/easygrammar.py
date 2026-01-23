from __future__ import annotations

from types import NoneType, NotImplementedType, UnionType
import typing
from typing import Self, final, Protocol, Any, Union, overload, Annotated as Cast, TYPE_CHECKING
from abc import ABC, ABCMeta, abstractmethod
import inspect
import ast

from .grammar import register_rule, _build_grammar

if TYPE_CHECKING:
    from .grammar import GrammarRule
    from .backend.gll import ParseTree, CompiledGrammar


class SourceNotAvailableError(Exception):
    """Raised when the turtles DSL is used outside of a source file context."""
    pass


def _check_source_available() -> None:
    """
    Check that the module importing turtles has source code available.
    Raises SourceNotAvailableError if called from REPL, exec(), etc.
    """
    frame = inspect.currentframe()
    try:
        # Walk up the stack to find the first frame outside of the turtles package
        while frame is not None:
            filename = frame.f_code.co_filename
            # skip frames from within the turtles package itself
            if 'turtles' in filename and ('easygrammar' in filename or '__init__' in filename or 'grammar' in filename):
                frame = frame.f_back
                continue
            # skip importlib internals
            if 'importlib' in filename or filename.startswith('<frozen'):
                frame = frame.f_back
                continue
            # found the caller - check if it has source
            if filename.startswith('<') or not filename:
                raise SourceNotAvailableError(
                    f"The turtles DSL requires source code to be available. "
                    f"Cannot import from '{filename}'. "
                    f"Please use turtles from a .py file, not from the REPL, exec(), or eval()."
                )
            # source is available
            return
    finally:
        del frame


_check_source_available()


"""
Notes:
- optional should maybe just be the regular typing.Optional
- __or__ for Rule|None should return Optional[Rule]
"""

_all_rule_unions: list['RuleUnion'] = []

# Cache of local scopes captured at rule/union definition time
# Maps frame identity (file, function name, line) to locals snapshot
_captured_locals: dict[tuple[str, str, int], dict[str, object]] = {}


def _capture_caller_locals() -> None:
    """
    Capture a snapshot of the caller's locals.
    This allows rules defined inside functions to be discovered later.
    """
    frame = inspect.currentframe()
    try:
        # Walk up to find the first frame outside the turtles package
        caller = frame.f_back
        while caller:
            filename = caller.f_code.co_filename
            if 'easygrammar.py' not in filename and 'grammar.py' not in filename:
                break
            caller = caller.f_back
        
        if caller:
            # Use (filename, function name, first line) as key for deduplication
            key = (caller.f_code.co_filename, caller.f_code.co_name, caller.f_code.co_firstlineno)
            # Update the snapshot (later captures override earlier, which is what we want)
            _captured_locals[key] = dict(caller.f_locals)
    finally:
        del frame


def _get_all_captured_vars() -> dict[str, object]:
    """
    Get all variables from captured local scopes plus caller's current scope.
    Returns a dict with all discovered variables (later captures override earlier).
    """
    result: dict[str, object] = {}
    
    # First, include all previously captured locals
    for locals_snapshot in _captured_locals.values():
        result.update(locals_snapshot)
    
    # Then, walk the current call stack to find current locals
    frame = inspect.currentframe()
    try:
        caller = frame.f_back
        while caller:
            filename = caller.f_code.co_filename
            # Skip turtles internals and Python/importlib internals
            if ('easygrammar.py' not in filename and 
                'grammar.py' not in filename and
                'gll.py' not in filename and
                'importlib' not in filename and
                not filename.startswith('<frozen')):
                result.update(caller.f_locals)
                result.update(caller.f_globals)
            caller = caller.f_back
    finally:
        del frame
    
    return result


class RuleUnion[T]:
    """
    Represents a union of Rule classes (A | B | C).
    Can be registered as a named rule.
    
    Supports disambiguation via:
        union.precedence = [HighestPriorityRule, ..., LowestPriorityRule]
        union.associativity = {Rule: 'left', OtherRule: 'right'}
    """
    def __init__(self, alternatives: list[type['Rule']], *, _source_file: str | None = None, _source_line: int | None = None):
        self.alternatives = alternatives
        self._name: str | None = None
        self._grammar: GrammarRule | None = None
        self._source_file = _source_file
        self._source_line = _source_line
        
        # Disambiguation rules
        self.precedence: list[type['Rule']] = []
        self.associativity: dict[type['Rule'], str] = {}
        
        # Track for auto-discovery
        _all_rule_unions.append(self)
        
        # Capture caller's locals so we can find the variable name later
        _capture_caller_locals()
        
        # Capture source location if not provided
        if _source_file is None:
            frame = inspect.currentframe()
            try:
                # Walk up to find the first frame outside this module
                caller = frame.f_back
                while caller and 'easygrammar' in caller.f_code.co_filename:
                    caller = caller.f_back
                if caller:
                    self._source_file = caller.f_code.co_filename
                    self._source_line = caller.f_lineno
            finally:
                del frame
    
    @overload
    def __or__[U: Rule](self, other: type[U]) -> 'RuleUnion[T | U]': ...
    @overload
    def __or__[U](self, other: 'RuleUnion[U]') -> 'RuleUnion[T | U]': ...
    @overload
    def __or__(self, other: type[None]) -> 'RuleUnion[T | None]': ...
    def __or__(self, other):
        if isinstance(other, RuleUnion):
            return RuleUnion(self.alternatives + other.alternatives, 
                           _source_file=self._source_file, _source_line=self._source_line)
        if other is type(None) or other is None:
            return RuleUnion(self.alternatives + [None],
                           _source_file=self._source_file, _source_line=self._source_line)
        return RuleUnion(self.alternatives + [other],
                        _source_file=self._source_file, _source_line=self._source_line)
    
    @overload
    def __ror__[U: Rule](self, other: type[U]) -> 'RuleUnion[U | T]': ...
    @overload
    def __ror__[U](self, other: 'RuleUnion[U]') -> 'RuleUnion[U | T]': ...
    def __ror__(self, other):
        if isinstance(other, RuleUnion):
            return RuleUnion(other.alternatives + self.alternatives,
                           _source_file=self._source_file, _source_line=self._source_line)
        return RuleUnion([other] + self.alternatives,
                        _source_file=self._source_file, _source_line=self._source_line)
    
    def _register_with_name(self, name: str, source_file: str, source_line: int) -> None:
        """Internal registration with explicit source info."""
        from .grammar import GrammarRule, GrammarSequence, GrammarChoice, GrammarRef, GrammarLiteral, register_rule
        
        if self._grammar is not None:
            return  # Already registered
        
        self._name = name
        
        # Build alternatives
        alt_elements = []
        for alt in self.alternatives:
            if alt is None:
                alt_elements.append(GrammarLiteral(""))
            else:
                alt_elements.append(GrammarRef(alt.__name__, source_file, source_line))
        
        choice = GrammarChoice(alt_elements)
        self._grammar = GrammarRule(
            name=name,
            source_file=source_file,
            source_line=source_line,
            body=GrammarSequence([choice]),
        )
        register_rule(self._grammar)
    
    def register(self, name: str) -> 'RuleUnion':
        """Explicitly register this union as a named rule."""
        frame = inspect.currentframe()
        try:
            caller = frame.f_back
            source_file = caller.f_code.co_filename
            source_line = caller.f_lineno
        finally:
            del frame
        
        self._register_with_name(name, source_file, source_line)
        return self
    
    def __str__(self) -> str:
        alt_names = [a.__name__ if a is not None else 'ε' for a in self.alternatives]
        choice_str = ' | '.join(alt_names)
        if self._name:
            return f'{self._name} ::= {choice_str}'
        return f'({choice_str})'
    
    def __repr__(self) -> str:
        alt_names = [a.__name__ if a is not None else 'None' for a in self.alternatives]
        return f"RuleUnion([{', '.join(alt_names)}])"
    
    def __call__(self, raw: str) -> T:
        """Parse input string using this union as the start rule."""
        from .backend.gll import (
            CompiledGrammar, GLLParser, DisambiguationRules, ParseError
        )
        from .grammar import get_all_rules
        
        # Try to discover the variable name for this union before auto-generating
        # This allows unions defined in local scopes to get proper names
        if self._grammar is None:
            _auto_register_unions()  # Try to find variable name first
        
        # Ensure this union is registered
        if self._grammar is None:
            if self._name is None:
                # Auto-generate a name (fallback if variable name wasn't found)
                self._name = "_Union_" + "_".join(
                    a.__name__ if a is not None else "None" 
                    for a in self.alternatives
                )
            self._register_with_name(
                self._name,
                self._source_file or "",
                self._source_line or 0,
            )
        
        # Get all registered rules
        rules = get_all_rules(all_files=True)
        
        # Build disambiguation rules
        disambig = DisambiguationRules()
        if self.precedence:
            disambig.priority = [
                r.__name__ if isinstance(r, type) else str(r)
                for r in self.precedence
            ]
        if self.associativity:
            disambig.associativity = {
                (r.__name__ if isinstance(r, type) else str(r)): assoc
                for r, assoc in self.associativity.items()
            }
        
        # Compile and parse
        grammar = CompiledGrammar.from_rules(rules)
        parser = GLLParser(grammar, disambig)
        
        result = parser.parse(self._name, raw)
        if result is None:
            raise ParseError(f"Failed to parse as {self._name}", 0, raw)
        
        # Extract tree and hydrate
        tree = parser.extract_tree(result)
        
        # Find which alternative matched based on tree structure
        matched_cls = self._find_matched_alternative(tree, raw)
        if matched_cls is None:
            matched_cls = self.alternatives[0]  # fallback
        
        return _hydrate_tree(tree, raw, matched_cls, grammar, rules)
    
    def _find_matched_alternative(self, tree: 'ParseTree', input_str: str) -> type['Rule'] | None:
        """Determine which alternative in the union was matched."""
        # Look at the tree label to determine which rule matched
        for alt in self.alternatives:
            if alt is None:
                continue
            if tree.label == alt.__name__:
                return alt
            # Check children
            for child in tree.children:
                if child.label == alt.__name__:
                    return alt
        return None


def _auto_register_unions() -> None:
    """
    Scan for unregistered RuleUnion objects in all captured scopes
    and register them with their variable names.
    
    This allows rules defined inside functions to be discovered.
    """
    # Collect all variables from captured locals and current call stack
    all_vars = _get_all_captured_vars()
    
    for name, value in all_vars.items():
        if isinstance(value, RuleUnion) and value._grammar is None:
            source_file = value._source_file or ""
            source_line = value._source_line or 0
            value._register_with_name(name, source_file, source_line)


class RuleMeta(ABCMeta):
    @overload
    def __or__[T: Rule](cls: type[T], other: type[None]) -> RuleUnion[T | None]: ...
    @overload
    def __or__[T: Rule, U: Rule](cls: type[T], other: type[U]) -> RuleUnion[T | U]: ...
    @overload
    def __or__[T: Rule, U](cls: type[T], other: RuleUnion[U]) -> RuleUnion[T | U]: ...
    def __or__(cls, other):
        if isinstance(other, RuleUnion):
            return RuleUnion([cls] + other.alternatives)
        if other is type(None) or other is None:
            return RuleUnion([cls, None])
        return RuleUnion([cls, other])

    @overload
    def __ror__[T: Rule, U: Rule](cls: type[T], other: type[U]) -> RuleUnion[U | T]: ...
    @overload
    def __ror__[T: Rule, U](cls: type[T], other: RuleUnion[U]) -> RuleUnion[U | T]: ...
    def __ror__(cls, other):
        if isinstance(other, RuleUnion):
            return RuleUnion(other.alternatives + [cls])
        return RuleUnion([other, cls])
    
    def __str__(cls) -> str:
        """Return the grammar rule string representation."""
        if hasattr(cls, '_grammar') and cls._grammar is not None:
            return str(cls._grammar)
        return cls.__name__
    
    def __repr__(cls) -> str:
        """Return the grammar rule string representation."""
        return cls.__str__()

    def __call__[T:Rule](cls: type[T], raw: str, /) -> T:
        """Parse input string and return a hydrated Rule instance."""
        from .backend.gll import (
            CompiledGrammar, GLLParser, DisambiguationRules, ParseTree, ParseError
        )
        from .grammar import get_all_rules, lookup_by_name
        
        # Get all registered rules (from the caller's file by default)
        rules = get_all_rules()
        
        # Build disambiguation rules from class attributes if present
        disambig = DisambiguationRules()
        if hasattr(cls, 'precedence'):
            # Convert class references to names
            disambig.priority = [
                r.__name__ if isinstance(r, type) else str(r) 
                for r in cls.precedence
            ]
        if hasattr(cls, 'associativity'):
            disambig.associativity = {
                (r.__name__ if isinstance(r, type) else str(r)): assoc
                for r, assoc in cls.associativity.items()
            }
        
        # Compile grammar and parse
        grammar = CompiledGrammar.from_rules(rules)
        parser = GLLParser(grammar, disambig)
        
        result = parser.parse(cls.__name__, raw)
        if result is None:
            raise ParseError(f"Failed to parse as {cls.__name__}", 0, raw)
        
        # Extract parse tree with disambiguation
        tree = parser.extract_tree(result)
        
        # Hydrate into Rule instance
        return _hydrate_tree(tree, raw, cls, grammar, rules)


def _hydrate_tree(
    tree: 'ParseTree',
    input_str: str,
    target_cls: type,
    grammar: 'CompiledGrammar',
    rules: list,
) -> object:
    """
    Hydrate a parse tree into a Rule instance.
    Populates fields based on captures in the tree.
    """
    from .backend.gll import ParseTree
    
    # Create instance without calling __init__
    instance = object.__new__(target_cls)
    
    # Get matched text
    text = tree.get_text(input_str)
    
    # Find all captures
    captures = tree.find_captures()
    
    # Build a map of rule names to classes
    rule_classes: dict[str, type] = {}
    for rule in rules:
        # Try to find the class with this name in the caller's context
        # This is a simplification - in practice we'd need better class resolution
        rule_classes[rule.name] = target_cls  # placeholder
    
    # Populate captured fields
    for name, capture_trees in captures.items():
        if len(capture_trees) == 1:
            capture_tree = capture_trees[0]
            value = capture_tree.get_text(input_str)
            setattr(instance, name, value)
        else:
            values = [ct.get_text(input_str) for ct in capture_trees]
            setattr(instance, name, values)
    
    # Handle mixin types (Rule, int), (Rule, str), etc.
    for base in target_cls.__mro__:
        if base in (int, float, str, bool) and base is not object:
            try:
                converted = base(text)
                # For mixin types, we want the instance to behave like the base type
                # Store the converted value and override comparison
                object.__setattr__(instance, '_mixin_value', converted)
            except (ValueError, TypeError):
                pass
            break
    
    # Store the matched text and original input
    object.__setattr__(instance, '_text', text)
    object.__setattr__(instance, '_tree', tree)
    object.__setattr__(instance, '_input_str', input_str)
    
    return instance


# @dataclass_transform()
class Rule(ABC, metaclass=RuleMeta):
    """initialize a token subclass as a dataclass"""
    # this is just a placeholder for type-checking. The actual implementation is in the __call__ method.
    @final
    def __init__(self, raw:str, /):
        ...
    
    def __eq__(self, other: object) -> bool:
        """Compare with other values. Supports comparison with mixin base types."""
        if hasattr(self, '_mixin_value'):
            # For mixin types, compare the converted value
            return self._mixin_value == other
        if hasattr(self, '_text'):
            # Compare by matched text
            if isinstance(other, str):
                return self._text == other
            if isinstance(other, Rule) and hasattr(other, '_text'):
                return self._text == other._text
        return self is other
    
    def __hash__(self) -> int:
        if hasattr(self, '_mixin_value'):
            return hash(self._mixin_value)
        if hasattr(self, '_text'):
            return hash(self._text)
        return id(self)
    
    def __str__(self) -> str:
        if hasattr(self, '_text'):
            return self._text
        return super().__str__()
    
    def __repr__(self) -> str:
        if hasattr(self, '_tree') and hasattr(self, '_input_str'):
            return tree_string(self)
        cls_name = self.__class__.__name__
        if hasattr(self, '_text'):
            return f"{cls_name}({self._text!r})"
        return f"{cls_name}()"
    
    # Numeric operations for mixin types (int, float)
    def __int__(self) -> int:
        if hasattr(self, '_mixin_value') and isinstance(self._mixin_value, (int, float)):
            return int(self._mixin_value)
        if hasattr(self, '_text'):
            return int(self._text)
        raise TypeError(f"cannot convert {self.__class__.__name__} to int")
    
    def __float__(self) -> float:
        if hasattr(self, '_mixin_value') and isinstance(self._mixin_value, (int, float)):
            return float(self._mixin_value)
        if hasattr(self, '_text'):
            return float(self._text)
        raise TypeError(f"cannot convert {self.__class__.__name__} to float")

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
            raise ValueError(f'Rule subclass `{target_cls.__name__}` must be defined in a file (e.g. cannot create a grammar rule in the REPL). Source code inspection failed.')
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

            # capture other bare expressions (e.g., char['+-'], sequence[...], etc.)
            if isinstance(stmt, ast.Expr):
                expr_text = ast.get_source_segment(file_source, stmt.value)
                if expr_text is None:
                    try:
                        expr_text = ast.unparse(stmt.value)
                    except Exception:
                        continue
                # Store as anonymous declaration (no name, just the expression)
                sequence.append(("decl", None, expr_text))
                continue

        return sequence


    def __init_subclass__(cls: 'type[Rule]', **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        # ensure that __init__ in this base class was not overridden
        # TODO: can this point to where the __init__ was overridden?
        if cls.__init__ != Rule.__init__:
            raise ValueError(f"Rule subclass `{cls.__name__}` must not override __init__ in the base class.")

        # Capture caller's locals so rules defined in functions can be found later
        _capture_caller_locals()

        # capture the ordered sequence of class-body expressions and declarations
        sequence = Rule._collect_sequence_for_class(cls)
        setattr(cls, "_sequence", sequence)

        # build grammar and register
        try:
            source_file = inspect.getsourcefile(cls) or ""
            _, line_no = inspect.getsourcelines(cls)
        except OSError:
            source_file = ""
            line_no = 0
        
        grammar_rule = _build_grammar(cls.__name__, sequence, source_file, line_no)
        register_rule(grammar_rule)
        setattr(cls, "_grammar", grammar_rule)



# protocol for helper functions
class HelperFunction(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> type[Rule]: ...


# TODO: consider instead making these just classes that we call with arguments, since they aren't rules (char needs special handling though...)
class char(Rule):
    def __class_getitem__(self, item: str): ...
class separator: 
    def __class_getitem__(self, item: str): ...
class at_least: 
    def __class_getitem__(self, item: int): ...
class at_most: 
    def __class_getitem__(self, item: int): ...
class exactly: 
    def __class_getitem__(self, item: int): ...



class either[*Ts](Rule):
    """
    Represents a choice between alternatives.
    Usage: either[A, B, C] or either[A | B | C]
    """
    item: Union[*Ts]  # Type is determined by the alternatives
    
    def __class_getitem__(cls, items):
        # When either[A, B, C] is used, return a RuleUnion
        if not isinstance(items, tuple):
            items = (items,)
        
        alternatives = []
        for item in items:
            if isinstance(item, type) and issubclass(item, Rule):
                alternatives.append(item)
            elif isinstance(item, RuleUnion):
                alternatives.extend(item.alternatives)
            elif item is None or item is type(None):
                alternatives.append(None)
        
        if alternatives:
            return RuleUnion(alternatives)
        
        # Fallback: return a generic alias for type checking purposes
        return super().__class_getitem__(items)
class repeat[T:Rule, *Rules](Rule):
    items: list[T]
class optional[T:Rule](Rule):
    item: T|None
class sequence[*Ts](Rule):
    items: tuple[*Ts]

# TBD how this will work
class _ambiguous[T:Rule](Rule):
    alternatives: list[T]


def tree_string(node: Rule) -> str:
    """
    Generate a tree-formatted string representation of a parsed Rule.
    
    Args:
        node: A hydrated Rule instance from parsing
    
    Returns:
        A string showing the parse tree with box-drawing characters
    
    Example:
        >>> result = Expr("(1+2)*3")
        >>> print(tree_string(result))
        Mul
        ├── left: Paren
        │   └── inner: Add
        │       ├── left: Num
        │       │   └── 1
        │       └── right: Num
        │           └── 2
        └── right: Num
            └── 3
    """
    from .backend.gll import ParseTree
    
    if not hasattr(node, '_tree') or not hasattr(node, '_input_str'):
        return f"{node.__class__.__name__}: {node}"
    
    tree: ParseTree = node._tree
    input_str: str = node._input_str
    
    # Build a map of rule names to their field sequences
    # This helps us infer field names from child order
    rule_fields: dict[str, list[str]] = {}
    
    def get_rule_fields(rule_name: str) -> list[str]:
        """Get the field names for a rule in order."""
        if rule_name in rule_fields:
            return rule_fields[rule_name]
        
        # Try to find the rule class
        all_vars = _get_all_captured_vars()
        for name, value in all_vars.items():
            if isinstance(value, type) and issubclass(value, Rule) and value.__name__ == rule_name:
                # Get the _sequence attribute
                if hasattr(value, '_sequence'):
                    fields = []
                    for item in value._sequence:
                        if item[0] == 'decl' and item[1]:  # Named field
                            fields.append(item[1])
                    rule_fields[rule_name] = fields
                    return fields
        
        rule_fields[rule_name] = []
        return []
    
    # Collect user-defined rule names by looking at the parse tree
    rule_names: set[str] = set()
    union_names: set[str] = set()
    
    def is_user_rule_name(label: str) -> bool:
        """Check if a label is a user-defined rule name (not internal GLL label)."""
        if not label or label.startswith(':') or label.startswith('_'):
            return False
        if any(c in label for c in '+-*[](){}|"\''):
            return False
        if not label[0].isupper():
            return False
        return label.isidentifier()
    
    def collect_rule_names(t: ParseTree) -> None:
        if is_user_rule_name(t.label):
            rule_names.add(t.label)
        for c in t.children:
            collect_rule_names(c)
    collect_rule_names(tree)
    
    # Identify union names by checking if the rule has field definitions
    # Rules with fields are meaningful (Add, Mul, Paren, Num)
    # Rules without fields that just wrap other rules are unions (Expr)
    def is_union_rule(rule_name: str) -> bool:
        """Check if a rule is a union (no fields, just wraps other rules)."""
        all_vars = _get_all_captured_vars()
        for name, value in all_vars.items():
            if isinstance(value, type) and issubclass(value, Rule) and value.__name__ == rule_name:
                # Check if it has any field declarations
                if hasattr(value, '_sequence'):
                    for item in value._sequence:
                        if item[0] == 'decl' and item[1]:  # Has a named field
                            return False
                return False  # It's a Rule class with definition, not a union
            elif isinstance(value, RuleUnion) and value._name == rule_name:
                return True  # It's a RuleUnion
        # Assume unknown rules might be unions if they only contain one child rule
        return True
    
    # Mark all RuleUnion names as unions
    all_vars = _get_all_captured_vars()
    for name, value in all_vars.items():
        if isinstance(value, RuleUnion) and value._name:
            union_names.add(value._name)
    
    # Also detect from the tree: rules that only wrap other rules without adding structure
    def analyze_unions(t: ParseTree) -> None:
        if is_user_rule_name(t.label) and t.label not in union_names:
            if is_union_rule(t.label):
                union_names.add(t.label)
        for c in t.children:
            analyze_unions(c)
    analyze_unions(tree)
    
    # Structured tree node
    class TreeNode:
        def __init__(self, rule_name: str, text: str):
            self.rule_name = rule_name
            self.text = text
            self.children: list[tuple[str | None, TreeNode]] = []
    
    def is_meaningful_rule(label: str) -> bool:
        return is_user_rule_name(label) and label not in union_names
    
    def extract_structure(t: ParseTree, parent_rule: str | None = None, field_index: list[int] | None = None) -> TreeNode | None:
        """Extract meaningful structure from parse tree."""
        if is_meaningful_rule(t.label):
            node = TreeNode(t.label, t.get_text(input_str))
            find_children(t, node, t.label)
            return node
        
        if t.label in union_names:
            for c in t.children:
                result = extract_structure(c, parent_rule, field_index)
                if result:
                    return result
        
        for c in t.children:
            result = extract_structure(c, parent_rule, field_index)
            if result:
                return result
        return None
    
    def find_children(t: ParseTree, parent: TreeNode, parent_rule: str) -> None:
        """Find children, inferring field names from rule definition."""
        fields = get_rule_fields(parent_rule)
        rule_child_index = 0
        
        def process_subtree(pt: ParseTree) -> None:
            nonlocal rule_child_index
            
            if pt.label.startswith(':'):
                # Explicit capture
                capture_name = pt.label[1:]
                rule_node = find_rule_in_tree(pt)
                if rule_node:
                    parent.children.append((capture_name, rule_node))
                else:
                    leaf = TreeNode("", pt.get_text(input_str))
                    parent.children.append((capture_name, leaf))
            elif is_meaningful_rule(pt.label):
                # Infer field name from position
                field_name = None
                if rule_child_index < len(fields):
                    field_name = fields[rule_child_index]
                rule_child_index += 1
                
                rule_node = extract_structure(pt)
                if rule_node:
                    parent.children.append((field_name, rule_node))
            elif pt.label in union_names:
                # Union passthrough - process contents
                for c in pt.children:
                    process_subtree(c)
            else:
                # Continue searching
                for c in pt.children:
                    process_subtree(c)
        
        for child in t.children:
            process_subtree(child)
    
    def find_rule_in_tree(t: ParseTree) -> TreeNode | None:
        """Find a meaningful rule in a tree."""
        if is_meaningful_rule(t.label):
            node = TreeNode(t.label, t.get_text(input_str))
            find_children(t, node, t.label)
            return node
        if t.label in union_names:
            for c in t.children:
                result = find_rule_in_tree(c)
                if result:
                    return result
        for c in t.children:
            result = find_rule_in_tree(c)
            if result:
                return result
        return None
    
    root = extract_structure(tree)
    if not root:
        return f"{node.__class__.__name__}: {node}"
    
    lines: list[str] = []
    
    def render(n: TreeNode, prefix: str, connector: str, child_prefix: str, label: str | None) -> None:
        if n.rule_name:
            if label:
                lines.append(f"{prefix}{connector}{label}: {n.rule_name}")
            else:
                lines.append(f"{prefix}{connector}{n.rule_name}")
            
            if n.children:
                for i, (child_label, child_node) in enumerate(n.children):
                    is_last = (i == len(n.children) - 1)
                    if is_last:
                        render(child_node, child_prefix, "└── ", child_prefix + "    ", child_label)
                    else:
                        render(child_node, child_prefix, "├── ", child_prefix + "│   ", child_label)
            else:
                lines.append(f"{child_prefix}└── {n.text}")
        else:
            if label:
                lines.append(f"{prefix}{connector}{label}: {n.text}")
            else:
                lines.append(f"{prefix}{connector}{n.text}")
    
    render(root, "", "", "", None)
    
    return "\n".join(lines)

