from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceKey:
    file: str
    line: int


@dataclass
class GrammarLiteral:
    value: str

    def __str__(self) -> str:
        if not self.value:
            return 'ε'
        escaped = self.value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'


@dataclass
class GrammarCharClass:
    pattern: str  # e.g. "a-zA-Z0-9"

    def __str__(self) -> str:
        return f'[{self.pattern}]'


@dataclass
class GrammarRef:
    name: str  # resolved lazily
    source_file: str
    source_line: int

    def __str__(self) -> str:
        return self.name


@dataclass
class GrammarCapture:
    name: str  # field name
    rule: GrammarElement  # what to match

    def __str__(self) -> str:
        return f'{self.name}:{self.rule}'


@dataclass
class GrammarRepeat:
    element: GrammarElement
    at_least: int = 0
    at_most: int | None = None  # None = unbounded
    separator: 'GrammarElement | None' = None

    def __str__(self) -> str:
        inner = str(self.element)
        
        if self.separator:
            # Expand separator pattern: repeat[A, sep] becomes (A (sep A)*)
            sep_str = str(self.separator)
            
            if self.at_least == 0 and self.at_most is None:
                # Zero or more with separator: (A (sep A)*)?
                return f'({inner} ({sep_str} {inner})*)?'
            elif self.at_least == 1 and self.at_most is None:
                # One or more with separator: (A (sep A)*)
                return f'({inner} ({sep_str} {inner})*)'
            elif self.at_least == 0 and self.at_most == 1:
                # Zero or one: A?
                return f'{inner}?'
            else:
                # Complex bounds - show expanded form with bounds notation
                if self.at_least == self.at_most:
                    return f'({inner} ({sep_str} {inner})*){{{self.at_least}}}'
                elif self.at_most is None:
                    return f'({inner} ({sep_str} {inner})*){{{self.at_least},}}'
                else:
                    return f'({inner} ({sep_str} {inner})*){{{self.at_least},{self.at_most}}}'
        
        # No separator - simple quantifier
        if self.at_least == 0 and self.at_most is None:
            return f'{inner}*'
        elif self.at_least == 1 and self.at_most is None:
            return f'{inner}+'
        elif self.at_least == 0 and self.at_most == 1:
            return f'{inner}?'
        elif self.at_least == self.at_most:
            return f'{inner}{{{self.at_least}}}'
        elif self.at_most is None:
            return f'{inner}{{{self.at_least},}}'
        else:
            return f'{inner}{{{self.at_least},{self.at_most}}}'


@dataclass
class GrammarChoice:
    alternatives: list[GrammarElement] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.alternatives:
            return 'ε'
        parts = [str(a) for a in self.alternatives]
        if len(parts) == 1:
            return parts[0]
        return '(' + ' | '.join(parts) + ')'


@dataclass
class GrammarSequence:
    elements: list[GrammarElement] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.elements:
            return 'ε'
        parts = [str(e) for e in self.elements]
        return ' '.join(parts)


@dataclass
class GrammarRule:
    name: str
    source_file: str
    source_line: int
    body: GrammarSequence

    def __str__(self) -> str:
        return f'{self.name} ::= {self.body}'


GrammarElement = (
    GrammarLiteral
    | GrammarCharClass
    | GrammarRef
    | GrammarCapture
    | GrammarRepeat
    | GrammarChoice
    | GrammarSequence
)


# --- Global Registry ---

_registry_by_location: dict[SourceKey, GrammarRule] = {}
_registry_by_name: dict[str, list[GrammarRule]] = {}


def register_rule(rule: GrammarRule) -> None:
    key = SourceKey(rule.source_file, rule.source_line)
    _registry_by_location[key] = rule
    
    if rule.name not in _registry_by_name:
        _registry_by_name[rule.name] = []
    _registry_by_name[rule.name].append(rule)


def lookup_by_location(file: str, line: int) -> GrammarRule | None:
    key = SourceKey(file, line)
    return _registry_by_location.get(key)


def lookup_by_name(name: str, from_file: str | None = None, from_line: int | None = None) -> GrammarRule | None:
    """
    Look up a rule by name. If from_file is provided, prefer rules from the same file.
    If multiple matches exist in the same file, prefer the one defined closest before from_line.
    """
    rules = _registry_by_name.get(name)
    if not rules:
        return None
    
    if len(rules) == 1:
        return rules[0]
    
    if from_file is None:
        return rules[-1]  # return most recently registered
    
    # prefer rules from the same file
    same_file = [r for r in rules if r.source_file == from_file]
    if not same_file:
        return rules[-1]
    
    if len(same_file) == 1:
        return same_file[0]
    
    # multiple in same file - prefer closest one defined before from_line
    if from_line is not None:
        before = [r for r in same_file if r.source_line < from_line]
        if before:
            return max(before, key=lambda r: r.source_line)
    
    return same_file[-1]


def get_rules_for_file(source_file: str) -> list[GrammarRule]:
    """
    Get all registered grammar rules defined in a specific file.
    """
    from .easygrammar import _auto_register_unions
    _auto_register_unions()
    
    return [r for r in _registry_by_location.values() if r.source_file == source_file]


def get_all_rules(*, all_files: bool = False, source_file: str | None = None) -> list[GrammarRule]:
    """
    Get all registered grammar rules.
    
    By default, returns only rules defined in the caller's file.
    Pass all_files=True to get rules from all files.
    Pass source_file to get rules from a specific file.
    """
    import inspect
    
    # Auto-register any RuleUnion objects from caller's scope
    from .easygrammar import _auto_register_unions
    _auto_register_unions()
    
    if all_files:
        return list(_registry_by_location.values())
    
    if source_file is not None:
        return [r for r in _registry_by_location.values() if r.source_file == source_file]
    
    # Get caller's filename
    frame = inspect.currentframe()
    try:
        caller = frame.f_back
        # Walk up past any wrapper frames in grammar/easygrammar
        while caller:
            filename = caller.f_code.co_filename
            if 'grammar.py' not in filename and 'easygrammar.py' not in filename:
                break
            caller = caller.f_back
        
        if not caller:
            return list(_registry_by_location.values())
        
        caller_file = caller.f_code.co_filename
    finally:
        del frame
    
    # Filter to rules from caller's file
    return [r for r in _registry_by_location.values() if r.source_file == caller_file]


def clear_registry() -> None:
    _registry_by_location.clear()
    _registry_by_name.clear()


def clear_registry_for_file(source_file: str) -> None:
    """Clear only rules from a specific source file."""
    # Remove from location registry
    keys_to_remove = [k for k, v in _registry_by_location.items() if v.source_file == source_file]
    for k in keys_to_remove:
        del _registry_by_location[k]
    
    # Remove from name registry
    for name in list(_registry_by_name.keys()):
        rules = _registry_by_name[name]
        _registry_by_name[name] = [r for r in rules if r.source_file != source_file]
        if not _registry_by_name[name]:
            del _registry_by_name[name]


# --- Annotation Parsing ---

import ast


def _parse_annotation(annotation_str: str, source_file: str, source_line: int) -> GrammarElement:
    """
    Parse an annotation string (e.g. "repeat[char['a-zA-Z'], at_least[1]]") 
    into a GrammarElement structure.
    """
    try:
        node = ast.parse(annotation_str, mode='eval').body
    except SyntaxError:
        return GrammarRef(annotation_str, source_file, source_line)
    
    return _ast_to_grammar(node, source_file, source_line)


def _ast_to_grammar(node: ast.expr, source_file: str, source_line: int) -> GrammarElement:
    """Convert an AST node into a GrammarElement."""
    
    # Handle binary OR: A | B | C -> GrammarChoice
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        alternatives = _flatten_bitor(node, source_file, source_line)
        # check for optional pattern: T | None
        none_alt = [a for a in alternatives if isinstance(a, GrammarRef) and a.name == 'None']
        if none_alt:
            non_none = [a for a in alternatives if not (isinstance(a, GrammarRef) and a.name == 'None')]
            # optional is choice with empty literal
            return GrammarChoice(non_none + [GrammarLiteral("")])
        return GrammarChoice(alternatives)
    
    # Handle subscript: something[...]
    if isinstance(node, ast.Subscript):
        return _parse_subscript(node, source_file, source_line)
    
    # Handle plain name: SomeRule, None, etc.
    if isinstance(node, ast.Name):
        name = node.id
        if name == 'None':
            return GrammarLiteral("")
        return GrammarRef(name, source_file, source_line)
    
    # Handle constant (including None)
    if isinstance(node, ast.Constant):
        if node.value is None:
            return GrammarLiteral("")
        return GrammarLiteral(str(node.value))
    
    # Fallback: unparse and treat as reference
    try:
        text = ast.unparse(node)
    except Exception:
        text = "<unknown>"
    return GrammarRef(text, source_file, source_line)


def _flatten_bitor(node: ast.expr, source_file: str, source_line: int) -> list[GrammarElement]:
    """Flatten nested BitOr nodes (A | B | C) into a list of alternatives."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _flatten_bitor(node.left, source_file, source_line)
        right = _flatten_bitor(node.right, source_file, source_line)
        return left + right
    return [_ast_to_grammar(node, source_file, source_line)]


def _parse_subscript(node: ast.Subscript, source_file: str, source_line: int) -> GrammarElement:
    """Parse subscript expressions like char['a-z'], repeat[T, at_least[1]], etc."""
    
    # Get the name being subscripted
    if not isinstance(node.value, ast.Name):
        # complex subscript base - treat as ref
        try:
            text = ast.unparse(node)
        except Exception:
            text = "<unknown>"
        return GrammarRef(text, source_file, source_line)
    
    base_name = node.value.id
    
    # Extract subscript arguments
    if isinstance(node.slice, ast.Tuple):
        args = list(node.slice.elts)
    else:
        args = [node.slice]
    
    # char['a-zA-Z']
    if base_name == 'char':
        if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
            return GrammarCharClass(args[0].value)
        return GrammarCharClass("")
    
    # repeat[T, modifiers...]
    if base_name == 'repeat':
        return _parse_repeat(args, source_file, source_line)
    
    # either[A | B] or either[A, B, C]
    if base_name == 'either':
        alternatives = []
        for arg in args:
            if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.BitOr):
                alternatives.extend(_flatten_bitor(arg, source_file, source_line))
            else:
                alternatives.append(_ast_to_grammar(arg, source_file, source_line))
        return GrammarChoice(alternatives)
    
    # optional[T]
    if base_name == 'optional':
        if args:
            inner = _ast_to_grammar(args[0], source_file, source_line)
            return GrammarChoice([inner, GrammarLiteral("")])
        return GrammarChoice([GrammarLiteral("")])
    
    # sequence[A, B, C]
    if base_name == 'sequence':
        elements = [_ast_to_grammar(a, source_file, source_line) for a in args]
        return GrammarSequence(elements)
    
    # at_least[n], at_most[n], exactly[n], separator['.'] - these are modifiers, not standalone
    # but if they appear standalone, treat as ref
    if base_name in ('at_least', 'at_most', 'exactly', 'separator'):
        try:
            text = ast.unparse(node)
        except Exception:
            text = base_name
        return GrammarRef(text, source_file, source_line)
    
    # Unknown subscript - treat as reference
    return GrammarRef(base_name, source_file, source_line)


def _parse_repeat(args: list[ast.expr], source_file: str, source_line: int) -> GrammarRepeat:
    """Parse repeat[T, modifiers...] into GrammarRepeat."""
    if not args:
        return GrammarRepeat(GrammarLiteral(""))
    
    # First arg is the element to repeat
    element = _ast_to_grammar(args[0], source_file, source_line)
    
    at_least = 0
    at_most: int | None = None
    separator: GrammarElement | None = None
    
    # Remaining args are modifiers
    for mod in args[1:]:
        if isinstance(mod, ast.Subscript) and isinstance(mod.value, ast.Name):
            mod_name = mod.value.id
            
            if mod_name == 'at_least':
                if isinstance(mod.slice, ast.Constant):
                    at_least = int(mod.slice.value)
            
            elif mod_name == 'at_most':
                if isinstance(mod.slice, ast.Constant):
                    at_most = int(mod.slice.value)
            
            elif mod_name == 'exactly':
                if isinstance(mod.slice, ast.Constant):
                    n = int(mod.slice.value)
                    at_least = n
                    at_most = n
            
            elif mod_name == 'separator':
                # Parse separator as a grammar element (can be string, char class, rule ref, etc.)
                separator = _ast_to_grammar(mod.slice, source_file, source_line)
    
    return GrammarRepeat(element, at_least, at_most, separator)


def _build_grammar(
    name: str,
    sequence: list[tuple],
    source_file: str,
    source_line: int,
) -> GrammarRule:
    """
    Build a GrammarRule from the collected sequence of expressions and declarations.
    
    sequence is a list of tuples like:
        ("expr", "literal string")
        ("decl", "field_name", "annotation_text")
    """
    elements: list[GrammarElement] = []
    
    for item in sequence:
        if item[0] == "expr":
            # Bare string literal
            elements.append(GrammarLiteral(item[1]))
        
        elif item[0] == "decl":
            field_name = item[1]
            annotation_text = item[2]
            
            if annotation_text:
                inner = _parse_annotation(annotation_text, source_file, source_line)
            else:
                inner = GrammarRef("<unknown>", source_file, source_line)
            
            if field_name:
                elements.append(GrammarCapture(field_name, inner))
            else:
                elements.append(inner)
    
    return GrammarRule(
        name=name,
        source_file=source_file,
        source_line=source_line,
        body=GrammarSequence(elements),
    )
