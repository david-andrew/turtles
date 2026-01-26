"""
Domain-specific language (DSL) frontend for defining parsers.

This module provides the core DSL for writing parsers in Turtles. Users define grammars
by creating `Rule` subclasses, where the class body describes the grammar structure.
Named fields become captured values in the parse result, and anonymous literals/patterns
guide parsing without appearing in the result.

The module handles:
- Inspecting `Rule` class bodies and compiling them into context-free grammars
- Hydrating parse trees back into `Rule` instances with captured fields populated
- Providing helper functions (`char`, `repeat`, `optional`, etc.) for building grammars

Example:
```python
class Int(Rule):
    value: repeat[char["0-9"], at_least[1]]

result = Int("42")
assert result.value == "42"
```
"""
from __future__ import annotations

from pathlib import Path
from typing import final, overload, TYPE_CHECKING, Union
from abc import ABC, ABCMeta
import inspect
import ast

from .grammar import register_rule, _build_grammar

if TYPE_CHECKING:
    from .grammar import GrammarRule
    from .gll import ParseTree, CompiledGrammar


class SourceNotAvailableError(Exception):
    """Raised when the turtles DSL is used outside of a source file context."""
    pass


_TURTLES_PACKAGE_DIR = Path(__file__).resolve().parent
_TURTLES_EXAMPLE_DIR = _TURTLES_PACKAGE_DIR / "examples"


def _is_turtles_core_internal_frame(filename: str) -> bool:
    if not filename or filename.startswith("<"):
        return False
    try:
        path = Path(filename).resolve()
        if not path.is_relative_to(_TURTLES_PACKAGE_DIR):
            return False
        return not path.is_relative_to(_TURTLES_EXAMPLE_DIR)
    except Exception:
        return False


def _get_user_frame() -> tuple[str, int]:
    """
    Find the first frame that represents user code (not turtles internals or importlib).
    Returns (filename, lineno).
    
    This walks up the stack looking for the first frame that is:
    - Not part of the turtles package (excluding examples)
    - Not part of importlib
    - Not a frozen module
    """
    frame = inspect.currentframe()
    try:
        while frame is not None:
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno
            
            # Skip frames from within the turtles package itself
            if _is_turtles_core_internal_frame(filename):
                frame = frame.f_back
                continue
            # Skip importlib internals and frozen modules
            if 'importlib' in filename or filename.startswith('<frozen'):
                frame = frame.f_back
                continue
            
            # Found user code
            return filename, lineno
        return "", 0
    finally:
        del frame


def _check_not_in_repl(operation: str) -> None:
    """
    Raise SourceNotAvailableError if the immediate user code is in REPL/exec context.
    
    This checks where the grammar-building operation is being called from in user code,
    not the entire call stack. This allows importing grammars in a REPL while preventing
    definition of new grammars in the REPL.
    
    Args:
        operation: Description of the operation being attempted (e.g., "create Rule union")
    """
    filename, _ = _get_user_frame()
    
    # Check if the user code is in a REPL/exec context
    if filename.startswith('<') or not filename:
        raise SourceNotAvailableError(
            f"Cannot {operation} in REPL/exec context (detected '{filename}'). "
            f"Grammar definitions must be in a .py file. "
            f"You can import and use existing grammars from the REPL."
        )


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
            if not _is_turtles_core_internal_frame(filename):
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
            if (
                not _is_turtles_core_internal_frame(filename)
                and 'importlib' not in filename
                and not filename.startswith('<frozen')
            ):
                result.update(caller.f_locals)
                result.update(caller.f_globals)
            caller = caller.f_back
    finally:
        del frame
    
    return result


class RuleUnion[*Ts]:
    """
    Represents a union of Rule classes (A | B | C).
    Can be registered as a named rule.
    
    Supports disambiguation via:
        union.precedence = [HighestPriorityRule, ..., LowestPriorityRule]
        union.associativity = {Rule: 'left', OtherRule: 'right'}
    """
    def __init__(
        self, 
        alternatives: list[type['Rule']], 
        *, 
        _source_files: set[str] | None = None, 
        _source_line: int | None = None
    ):
        _check_not_in_repl("create Rule union")
        self.alternatives = alternatives
        self._name: str | None = None
        self._grammar: GrammarRule | None = None
        self._source_files: set[str] = _source_files.copy() if _source_files else set()
        self._source_line = _source_line
        
        # Collect source files from all alternatives
        for alt in alternatives:
            if alt is not None and hasattr(alt, '_grammar') and alt._grammar is not None:
                self._source_files.add(alt._grammar.source_file)
        
        # Disambiguation rules
        self.precedence: list[type['Rule']] = []
        self.associativity: dict[type['Rule'], str] = {}
        self.longest_match: bool = False
        
        # Track for auto-discovery
        _all_rule_unions.append(self)
        
        # Capture caller's locals so we can find the variable name later
        _capture_caller_locals()
        
        # Capture source location if not provided - add caller's file to source_files
        frame = inspect.currentframe()
        try:
            # Walk up to find the first frame outside this module
            caller = frame.f_back
            while caller and _is_turtles_core_internal_frame(caller.f_code.co_filename):
                caller = caller.f_back
            if caller:
                self._source_files.add(caller.f_code.co_filename)
                if self._source_line is None:
                    self._source_line = caller.f_lineno
        finally:
            del frame
    
    @overload
    def __or__[U: Rule](self, other: type[U]) -> 'RuleUnion[*Ts, U]': ...
    @overload
    def __or__[U](self, other: 'RuleUnion[U]') -> 'RuleUnion[*Ts, U]': ...
    @overload
    def __or__(self, other: type[None]) -> 'RuleUnion[*Ts, None]': ...
    def __or__(self, other):
        _check_not_in_repl("create Rule union with '|' operator")
        # Merge source files from both operands
        new_files = set(self._source_files)
        if isinstance(other, RuleUnion):
            new_files.update(other._source_files)
            return RuleUnion(self.alternatives + other.alternatives, 
                           _source_files=new_files, _source_line=self._source_line)
        if other is type(None) or other is None:
            return RuleUnion(self.alternatives + [None],
                           _source_files=new_files, _source_line=self._source_line)
        # Add source file from the other Rule if available
        if hasattr(other, '_grammar') and other._grammar is not None:
            new_files.add(other._grammar.source_file)
        return RuleUnion(self.alternatives + [other],
                        _source_files=new_files, _source_line=self._source_line)
    
    @overload
    def __ror__[U: Rule](self, other: type[U]) -> 'RuleUnion[*Ts, U]': ...
    @overload
    def __ror__[U](self, other: 'RuleUnion[U]') -> 'RuleUnion[*Ts, U]': ...
    def __ror__(self, other):
        _check_not_in_repl("create Rule union with '|' operator")
        # Merge source files from both operands
        new_files = set(self._source_files)
        if isinstance(other, RuleUnion):
            new_files.update(other._source_files)
            return RuleUnion(other.alternatives + self.alternatives,
                           _source_files=new_files, _source_line=self._source_line)
        # Add source file from the other Rule if available
        if hasattr(other, '_grammar') and other._grammar is not None:
            new_files.add(other._grammar.source_file)
        return RuleUnion([other] + self.alternatives,
                        _source_files=new_files, _source_line=self._source_line)
    
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
    
    def __call__(self, raw: str) -> Union[*Ts]:
        """Parse input string using this union as the start rule."""
        from .gll import (
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
            # Use first file from set for registration (or empty string)
            primary_source = next(iter(self._source_files), "")
            self._register_with_name(
                self._name,
                primary_source,
                self._source_line or 0,
            )
        
        # Ensure any RuleUnions from all source files are registered
        for source_file in self._source_files:
            _auto_register_unions_for_file(source_file)
        
        # Get all registered rules from all source files in the union
        rules = get_all_rules(source_files=self._source_files)
        
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
        
        # Collect longest_match from ALL registered rules, not just the entry point
        rule_classes = _build_rule_classes_map(source_files=self._source_files)
        for rule_name, rule_cls in rule_classes.items():
            if isinstance(rule_cls, type) and hasattr(rule_cls, 'longest_match') and rule_cls.longest_match:
                disambig.longest_match.add(rule_name)
            elif isinstance(rule_cls, RuleUnion) and hasattr(rule_cls, 'longest_match') and rule_cls.longest_match:
                disambig.longest_match.add(rule_name)
        
        # Compile and parse
        grammar = CompiledGrammar.from_rules(rules)
        parser = GLLParser(grammar, disambig)
        
        result = parser.parse(self._name, raw)
        if result is None:
            # Get failure info from parser for detailed error message
            failure_info = parser._get_failure_info()
            # Use first source file for error message
            primary_source = next(iter(self._source_files), "<input>")
            raise ParseError(
                f"Failed to parse as {self._name}",
                failure_info.position,
                raw,
                failure_info=failure_info,
                grammar=grammar,
                start_rule=self._name,
                source_name=primary_source,
            )
        
        # Extract tree and hydrate
        tree = parser.extract_tree(result)
        
        # Find which alternative matched based on tree structure
        matched_cls = self._find_matched_alternative(tree, raw)
        if matched_cls is None:
            matched_cls = self.alternatives[0]  # fallback
        
        return _hydrate_tree(tree, raw, matched_cls, grammar, rules, source_files=self._source_files)
    
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
            # Use first file from source_files set (or empty string)
            source_file = next(iter(value._source_files), "")
            source_line = value._source_line or 0
            value._register_with_name(name, source_file, source_line)


def _auto_register_unions_for_file(source_file: str) -> None:
    """
    Register any unregistered RuleUnion objects from a specific source file.
    
    This is needed when importing Rules from another file - we need to ensure
    all RuleUnions from that file are registered before parsing.
    """
    import sys
    
    # Find the module for this source file
    source_module = None
    for module in sys.modules.values():
        if module is not None and hasattr(module, '__file__') and module.__file__ == source_file:
            source_module = module
            break
    
    if source_module is None:
        return
    
    # Check all tracked unions from this file
    for union in _all_rule_unions:
        if union._grammar is None and source_file in union._source_files:
            # Search the module's namespace for this union
            for name, value in vars(source_module).items():
                if value is union:
                    union._register_with_name(name, source_file, union._source_line or 0)
                    break


class RuleMeta(ABCMeta):
    @overload
    def __or__[T: Rule](cls: type[T], other: type[None]) -> RuleUnion[T | None]: ...
    @overload
    def __or__[T: Rule, U: Rule](cls: type[T], other: type[U]) -> RuleUnion[T | U]: ...
    @overload
    def __or__[T: Rule, U](cls: type[T], other: RuleUnion[U]) -> RuleUnion[T | U]: ...
    def __or__(cls, other):
        _check_not_in_repl("create Rule union with '|' operator")
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
        _check_not_in_repl("create Rule union with '|' operator")
        if isinstance(other, RuleUnion):
            return RuleUnion(other.alternatives + [cls])
        return RuleUnion([other, cls])
    
    def __str__(cls) -> str:
        """Return the grammar rule string representation."""
        if hasattr(cls, '_grammar') and cls._grammar is not None:
            return str(cls._grammar)
        return cls.__name__
    
    def __repr__(cls) -> str:
        """Return standard class representation. Use str(cls) for grammar form."""
        module = cls.__module__
        if module and module != '__main__':
            return f"<class '{module}.{cls.__name__}'>"
        return f"<class '{cls.__name__}'>"

    def __call__[T:Rule](cls: type[T], raw: str, /) -> T:
        """Parse input string and return a hydrated Rule instance."""
        from .gll import CompiledGrammar, GLLParser, DisambiguationRules, ParseError
        from .grammar import get_all_rules
        
        # Collect source files from the Rule and any rules it references
        source_files: set[str] = set()
        if hasattr(cls, '_grammar') and cls._grammar is not None:
            source_files.add(cls._grammar.source_file)
        
        # Also collect source files from any rules referenced in class annotations
        # This enables cross-file composition when rules from other files are used
        sequence = getattr(cls, '_sequence', None)
        if isinstance(sequence, list):
            for item in sequence:
                if isinstance(item, tuple) and len(item) == 3 and item[0] == 'decl':
                    # item is ("decl", field_name, annotation_text)
                    # Check if the annotation refers to a known Rule with a grammar
                    ann_text = item[2]
                    if ann_text:
                        # Try to find referenced rules in captured locals and modules
                        for name, value in _get_all_captured_vars().items():
                            if isinstance(value, type) and issubclass(value, Rule) and value is not Rule:
                                if hasattr(value, '_grammar') and value._grammar is not None:
                                    if name in ann_text:
                                        source_files.add(value._grammar.source_file)
                            elif isinstance(value, RuleUnion):
                                if value._name and value._name in ann_text:
                                    source_files.update(value._source_files)
        
        # Ensure any RuleUnions from those files are registered
        for source_file in source_files:
            _auto_register_unions_for_file(source_file)
        
        # Get all registered rules from all collected source files
        rules = get_all_rules(source_files=source_files) if source_files else get_all_rules()
        
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
        
        # Collect longest_match from ALL registered rules, not just the entry point
        rule_classes = _build_rule_classes_map(source_files=source_files)
        for rule_name, rule_cls in rule_classes.items():
            if isinstance(rule_cls, type) and hasattr(rule_cls, 'longest_match') and rule_cls.longest_match:
                disambig.longest_match.add(rule_name)
            elif isinstance(rule_cls, RuleUnion) and hasattr(rule_cls, 'longest_match') and rule_cls.longest_match:
                disambig.longest_match.add(rule_name)
        
        # Compile grammar and parse
        grammar = CompiledGrammar.from_rules(rules)
        parser = GLLParser(grammar, disambig)
        
        result = parser.parse(cls.__name__, raw)
        if result is None:
            # Get failure info from parser for detailed error message
            failure_info = parser._get_failure_info()
            source_name = next(iter(source_files), "<input>") if source_files else "<input>"
            raise ParseError(
                f"Failed to parse as {cls.__name__}",
                failure_info.position,
                raw,
                failure_info=failure_info,
                grammar=grammar,
                start_rule=cls.__name__,
                source_name=source_name,
            )
        
        # Extract parse tree with disambiguation
        tree = parser.extract_tree(result)
        
        # Hydrate into Rule instance
        return _hydrate_tree(tree, raw, cls, grammar, rules, source_files=source_files)


def _build_rule_classes_map(
    source_file: str | None = None,
    source_files: set[str] | None = None,
) -> dict[str, type]:
    """Build a map from rule names to Rule classes.
    
    If source_file is provided, includes classes from that file's module.
    If source_files is provided, includes classes from all those files' modules.
    """
    import sys
    
    rule_classes: dict[str, type] = {}
    
    # Determine which files to include
    files_to_include: set[str] = set()
    if source_files is not None:
        files_to_include = source_files
    elif source_file is not None:
        files_to_include = {source_file}
    
    # Include classes from the specified files' modules
    if files_to_include:
        for module in sys.modules.values():
            if module is not None and hasattr(module, '__file__') and module.__file__ in files_to_include:
                for name, value in vars(module).items():
                    if isinstance(value, type) and issubclass(value, Rule) and value is not Rule:
                        rule_classes[value.__name__] = value
                    elif isinstance(value, RuleUnion) and value._name:
                        rule_classes[value._name] = value
    
    # Then add from captured vars (later entries override)
    all_vars = _get_all_captured_vars()
    for name, value in all_vars.items():
        if isinstance(value, type) and issubclass(value, Rule) and value is not Rule:
            rule_classes[value.__name__] = value
        elif isinstance(value, RuleUnion) and value._name:
            rule_classes[value._name] = value
    return rule_classes


def _hydrate_tree(
    tree: 'ParseTree',
    input_str: str,
    target_cls: type,
    grammar: 'CompiledGrammar',
    rules: list,
    rule_classes: dict[str, type] | None = None,
    source_file: str | None = None,
    source_files: set[str] | None = None,
) -> object:
    """
    Hydrate a parse tree into a Rule instance.
    Populates fields based on captures in the tree.
    """    
    # Build a map of rule names to classes on first call
    if rule_classes is None:
        rule_classes = _build_rule_classes_map(source_file=source_file, source_files=source_files)
    
    # Get matched text
    text = tree.get_text(input_str)
    
    # Create instance without calling __init__
    # For mixin types (Rule, int), (Rule, str), etc., we need to use their __new__
    mixin_base = None
    for base in target_cls.__mro__:
        if base in (int, float, str, bool) and base is not object:
            mixin_base = base
            break
    
    if mixin_base:
        # Need to use mixin type's __new__ with the text value
        try:
            instance = mixin_base.__new__(target_cls, text)
        except (ValueError, TypeError):
            instance = object.__new__(target_cls)
    else:
        instance = object.__new__(target_cls)
    
    # Store the actual class for __class__ property
    object.__setattr__(instance, '_actual_class', target_cls)
    
    # If the tree label doesn't match target_cls, find the matching subtree
    target_tree = tree
    if tree.label != target_cls.__name__:
        subtree = _find_subtree_for_class(tree, target_cls.__name__)
        if subtree:
            target_tree = subtree
    
    # Find all captures and hydrate them using grammar-guided extraction
    captures, list_captures, string_captures = _grammar_guided_extract(
        target_tree, input_str, target_cls, rules, rule_classes
    )
    
    # Identify optional fields (those typed as optional[X] or X|None)
    optional_fields: set[str] = set()
    sequence = getattr(target_cls, "_sequence", None)
    if isinstance(sequence, list):
        for item in sequence:
            if not isinstance(item, tuple) or len(item) != 3:
                continue
            kind, var_name, annotation_text = item
            if kind != "decl" or not isinstance(var_name, str) or not annotation_text:
                continue
            normalized = annotation_text.replace(" ", "")
            if normalized.startswith("optional[") or "|None" in normalized or "None|" in normalized:
                optional_fields.add(var_name)
    
    # Populate captured fields
    for name, capture_values in captures.items():
        if name in string_captures:
            # Repeat of simple types (char class, literal) - join into string
            setattr(instance, name, ''.join(str(v) for v in capture_values))
        elif name in list_captures:
            # Repeat of complex types - keep as list
            setattr(instance, name, capture_values)
        elif len(capture_values) == 1:
            setattr(instance, name, capture_values[0])
        elif len(capture_values) == 0 and name in optional_fields:
            # Empty optional field - use None instead of empty list
            setattr(instance, name, None)
        else:
            setattr(instance, name, capture_values)
    
    # Handle mixin types (Rule, int), (Rule, str), etc.
    for base in target_cls.__mro__:
        if base in (int, float, str, bool) and base is not object:
            try:
                converted = base(text)
                object.__setattr__(instance, '_mixin_value', converted)
            except (ValueError, TypeError):
                pass
            break
    
    # Store the matched text and original input
    object.__setattr__(instance, '_text', text)
    object.__setattr__(instance, '_tree', tree)
    object.__setattr__(instance, '_input_str', input_str)
    
    # Handle custom converter (__convert__ method)
    if hasattr(target_cls, '__convert__'):
        try:
            converted = instance.__convert__()
            object.__setattr__(instance, '_converted_value', converted)
        except Exception:
            pass
    
    return instance


# =============================================================================
# Grammar-Guided Extraction
# =============================================================================

def _grammar_guided_extract(
    tree: 'ParseTree',
    input_str: str,
    target_cls: type,
    rules: list,
    rule_classes: dict[str, type],
) -> tuple[dict[str, list], set[str], set[str]]:
    """
    Extract captures by walking the grammar and tree together.
    
    Key tree structure patterns:
    - Terminal captures: `:name` node with text span
    - Rule captures: Rule name appears directly in tree (not `:name`)
    - Empty optional: `:name` with empty span (start == end)
    - Repeat with separator: compound labels like `Num+Num` containing items
    
    Returns:
        captures: dict mapping capture names to lists of values
        list_captures: set of capture names that should be lists
        string_captures: set of capture names that should be strings
    """
    from .grammar import (
        GrammarSequence, GrammarCapture, GrammarRef, GrammarRepeat, 
        GrammarCharClass, GrammarLiteral, GrammarChoice,
        CaptureKind
    )
    
    captures: dict[str, list] = {}
    list_captures: set[str] = set()
    string_captures: set[str] = set()
    
    # Find the grammar rule for target_cls
    grammar_rule = None
    if target_cls is not None and hasattr(target_cls, '__name__'):
        rule_name = target_cls.__name__
        for r in rules:
            if r.name == rule_name:
                grammar_rule = r
                break
    
    if grammar_rule is None:
        return captures, list_captures, string_captures
    
    def is_simple_element(elem) -> bool:
        """Check if an element is simple (char class or literal)."""
        if isinstance(elem, (GrammarCharClass, GrammarLiteral)):
            return True
        if isinstance(elem, GrammarChoice):
            return all(is_simple_element(a) for a in elem.alternatives)
        if isinstance(elem, GrammarSequence):
            return all(is_simple_element(e) for e in elem.elements)
        return False
    
    def unwrap_optional(elem):
        """Unwrap optional pattern: GrammarChoice([inner, GrammarLiteral("")])"""
        if isinstance(elem, GrammarChoice):
            non_empty = [a for a in elem.alternatives 
                         if not (isinstance(a, GrammarLiteral) and a.value == "")]
            if len(non_empty) == 1:
                return non_empty[0], True
        return elem, False
    
    def get_ref_name(elem) -> str | None:
        """Get the reference name from an element if it's a GrammarRef."""
        if isinstance(elem, GrammarRef):
            return elem.name
        return None
    
    
    def expand_rule_names(name: str) -> set[str]:
        """Expand a rule name to include RuleUnion alternatives."""
        names = {name}
        if name in rule_classes:
            cls = rule_classes[name]
            if isinstance(cls, RuleUnion):
                for alt in cls.alternatives:
                    if alt is not None and hasattr(alt, '__name__'):
                        names.add(alt.__name__)
        return names
    
    def find_all_rule_nodes(node: ParseTree, rule_name: str, results: list = None, depth: int = 0, skip_root: bool = True) -> list[ParseTree]:
        """Find all Rule nodes by name (for repeats)."""
        if results is None:
            results = []
        
        # Expand rule name to include RuleUnion alternatives
        target_names = expand_rule_names(rule_name)
        
        # Found exact match (but skip root to avoid returning the tree itself)
        if node.label in target_names:
            if depth == 0 and skip_root:
                pass  # Skip root node, search children instead
            else:
                results.append(node)
                return results  # Don't descend into the matched rule
        
        # Check compound labels
        has_rule_in_label = '+' in node.label and any(n in node.label.split('+') for n in target_names)
        
        # Don't descend into other Rules (except root and compound labels)
        if node.label in rule_classes and node.label != target_cls.__name__ and not has_rule_in_label:
            return results
        
        # Search children
        for child in node.children:
            find_all_rule_nodes(child, rule_name, results, depth + 1, skip_root=False)
        
        return results
    
    def find_capture_node(node: ParseTree, capture_name: str) -> tuple[ParseTree | None, int, int]:
        """
        Find a :name capture node and return (node, start, end).
        Returns the actual capture node and its span.
        """
        # Check if this is the exact capture node
        if node.label == f':{capture_name}':
            return node, node.start, node.end
        
        # Check compound labels
        if f':{capture_name}' in node.label:
            # Search children for more specific capture node
            for child in node.children:
                result, start, end = find_capture_node(child, capture_name)
                if result:
                    return result, start, end
            # This compound node itself represents the capture
            return node, node.start, node.end
        
        # Don't descend into other Rules
        if node.label in rule_classes and node.label != target_cls.__name__:
            return None, 0, 0
        
        # Search children
        for child in node.children:
            result, start, end = find_capture_node(child, capture_name)
            if result:
                return result, start, end
        
        return None, 0, 0
    
    def find_capture_span_for_compound(node: ParseTree, capture_name: str, grammar_elem) -> tuple[int, int] | None:
        """
        For compound grammar elements (choices with sequences), find the full span.
        This handles cases like either['0', sequence[char['1-9'], repeat[...]]]
        where the tree has [1-9]+:value but we need the full span.
        """
        # Only applies to choices
        if not isinstance(grammar_elem, GrammarChoice):
            return None
        
        # Check if any alternative is a sequence
        has_sequence_alt = any(
            isinstance(alt, GrammarSequence) and len(alt.elements) > 1
            for alt in grammar_elem.alternatives
        )
        if not has_sequence_alt:
            return None
        
        # Find the compound label containing this capture
        def find_compound_label(n: ParseTree) -> ParseTree | None:
            if f':{capture_name}' in n.label and '+' in n.label:
                # Check if this has only one capture
                if n.label.count(':') == 1:
                    return n
            for child in n.children:
                result = find_compound_label(child)
                if result:
                    return result
            return None
        
        compound = find_compound_label(node)
        if compound:
            return compound.start, compound.end
        return None
    
    def hydrate_rule_node(node: ParseTree, ref_name: str):
        """Hydrate a Rule node."""
        # First, check if the node label itself is a Rule class
        if node.label in rule_classes:
            cls = rule_classes[node.label]
            if isinstance(cls, type) and issubclass(cls, Rule):
                return _hydrate_tree(node, input_str, cls, None, rules, rule_classes)
        
        # Otherwise, look up by ref_name
        if ref_name in rule_classes:
            cls = rule_classes[ref_name]
            if isinstance(cls, RuleUnion):
                actual_cls = _find_rule_in_tree(node, rule_classes)
                if actual_cls:
                    cls = actual_cls
            if isinstance(cls, type) and issubclass(cls, Rule):
                return _hydrate_tree(node, input_str, cls, None, rules, rule_classes)
        return input_str[node.start:node.end]
    
    # Track consumed nodes to avoid reusing the same node for multiple captures
    consumed_nodes: set[int] = set()  # Set of node ids
    
    def find_next_rule_node(node: ParseTree, rule_name: str, skip_root: bool = True) -> ParseTree | None:
        """Find the next unconsumed Rule node by name in document order."""
        # Expand rule name to include RuleUnion alternatives
        target_names = expand_rule_names(rule_name)
        
        def _search(n: ParseTree, is_root: bool) -> ParseTree | None:
            # Found exact match (but skip the root to avoid recursion issues)
            if n.label in target_names:
                if is_root and skip_root:
                    pass  # Skip root, search children instead
                elif id(n) not in consumed_nodes:
                    return n
            
            # Check compound labels (e.g., "Key+WS+Val")
            if '+' in n.label and any(name in n.label.split('+') for name in target_names):
                for child in n.children:
                    result = _search(child, False)
                    if result:
                        return result
            
            # Don't descend into other Rules (except the root)
            if n.label in rule_classes and n.label != target_cls.__name__:
                return None
            
            # Search children in order
            for child in n.children:
                result = _search(child, False)
                if result:
                    return result
            
            return None
        
        return _search(node, True)
    
    # Helper to find all rule nodes for a set of target names
    def find_rule_nodes_for_targets(target_names: frozenset[str]) -> list:
        """Find all rule nodes matching any of the target names."""
        all_nodes = []
        seen_ids = set()
        for name in target_names:
            nodes = find_all_rule_nodes(tree, name)
            for node in nodes:
                node_id = id(node)
                if node_id not in consumed_nodes and node_id not in seen_ids:
                    all_nodes.append(node)
                    seen_ids.add(node_id)
        return all_nodes
    
    def find_single_rule_node_for_targets(target_names: frozenset[str]):
        """Find the first unconsumed rule node matching any target name."""
        for name in target_names:
            node = find_next_rule_node(tree, name)
            if node:
                return node
        return None
    
    # Analyze the grammar and extract captures using descriptors
    if isinstance(grammar_rule.body, GrammarSequence):
        for elem in grammar_rule.body.elements:
            if not isinstance(elem, GrammarCapture):
                continue
            
            name = elem.name
            desc = elem.descriptor
            captures[name] = []
            
            # Use descriptor if available
            if desc is not None:
                # Track list/string captures based on descriptor
                if desc.is_list:
                    # Only use string_captures for pure terminal repeats (no rule refs)
                    # Mixed captures (text_fallback=True) still go to list_captures
                    if desc.kind == CaptureKind.TEXT and not desc.text_fallback and len(desc.target_names) == 0:
                        string_captures.add(name)
                    else:
                        list_captures.add(name)
                
                # Expand target names with runtime union info
                target_names = set(desc.target_names)
                for tname in list(desc.target_names):
                    target_names.update(expand_rule_names(tname))
                target_names_frozen = frozenset(target_names)
                
                # Extract based on descriptor kind
                match desc.kind:
                    case CaptureKind.RULE:
                        # Single rule reference
                        rule_node = find_single_rule_node_for_targets(target_names_frozen)
                        if rule_node:
                            consumed_nodes.add(id(rule_node))
                            # Determine the actual rule name from the node label
                            ref_name = rule_node.label if rule_node.label in rule_classes else next(iter(target_names_frozen), None)
                            if ref_name:
                                captures[name].append(hydrate_rule_node(rule_node, ref_name))
                    
                    case CaptureKind.OPTIONAL_RULE:
                        # Optional rule reference - same as RULE but no error if not found
                        rule_node = find_single_rule_node_for_targets(target_names_frozen)
                        if rule_node:
                            consumed_nodes.add(id(rule_node))
                            ref_name = rule_node.label if rule_node.label in rule_classes else next(iter(target_names_frozen), None)
                            if ref_name:
                                captures[name].append(hydrate_rule_node(rule_node, ref_name))
                    
                    case CaptureKind.RULE_LIST:
                        # List of rules
                        rule_nodes = find_rule_nodes_for_targets(target_names_frozen)
                        for rn in rule_nodes:
                            consumed_nodes.add(id(rn))
                            ref_name = rn.label if rn.label in rule_classes else next(iter(target_names_frozen), None)
                            if ref_name:
                                captures[name].append(hydrate_rule_node(rn, ref_name))
                    
                    case CaptureKind.TEXT | CaptureKind.OPTIONAL_TEXT:
                        # Terminal capture - extract text span
                        # Check for compound choice that needs span expansion
                        inner_unwrapped, _ = unwrap_optional(elem.rule)
                        compound_span = find_capture_span_for_compound(tree, name, inner_unwrapped)
                        if compound_span:
                            cap_start, cap_end = compound_span
                            if cap_start < cap_end:
                                captures[name].append(input_str[cap_start:cap_end])
                        else:
                            cap_node, cap_start, cap_end = find_capture_node(tree, name)
                            if cap_node and cap_start < cap_end:
                                captures[name].append(input_str[cap_start:cap_end])
                    
                    case CaptureKind.MIXED:
                        # Mixed choice - try rules first, fall back to text
                        found = False
                        rule_node = find_single_rule_node_for_targets(target_names_frozen)
                        if rule_node:
                            consumed_nodes.add(id(rule_node))
                            ref_name = rule_node.label if rule_node.label in rule_classes else next(iter(target_names_frozen), None)
                            if ref_name:
                                captures[name].append(hydrate_rule_node(rule_node, ref_name))
                                found = True
                        
                        if not found:
                            # Fall back to text capture
                            inner_unwrapped, _ = unwrap_optional(elem.rule)
                            compound_span = find_capture_span_for_compound(tree, name, inner_unwrapped)
                            if compound_span:
                                cap_start, cap_end = compound_span
                                if cap_start < cap_end:
                                    captures[name].append(input_str[cap_start:cap_end])
                            else:
                                cap_node, cap_start, cap_end = find_capture_node(tree, name)
                                if cap_node and cap_start < cap_end:
                                    captures[name].append(input_str[cap_start:cap_end])
            
            else:
                # Fallback: No descriptor - use legacy logic
                inner = elem.rule
                inner_unwrapped, is_optional = unwrap_optional(inner)
                
                if isinstance(inner_unwrapped, GrammarRepeat):
                    if is_simple_element(inner_unwrapped.element):
                        string_captures.add(name)
                    else:
                        list_captures.add(name)
                
                ref_name = get_ref_name(inner_unwrapped)
                
                if ref_name:
                    rule_node = find_next_rule_node(tree, ref_name)
                    if rule_node:
                        consumed_nodes.add(id(rule_node))
                        captures[name].append(hydrate_rule_node(rule_node, ref_name))
                elif isinstance(inner_unwrapped, GrammarRepeat):
                    repeat_elem = inner_unwrapped.element
                    repeat_ref = get_ref_name(repeat_elem)
                    
                    if repeat_ref:
                        rule_nodes = find_all_rule_nodes(tree, repeat_ref)
                        for rn in rule_nodes:
                            if id(rn) not in consumed_nodes:
                                consumed_nodes.add(id(rn))
                                captures[name].append(hydrate_rule_node(rn, repeat_ref))
                    else:
                        cap_node, cap_start, cap_end = find_capture_node(tree, name)
                        if cap_node and cap_start < cap_end:
                            captures[name].append(input_str[cap_start:cap_end])
                else:
                    cap_node, cap_start, cap_end = find_capture_node(tree, name)
                    if cap_node and cap_start < cap_end:
                        captures[name].append(input_str[cap_start:cap_end])
    
    return captures, list_captures, string_captures


def _find_subtree_for_class(tree: 'ParseTree', class_name: str) -> 'ParseTree | None':
    """Find the subtree whose label matches the given class name."""
    if tree.label == class_name:
        return tree
    for child in tree.children:
        result = _find_subtree_for_class(child, class_name)
        if result:
            return result
    return None


def _find_rule_in_tree(tree: 'ParseTree', rule_classes: dict[str, type]) -> type | None:
    """Find the first Rule class in a tree's children (not the tree node itself)."""
    for child in tree.children:
        if child.label in rule_classes:
            cls = rule_classes[child.label]
            if isinstance(cls, type) and issubclass(cls, Rule):
                return cls
        result = _find_rule_in_tree(child, rule_classes)
        if result:
            return result
    return None


type AsDictResult = str | int | float | bool | dict[str, AsDictResult] | list[AsDictResult]


# @dataclass_transform()
class Rule(ABC, metaclass=RuleMeta):
    """initialize a token subclass as a dataclass"""
    # this is just a placeholder for type-checking. The actual implementation is in the __call__ method.
    @final
    def __init__(self, raw:str, /):
        ...
    
    def _get_actual_class(self):
        """Get the actual class (not mixin base) for internal use."""
        try:
            return object.__getattribute__(self, '_actual_class')
        except AttributeError:
            # Fallback - shouldn't normally happen for hydrated instances
            return Rule
    
    def _get_effective_class(self):
        """Get the effective class (mixin base or converted type) for type checking."""
        actual_class = self._get_actual_class()
        
        # Check for mixin base (int, float, str, bool)
        for base in actual_class.__mro__:
            if base in (int, float, str, bool):
                return base
        
        # Check for converter result type
        try:
            converted = object.__getattribute__(self, '_converted_value')
            return type(converted)
        except AttributeError:
            pass
        
        return actual_class
    
    @property
    def __class__(self):
        """Return the mixin base type or converted value type for type() and isinstance()."""
        return self._get_effective_class()
    
    def __eq__(self, other: object) -> bool:
        """Compare with other values. Supports comparison with mixin/converted types."""
        # Allow comparison with class (e.g., instance == JNull)
        if isinstance(other, type) and issubclass(other, Rule):
            actual_cls = self._get_actual_class()
            return issubclass(actual_cls, other)
        # Check converted value first (from __convert__)
        if hasattr(self, '_converted_value'):
            return self._converted_value == other
        # Then check mixin value
        if hasattr(self, '_mixin_value'):
            return self._mixin_value == other
        if hasattr(self, '_text'):
            # Compare by matched text
            if isinstance(other, str):
                return self._text == other
            if isinstance(other, Rule) and hasattr(other, '_text'):
                return self._text == other._text
        return self is other
    
    def __hash__(self) -> int:
        if hasattr(self, '_converted_value'):
            return hash(self._converted_value)
        if hasattr(self, '_mixin_value'):
            return hash(self._mixin_value)
        if hasattr(self, '_text'):
            return hash(self._text)
        return id(self)
    
    def _get_comparable_value(self):
        """Get the value to use for comparisons."""
        if hasattr(self, '_converted_value'):
            return self._converted_value
        if hasattr(self, '_mixin_value'):
            return self._mixin_value
        if hasattr(self, '_text'):
            return self._text
        return None
    
    def __lt__(self, other: object) -> bool:
        val = self._get_comparable_value()
        if val is not None:
            return val < other
        return NotImplemented
    
    def __le__(self, other: object) -> bool:
        val = self._get_comparable_value()
        if val is not None:
            return val <= other
        return NotImplemented
    
    def __gt__(self, other: object) -> bool:
        val = self._get_comparable_value()
        if val is not None:
            return val > other
        return NotImplemented
    
    def __ge__(self, other: object) -> bool:
        val = self._get_comparable_value()
        if val is not None:
            return val >= other
        return NotImplemented
    
    def __bool__(self) -> bool:
        """Return boolean value of converted/mixin value."""
        if hasattr(self, '_converted_value'):
            return bool(self._converted_value)
        if hasattr(self, '_mixin_value'):
            return bool(self._mixin_value)
        # Default: non-empty text is truthy
        if hasattr(self, '_text'):
            return bool(self._text)
        return True
    
    def __str__(self) -> str:
        if hasattr(self, '_text'):
            return self._text
        return super().__str__()
    
    def __repr__(self) -> str:
        if hasattr(self, '_tree') and hasattr(self, '_input_str'):
            return tree_string(self)
        # Use actual class name, not mixin base
        actual_cls = self._get_actual_class()
        cls_name = actual_cls.__name__
        if hasattr(self, '_text'):
            return f"{cls_name}({self._text!r})"
        return f"{cls_name}()"

    def as_dict(self) -> AsDictResult:
        # If we have a converted value, return it directly
        if hasattr(self, '_converted_value'):
            return self._converted_value
        # If we have a mixin value, return it directly
        if hasattr(self, '_mixin_value'):
            return self._mixin_value
        
        # Use actual class, not mixin base
        cls = self._get_actual_class()
        optional_fields: set[str] = set()
        sequence = getattr(cls, "_sequence", None)
        if isinstance(sequence, list):
            for item in sequence:
                if not isinstance(item, tuple) or len(item) != 3:
                    continue
                kind, var_name, annotation_text = item
                if kind != "decl" or not isinstance(var_name, str) or not annotation_text:
                    continue
                normalized = annotation_text.replace(" ", "")
                if normalized.startswith("optional[") or "|None" in normalized or "None|" in normalized:
                    optional_fields.add(var_name)

        def convert(value: str | int | float | bool | Rule | list | tuple) -> AsDictResult:
            if isinstance(value, Rule):
                return value.as_dict()
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, tuple):
                return [convert(v) for v in value]
            return value

        fields: dict[str, AsDictResult] = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            # Skip empty optional fields (None or empty list for legacy)
            if key in optional_fields and (value is None or value == []):
                continue
            fields[key] = convert(value)

        if fields:
            return fields
        # No fields, no mixin/converted value - return text
        return getattr(self, "_text", "")
    
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

        # Check that the class is defined in a source file (not REPL/exec)
        # We check the class's source file, not the call stack, because the class
        # definition is what matters, not where the import started from
        try:
            source_file = inspect.getsourcefile(cls)
            if not source_file:
                raise SourceNotAvailableError(
                    f"Cannot define Rule subclass '{cls.__name__}' in REPL/exec context. "
                    f"Grammar definitions must be in a .py file. "
                    f"You can import and use existing grammars from the REPL."
                )
            _, line_no = inspect.getsourcelines(cls)
        except OSError as e:
            raise SourceNotAvailableError(
                f"Cannot define Rule subclass '{cls.__name__}' in REPL/exec context. "
                f"Grammar definitions must be in a .py file. "
                f"You can import and use existing grammars from the REPL."
            ) from e

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
        grammar_rule = _build_grammar(cls.__name__, sequence, source_file, line_no)
        register_rule(grammar_rule)
        setattr(cls, "_grammar", grammar_rule)



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

class repeat[T:Rule, *Rules](Rule): ...
class optional[T:Rule](Rule): ...
class sequence[*Ts](Rule): ...

# # TBD how this will work
# class _ambiguous[T:Rule](Rule):
#     alternatives: list[T]


def tree_string(node: Rule) -> str:
    """
    Generate a tree-formatted string representation of a parsed Rule.
    
    Works from the hydrated instance's actual attributes, correctly showing
    all items in lists and nested structures.
    
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
        │       │   └── value: 1
        │       └── right: Num
        │           └── value: 2
        └── right: Num
            └── value: 3
    """
    lines: list[str] = []
    
    def get_fields(obj: Rule) -> list[tuple[str, object]]:
        """Get field name/value pairs from a Rule instance, skipping empty optionals."""
        fields = []
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):  # Skip private attributes
                # Skip None (empty optional fields) and empty lists (legacy)
                if value is None or (isinstance(value, list) and len(value) == 0):
                    continue
                fields.append((key, value))
        return fields
    
    def render_value(value: object, prefix: str, connector: str, label: str | None) -> None:
        """Render a single value."""
        if isinstance(value, Rule):
            # It's a Rule instance - show class name and recurse
            class_name = value.__class__.__name__
            if label:
                lines.append(f"{prefix}{connector}{label}: {class_name}")
            else:
                lines.append(f"{prefix}{connector}{class_name}")
            
            # Get fields for this Rule
            fields = get_fields(value)
            child_prefix = prefix + ("    " if connector == "└── " else "│   ")
            
            if fields:
                for i, (field_name, field_value) in enumerate(fields):
                    is_last = (i == len(fields) - 1)
                    next_connector = "└── " if is_last else "├── "
                    render_value(field_value, child_prefix, next_connector, field_name)
            else:
                # No fields - show the text value
                if hasattr(value, '_text'):
                    lines.append(f"{child_prefix}└── {value._text}")
        elif isinstance(value, list):
            # It's a list - render each item
            if label:
                lines.append(f"{prefix}{connector}{label}: [{len(value)} items]")
            child_prefix = prefix + ("    " if connector == "└── " else "│   ")
            for i, item in enumerate(value):
                is_last = (i == len(value) - 1)
                next_connector = "└── " if is_last else "├── "
                render_value(item, child_prefix, next_connector, f"[{i}]")
        else:
            # It's a simple value (string, int, etc.)
            if label:
                lines.append(f"{prefix}{connector}{label}: {value}")
            else:
                lines.append(f"{prefix}{connector}{value}")
    
    # Start with the root node
    class_name = node.__class__.__name__
    lines.append(class_name)
    
    fields = get_fields(node)
    for i, (field_name, field_value) in enumerate(fields):
        is_last = (i == len(fields) - 1)
        connector = "└── " if is_last else "├── "
        render_value(field_value, "", connector, field_name)
    
    return "\n".join(lines)

