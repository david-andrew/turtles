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
from typing import final, Union, overload, TYPE_CHECKING
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
            if _is_turtles_core_internal_frame(filename):
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
        self.longest_match: bool = False
        
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
                while caller and _is_turtles_core_internal_frame(caller.f_code.co_filename):
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
            self._register_with_name(
                self._name,
                self._source_file or "",
                self._source_line or 0,
            )
        
        # Get source file for the union
        source_file = self._source_file
        
        # Ensure any RuleUnions from that file are registered
        if source_file:
            _auto_register_unions_for_file(source_file)
        
        # Get all registered rules from the union's source file
        rules = get_all_rules(source_file=source_file)
        
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
        if self.longest_match:
            disambig.longest_match.add(self._name)
        
        # Compile and parse
        grammar = CompiledGrammar.from_rules(rules)
        parser = GLLParser(grammar, disambig)
        
        result = parser.parse(self._name, raw)
        if result is None:
            # Get failure info from parser for detailed error message
            failure_info = parser._get_failure_info()
            raise ParseError(
                f"Failed to parse as {self._name}",
                failure_info.position,
                raw,
                failure_info=failure_info,
                grammar=grammar,
                start_rule=self._name,
                source_name=self._source_file or "<input>",
            )
        
        # Extract tree and hydrate
        tree = parser.extract_tree(result)
        
        # Find which alternative matched based on tree structure
        matched_cls = self._find_matched_alternative(tree, raw)
        if matched_cls is None:
            matched_cls = self.alternatives[0]  # fallback
        
        return _hydrate_tree(tree, raw, matched_cls, grammar, rules, source_file=source_file)
    
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
        if union._grammar is None and union._source_file == source_file:
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
        """Return standard class representation. Use str(cls) for grammar form."""
        module = cls.__module__
        if module and module != '__main__':
            return f"<class '{module}.{cls.__name__}'>"
        return f"<class '{cls.__name__}'>"

    def __call__[T:Rule](cls: type[T], raw: str, /) -> T:
        """Parse input string and return a hydrated Rule instance."""
        from .gll import CompiledGrammar, GLLParser, DisambiguationRules, ParseError
        from .grammar import get_all_rules
        
        # Get all registered rules from the Rule's source file
        # This allows Rules to be imported and used from different files
        rule_source_file = None
        if hasattr(cls, '_grammar') and cls._grammar is not None:
            rule_source_file = cls._grammar.source_file
            # Ensure any RuleUnions from that file are registered
            _auto_register_unions_for_file(rule_source_file)
        
        rules = get_all_rules(source_file=rule_source_file)
        
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
        if hasattr(cls, 'longest_match') and cls.longest_match:
            disambig.longest_match.add(cls.__name__)
        
        # Compile grammar and parse
        grammar = CompiledGrammar.from_rules(rules)
        parser = GLLParser(grammar, disambig)
        
        result = parser.parse(cls.__name__, raw)
        if result is None:
            # Get failure info from parser for detailed error message
            failure_info = parser._get_failure_info()
            source_name = rule_source_file if rule_source_file else "<input>"
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
        return _hydrate_tree(tree, raw, cls, grammar, rules, source_file=rule_source_file)


def _build_rule_classes_map(source_file: str | None = None) -> dict[str, type]:
    """Build a map from rule names to Rule classes.
    
    If source_file is provided, includes classes from that file's module.
    """
    import sys
    
    rule_classes: dict[str, type] = {}
    
    # First, include classes from the source file's module if specified
    if source_file is not None:
        for module in sys.modules.values():
            if module is not None and hasattr(module, '__file__') and module.__file__ == source_file:
                for name, value in vars(module).items():
                    if isinstance(value, type) and issubclass(value, Rule) and value is not Rule:
                        rule_classes[value.__name__] = value
                    elif isinstance(value, RuleUnion) and value._name:
                        rule_classes[value._name] = value
                break
    
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
) -> object:
    """
    Hydrate a parse tree into a Rule instance.
    Populates fields based on captures in the tree.
    """    
    # Build a map of rule names to classes on first call
    if rule_classes is None:
        rule_classes = _build_rule_classes_map(source_file)
    
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
        GrammarCharClass, GrammarLiteral, GrammarChoice
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
    
    
    def find_all_rule_nodes(node: ParseTree, rule_name: str, results: list = None, depth: int = 0) -> list[ParseTree]:
        """Find all Rule nodes by name (for repeats)."""
        if results is None:
            results = []
        
        # Found exact match
        if node.label == rule_name:
            results.append(node)
            return results  # Don't descend into the matched rule
        
        # Check compound labels
        has_rule_in_label = '+' in node.label and rule_name in node.label.split('+')
        
        # Don't descend into other Rules (except root and compound labels)
        if node.label in rule_classes and node.label != target_cls.__name__ and not has_rule_in_label:
            return results
        
        # Search children
        for child in node.children:
            find_all_rule_nodes(child, rule_name, results, depth + 1)
        
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
        def _search(n: ParseTree, is_root: bool) -> ParseTree | None:
            # Found exact match (but skip the root to avoid recursion issues)
            if n.label == rule_name:
                if is_root and skip_root:
                    pass  # Skip root, search children instead
                elif id(n) not in consumed_nodes:
                    return n
            
            # Check compound labels (e.g., "Key+WS+Val")
            if '+' in n.label and rule_name in n.label.split('+'):
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
    
    # Analyze the grammar and extract captures
    if isinstance(grammar_rule.body, GrammarSequence):
        for elem in grammar_rule.body.elements:
            if not isinstance(elem, GrammarCapture):
                continue
            
            name = elem.name
            inner = elem.rule
            captures[name] = []
            
            # Unwrap optional
            inner_unwrapped, is_optional = unwrap_optional(inner)
            
            # Determine capture type
            # Only repeats should be in list_captures/string_captures
            # Optionals return [] when absent, single value when present
            if isinstance(inner_unwrapped, GrammarRepeat):
                if is_simple_element(inner_unwrapped.element):
                    string_captures.add(name)
                else:
                    list_captures.add(name)
            
            # Extract based on grammar structure
            ref_name = get_ref_name(inner_unwrapped)
            
            if ref_name:
                # Rule reference capture - find the next unconsumed Rule node
                rule_node = find_next_rule_node(tree, ref_name)
                if rule_node:
                    consumed_nodes.add(id(rule_node))
                    captures[name].append(hydrate_rule_node(rule_node, ref_name))
            elif isinstance(inner_unwrapped, GrammarRepeat):
                # Repeat capture
                repeat_elem = inner_unwrapped.element
                repeat_ref = get_ref_name(repeat_elem)
                
                if repeat_ref:
                    # Repeat of Rules - find all rule nodes
                    rule_nodes = find_all_rule_nodes(tree, repeat_ref)
                    for rn in rule_nodes:
                        if id(rn) not in consumed_nodes:
                            consumed_nodes.add(id(rn))
                            captures[name].append(hydrate_rule_node(rn, repeat_ref))
                else:
                    # Repeat of terminals - find capture node and get text
                    cap_node, cap_start, cap_end = find_capture_node(tree, name)
                    if cap_node and cap_start < cap_end:
                        captures[name].append(input_str[cap_start:cap_end])
            else:
                # Terminal capture (char class, literal, choice of terminals)
                # Check if it's a compound choice that needs span expansion
                compound_span = find_capture_span_for_compound(tree, name, inner_unwrapped)
                if compound_span:
                    cap_start, cap_end = compound_span
                    if cap_start < cap_end:
                        captures[name].append(input_str[cap_start:cap_end])
                else:
                    cap_node, cap_start, cap_end = find_capture_node(tree, name)
                    if cap_node and cap_start < cap_end:
                        captures[name].append(input_str[cap_start:cap_end])
    
    return captures, list_captures, string_captures


def _extract_captures(
    tree: 'ParseTree',
    input_str: str,
    rule_classes: dict[str, type],
    grammar: 'CompiledGrammar',
    rules: list,
    target_cls: type | None = None,
) -> tuple[dict[str, list], set[str], set[str]]:
    """
    Extract captures from a parse tree.
    For each capture, returns either hydrated Rule instances or text values.
    
    Uses two strategies:
    1. Look for explicit :name capture nodes in the tree
    2. Look at the grammar structure to find captured references (like key:JString)
    
    Returns:
        captures: dict mapping capture names to lists of values
        list_captures: set of capture names that should be lists (repeat of complex types)
        string_captures: set of capture names that should be strings (repeat of simple types)
    """
    from .grammar import GrammarSequence, GrammarCapture, GrammarRef, GrammarRepeat, GrammarCharClass, GrammarLiteral, GrammarChoice
    
    captures: dict[str, list] = {}
    list_captures: set[str] = set()  # Repeat of complex types -> list
    string_captures: set[str] = set()  # Repeat of simple types -> string
    capture_expected_types: dict[str, set[str]] = {}  # capture_name -> set of expected rule names
    
    def is_simple_element(elem) -> bool:
        """Check if an element is simple (char class or literal)."""
        return isinstance(elem, (GrammarCharClass, GrammarLiteral))
    
    def get_expected_rule_names(elem) -> set[str]:
        """Get the set of rule names that are valid for this element."""
        from .grammar import GrammarChoice
        names = set()
        if isinstance(elem, GrammarRef):
            # Check if it's a union
            if elem.name in rule_classes:
                cls = rule_classes[elem.name]
                if isinstance(cls, RuleUnion):
                    # Add all alternatives
                    for alt in cls.alternatives:
                        if alt is not None and hasattr(alt, '__name__'):
                            names.add(alt.__name__)
                else:
                    names.add(elem.name)
            else:
                names.add(elem.name)
        elif isinstance(elem, GrammarChoice):
            for alt in elem.alternatives:
                names.update(get_expected_rule_names(alt))
        return names
    
    # First, identify which captures are from repeat elements and categorize them
    if target_cls is not None and hasattr(target_cls, '__name__'):
        rule_name = target_cls.__name__
        for r in rules:
            if r.name == rule_name:
                if isinstance(r.body, GrammarSequence):
                    for elem in r.body.elements:
                        if isinstance(elem, GrammarCapture):
                            if isinstance(elem.rule, GrammarRepeat):
                                # Check if the repeat element is simple
                                if is_simple_element(elem.rule.element):
                                    string_captures.add(elem.name)
                                else:
                                    list_captures.add(elem.name)
                                    # Track expected types for filtering
                                    expected = get_expected_rule_names(elem.rule.element)
                                    if expected:
                                        capture_expected_types[elem.name] = expected
                            elif isinstance(elem.rule, GrammarRef):
                                # Non-repeat capture - still track expected type
                                expected = get_expected_rule_names(elem.rule)
                                if expected:
                                    capture_expected_types[elem.name] = expected
                break
    
    def is_simple_capture_label(label: str) -> bool:
        """Check if a label is a simple capture (just :name, no compound parts)."""
        if not label.startswith(':'):
            return False
        # Simple capture: :name where name is alphanumeric/underscore only
        name = label[1:]
        return name.isidentifier()
    
    # Strategy 1: Look for explicit :name capture nodes
    def visit(node: 'ParseTree', parent: 'ParseTree | None' = None, grandparent: 'ParseTree | None' = None, is_first: bool = False):
        """Visit tree nodes, collecting captures."""
        # If this is a simple capture node (just :name)
        if is_simple_capture_label(node.label):
            capture_name = node.label[1:]
            if capture_name not in captures:
                captures[capture_name] = []
            
            # If the capture node is empty but has a parent with content,
            # this might be a compound label pattern where the capture marker is at the end
            # e.g., parent label "[1-9]+:value" with capture ":value" at end
            # The capture marker is placed AFTER the content it captures.
            #
            # ONLY apply this when there are NO sibling captures in the compound structure.
            # Check both parent AND grandparent for multiple captures.
            if node.start == node.end and parent is not None and parent.start < parent.end:
                # Only use parent text if parent label ends with this capture
                if parent.label.endswith(f':{capture_name}') or parent.label.endswith(f'+:{capture_name}'):
                    # Check if parent or grandparent has multiple captures
                    # If so, each capture is separate and terminals between are anonymous
                    has_sibling_captures = False
                    
                    # Check parent's label
                    parent_parts = parent.label.split('+')
                    capture_parts = [p for p in parent_parts if p.startswith(':')]
                    if len(capture_parts) > 1:
                        has_sibling_captures = True
                    
                    # Also check grandparent if available
                    if not has_sibling_captures and grandparent is not None:
                        gp_parts = grandparent.label.split('+')
                        gp_capture_parts = [p for p in gp_parts if p.startswith(':')]
                        if len(gp_capture_parts) > 1:
                            has_sibling_captures = True
                    
                    if not has_sibling_captures:
                        # Check if the preceding siblings are simple terminals (not compound structures)
                        preceding_siblings = []
                        for sibling in parent.children:
                            if sibling is node:
                                break
                            preceding_siblings.append(sibling)
                        
                        # Check if any sibling is a compound structure or Rule
                        has_compound_sibling = False
                        for sib in preceding_siblings:
                            # Compound label containing other captures or Rules
                            if '+' in sib.label or sib.label in rule_classes:
                                has_compound_sibling = True
                                break
                        
                        if not has_compound_sibling:
                            # Simple case: preceding siblings are terminals that belong to this capture
                            content_start = parent.start
                            content_end = node.start
                            
                            if content_start < content_end:
                                text = input_str[content_start:content_end]
                                if text:
                                    captures[capture_name].append(text)
                    return
            
            # Extract values from this capture's content
            expected_types = capture_expected_types.get(capture_name)
            values = _extract_capture_values(node, input_str, rule_classes, grammar, rules, expected_types)
            captures[capture_name].extend(values)
            return
        
        # If this is a nested Rule node (not the first one), stop
        # Its captures belong to it, not us
        if not is_first and node.label in rule_classes:
            return
        
        # Visit children (including compound labels that may contain captures)
        for child in node.children:
            visit(child, parent=node, grandparent=parent, is_first=False)
    
    # Visit starting from root
    visit(tree, parent=None, grandparent=None, is_first=True)
    
    # Strategy 2: Look at the grammar structure for captured references
    # This handles cases like key:JString where the capture isn't explicit in the tree
    if target_cls is not None and hasattr(target_cls, '__name__'):
        rule_name = target_cls.__name__
        # Find the grammar rule
        grammar_rule = None
        for r in rules:
            if r.name == rule_name:
                grammar_rule = r
                break
        
        if grammar_rule and isinstance(grammar_rule.body, GrammarSequence):
            for elem in grammar_rule.body.elements:
                if isinstance(elem, GrammarCapture):
                    capture_name = elem.name
                    # Skip if we already found this capture
                    if capture_name in captures:
                        continue
                    
                    # Look for the captured element in the tree
                    inner = elem.rule
                    
                    # Unwrap optional pattern: GrammarChoice([inner, GrammarLiteral("")])
                    if isinstance(inner, GrammarChoice):
                        non_empty = [a for a in inner.alternatives 
                                     if not (isinstance(a, GrammarLiteral) and a.value == "")]
                        if len(non_empty) == 1:
                            inner = non_empty[0]
                    
                    if isinstance(inner, GrammarRef):
                        ref_name = inner.name
                        # Find nodes in tree with this label
                        found_nodes = _find_nodes_by_label(tree, ref_name, rule_classes)
                        if found_nodes:
                            if capture_name not in captures:
                                captures[capture_name] = []
                            for node in found_nodes:
                                # Hydrate if it's a Rule, otherwise use text
                                if ref_name in rule_classes:
                                    cls = rule_classes[ref_name]
                                    if isinstance(cls, RuleUnion):
                                        # For unions, find the actual matched alternative
                                        actual_cls = _find_rule_in_tree(node, rule_classes)
                                        if actual_cls:
                                            cls = actual_cls
                                    if isinstance(cls, type) and issubclass(cls, Rule):
                                        hydrated = _hydrate_tree(node, input_str, cls, grammar, rules, rule_classes)
                                        captures[capture_name].append(hydrated)
                                else:
                                    captures[capture_name].append(input_str[node.start:node.end])
    
    return captures, list_captures, string_captures


def _find_nodes_by_label(
    tree: 'ParseTree', 
    label: str, 
    rule_classes: dict[str, type] | None = None,
    depth_limit: int = 15
) -> list['ParseTree']:
    """
    Find all tree nodes with the given label.
    
    When rule_classes is provided, the search stops when hitting a different Rule node
    to avoid finding nodes from nested structures.
    """
    results = []
    
    def search(node: 'ParseTree', depth: int, found_target_already: bool):
        if depth > depth_limit:
            return
        if node.label == label:
            results.append(node)
            return  # Don't search inside found nodes
        
        # If this is a nested Rule node (not the target), don't descend into it
        # This prevents finding nodes from deeply nested structures
        if rule_classes and depth > 0:
            # Check if this node is a Rule (not a capture or internal label)
            if node.label in rule_classes and node.label != label:
                return  # Stop - don't descend into nested Rules
        
        for child in node.children:
            search(child, depth + 1, found_target_already)
    
    search(tree, 0, False)
    return results


def _extract_capture_values(
    capture_node: 'ParseTree',
    input_str: str,
    rule_classes: dict[str, type],
    grammar: 'CompiledGrammar',
    rules: list,
    expected_types: set[str] | None = None,
) -> list:
    """
    Extract values from a capture node.
    Returns a list of hydrated Rule instances or text values.
    
    Args:
        expected_types: If provided, only extract Rule nodes whose names are in this set.
                       This filters out anonymous rules that shouldn't be captured.
    """
    rule_values = []
    
    def is_expected_type(label: str) -> bool:
        """Check if a label matches the expected types."""
        if expected_types is None:
            return True  # No filtering
        return label in expected_types
    
    def find_rule_values(node: 'ParseTree'):
        """Find Rule nodes and hydrate them."""
        # Check if this node is a Rule
        if node.label in rule_classes:
            cls = rule_classes[node.label]
            # If it's a union, find the actual matched alternative
            if isinstance(cls, RuleUnion):
                actual_cls = _find_rule_in_tree(node, rule_classes)
                if actual_cls:
                    cls = actual_cls
                    # Check if the actual class is expected
                    if not is_expected_type(cls.__name__):
                        return  # Skip - not an expected type
                else:
                    return
            else:
                # Check if this rule is expected
                if not is_expected_type(node.label):
                    return  # Skip - not an expected type
            # Hydrate this Rule
            if isinstance(cls, type) and issubclass(cls, Rule):
                hydrated = _hydrate_tree(node, input_str, cls, grammar, rules, rule_classes)
                rule_values.append(hydrated)
                return
        
        # Not a Rule node - check children
        for child in node.children:
            find_rule_values(child)
    
    # First, look for Rule nodes
    for child in capture_node.children:
        find_rule_values(child)
    
    # If Rule nodes were found, return them
    if rule_values:
        return rule_values
    
    # No Rule nodes found - this is a terminal capture, use text
    text = input_str[capture_node.start:capture_node.end]
    if text:
        return [text]
    return []


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
    """Find the first Rule class in a tree."""
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

