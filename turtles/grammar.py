from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
import ast


class CaptureKind(Enum):
    """Describes how to extract a captured value from the parse tree."""
    RULE = auto()           # Single rule reference: find node, hydrate
    RULE_LIST = auto()      # Repeat of rules: find all nodes, hydrate each
    TEXT = auto()           # Terminal capture: extract text span
    OPTIONAL_RULE = auto()  # Optional rule: find node or return None
    OPTIONAL_TEXT = auto()  # Optional terminal: extract text or return None
    MIXED = auto()          # Mixed choice (rules + terminals): try rules, fall back to text


@dataclass
class CaptureDescriptor:
    """
    Describes how to extract a captured value from the parse tree.
    Computed at grammar build time, used at extraction time.
    """
    kind: CaptureKind
    target_names: frozenset[str]  # Rule names to search for (expanded for unions)
    is_optional: bool = False     # Whether absent value should be None vs []
    is_list: bool = False         # Whether result should be a list
    text_fallback: bool = False   # For mixed choices, fall back to text if no rules found


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
    descriptor: CaptureDescriptor | None = None  # Computed at build time

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
    from .dsl import _auto_register_unions
    _auto_register_unions()
    
    return [r for r in _registry_by_location.values() if r.source_file == source_file]


def get_all_rules(
    *, 
    all_files: bool = False, 
    source_file: str | None = None,
    source_files: set[str] | None = None,
) -> list[GrammarRule]:
    """
    Get all registered grammar rules.
    
    By default, returns only rules defined in the caller's file.
    Pass all_files=True to get rules from all files.
    Pass source_file to get rules from a specific file.
    Pass source_files to get rules from multiple specific files.
    """
    import inspect
    
    # Auto-register any RuleUnion objects from caller's scope
    from .dsl import _auto_register_unions
    _auto_register_unions()
    
    if all_files:
        return list(_registry_by_location.values())
    
    if source_files is not None:
        return [r for r in _registry_by_location.values() if r.source_file in source_files]
    
    if source_file is not None:
        return [r for r in _registry_by_location.values() if r.source_file == source_file]
    
    # Get caller's filename
    frame = inspect.currentframe()
    try:
        caller = frame.f_back
        # Walk up past any wrapper frames in grammar/dsl
        while caller:
            filename = caller.f_code.co_filename
            if 'grammar.py' not in filename and 'dsl.py' not in filename:
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


# --- Capture Descriptor Computation ---

def _is_simple_element(elem: GrammarElement) -> bool:
    """Check if an element is simple (char class or literal) - captures as text."""
    if isinstance(elem, (GrammarCharClass, GrammarLiteral)):
        return True
    if isinstance(elem, GrammarChoice):
        return all(_is_simple_element(a) for a in elem.alternatives)
    if isinstance(elem, GrammarSequence):
        return all(_is_simple_element(e) for e in elem.elements)
    return False


def _unwrap_optional(elem: GrammarElement) -> tuple[GrammarElement, bool]:
    """
    Unwrap optional pattern: GrammarChoice([inner, GrammarLiteral("")]).
    Returns (unwrapped_element, is_optional).
    """
    if isinstance(elem, GrammarChoice):
        non_empty = [a for a in elem.alternatives 
                     if not (isinstance(a, GrammarLiteral) and a.value == "")]
        if len(non_empty) == 1 and len(elem.alternatives) > 1:
            return non_empty[0], True
    return elem, False


def _get_ref_name(elem: GrammarElement) -> str | None:
    """Get the reference name from an element if it's a GrammarRef."""
    if isinstance(elem, GrammarRef):
        return elem.name
    return None


def _collect_rule_refs(elem: GrammarElement) -> set[str]:
    """Collect all rule reference names from an element (recursively)."""
    refs: set[str] = set()
    if isinstance(elem, GrammarRef):
        refs.add(elem.name)
    elif isinstance(elem, GrammarChoice):
        for alt in elem.alternatives:
            refs.update(_collect_rule_refs(alt))
    elif isinstance(elem, GrammarSequence):
        for e in elem.elements:
            refs.update(_collect_rule_refs(e))
    elif isinstance(elem, GrammarRepeat):
        refs.update(_collect_rule_refs(elem.element))
    elif isinstance(elem, GrammarCapture):
        refs.update(_collect_rule_refs(elem.rule))
    return refs


def _has_non_empty_terminals(elem: GrammarElement) -> bool:
    """Check if element contains non-empty terminals (char classes or non-empty literals)."""
    if isinstance(elem, GrammarCharClass):
        return True
    if isinstance(elem, GrammarLiteral):
        return elem.value != ""
    if isinstance(elem, GrammarChoice):
        return any(_has_non_empty_terminals(a) for a in elem.alternatives)
    if isinstance(elem, GrammarSequence):
        return any(_has_non_empty_terminals(e) for e in elem.elements)
    return False


def _compute_repeat_descriptor(
    repeat_elem: GrammarElement,
    is_outer_optional: bool,
    rule_unions: dict[str, list[str]] | None = None
) -> CaptureDescriptor:
    """Compute descriptor for a repeat element."""
    rule_unions = rule_unions or {}
    
    ref_name = _get_ref_name(repeat_elem)
    if ref_name:
        # repeat[Rule] -> RULE_LIST
        target_names = {ref_name}
        if ref_name in rule_unions:
            target_names.update(rule_unions[ref_name])
        return CaptureDescriptor(
            kind=CaptureKind.RULE_LIST,
            target_names=frozenset(target_names),
            is_optional=is_outer_optional,
            is_list=True,
            text_fallback=False
        )
    
    if isinstance(repeat_elem, GrammarChoice):
        # repeat[optional[Rule]] or repeat[char | Rule]
        rule_refs = _collect_rule_refs(repeat_elem)
        has_terminals = _has_non_empty_terminals(repeat_elem)
        
        # Expand union names
        expanded_names: set[str] = set()
        for name in rule_refs:
            expanded_names.add(name)
            if name in rule_unions:
                expanded_names.update(rule_unions[name])
        
        if has_terminals and rule_refs:
            # Mixed: repeat[char | Escape] -> prefer text capture
            return CaptureDescriptor(
                kind=CaptureKind.TEXT,
                target_names=frozenset(expanded_names),
                is_optional=is_outer_optional,
                is_list=True,
                text_fallback=True
            )
        elif rule_refs:
            # Pure rule choice: repeat[optional[Field]] -> RULE_LIST
            return CaptureDescriptor(
                kind=CaptureKind.RULE_LIST,
                target_names=frozenset(expanded_names),
                is_optional=is_outer_optional,
                is_list=True,
                text_fallback=False
            )
    
    # repeat[char[...]] or other terminals -> TEXT
    return CaptureDescriptor(
        kind=CaptureKind.TEXT,
        target_names=frozenset(),
        is_optional=is_outer_optional,
        is_list=True,
        text_fallback=False
    )


def _compute_choice_descriptor(
    choice: GrammarChoice,
    is_optional: bool,
    rule_unions: dict[str, list[str]] | None = None
) -> CaptureDescriptor:
    """Compute descriptor for a choice element (not wrapped in repeat)."""
    rule_unions = rule_unions or {}
    
    rule_refs = _collect_rule_refs(choice)
    has_terminals = _has_non_empty_terminals(choice)
    
    # Expand union names
    expanded_names: set[str] = set()
    for name in rule_refs:
        expanded_names.add(name)
        if name in rule_unions:
            expanded_names.update(rule_unions[name])
    
    if rule_refs and has_terminals:
        # Mixed choice: either[Rule, "literal"] -> MIXED
        return CaptureDescriptor(
            kind=CaptureKind.MIXED,
            target_names=frozenset(expanded_names),
            is_optional=is_optional,
            is_list=False,
            text_fallback=True
        )
    elif rule_refs:
        # Pure rule choice: either[A, B, C]
        kind = CaptureKind.OPTIONAL_RULE if is_optional else CaptureKind.RULE
        return CaptureDescriptor(
            kind=kind,
            target_names=frozenset(expanded_names),
            is_optional=is_optional,
            is_list=False,
            text_fallback=False
        )
    
    # Pure terminal choice
    kind = CaptureKind.OPTIONAL_TEXT if is_optional else CaptureKind.TEXT
    return CaptureDescriptor(
        kind=kind,
        target_names=frozenset(),
        is_optional=is_optional,
        is_list=False,
        text_fallback=False
    )


def compute_capture_descriptor(
    inner: GrammarElement,
    rule_unions: dict[str, list[str]] | None = None
) -> CaptureDescriptor:
    """
    Analyze a capture's inner element and return extraction descriptor.
    
    Args:
        inner: The grammar element being captured
        rule_unions: Dict mapping union names to their alternative names
    
    Returns:
        CaptureDescriptor describing how to extract this capture
    """
    rule_unions = rule_unions or {}
    
    # Unwrap optional pattern
    inner_unwrapped, is_optional = _unwrap_optional(inner)
    
    # Simple rule reference
    ref_name = _get_ref_name(inner_unwrapped)
    if ref_name:
        target_names = {ref_name}
        if ref_name in rule_unions:
            target_names.update(rule_unions[ref_name])
        kind = CaptureKind.OPTIONAL_RULE if is_optional else CaptureKind.RULE
        return CaptureDescriptor(
            kind=kind,
            target_names=frozenset(target_names),
            is_optional=is_optional,
            is_list=False,
            text_fallback=False
        )
    
    # Repeat
    if isinstance(inner_unwrapped, GrammarRepeat):
        return _compute_repeat_descriptor(inner_unwrapped.element, is_optional, rule_unions)
    
    # Choice (not wrapped in repeat)
    if isinstance(inner_unwrapped, GrammarChoice):
        return _compute_choice_descriptor(inner_unwrapped, is_optional, rule_unions)
    
    # Terminal (char class, literal, sequence of terminals)
    if _is_simple_element(inner_unwrapped):
        kind = CaptureKind.OPTIONAL_TEXT if is_optional else CaptureKind.TEXT
        return CaptureDescriptor(
            kind=kind,
            target_names=frozenset(),
            is_optional=is_optional,
            is_list=False,
            text_fallback=False
        )
    
    # Sequence or unknown - treat as text
    kind = CaptureKind.OPTIONAL_TEXT if is_optional else CaptureKind.TEXT
    return CaptureDescriptor(
        kind=kind,
        target_names=frozenset(),
        is_optional=is_optional,
        is_list=False,
        text_fallback=False
    )


def _build_grammar(
    name: str,
    sequence: list[tuple],
    source_file: str,
    source_line: int,
    rule_unions: dict[str, list[str]] | None = None,
) -> GrammarRule:
    """
    Build a GrammarRule from the collected sequence of expressions and declarations.
    
    sequence is a list of tuples like:
        ("expr", "literal string")
        ("decl", "field_name", "annotation_text")
    
    rule_unions: Optional dict mapping union names to their alternative names,
                 used for computing capture descriptors.
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
                # Compute capture descriptor
                descriptor = compute_capture_descriptor(inner, rule_unions)
                elements.append(GrammarCapture(field_name, inner, descriptor))
            else:
                elements.append(inner)
    
    return GrammarRule(
        name=name,
        source_file=source_file,
        source_line=source_line,
        body=GrammarSequence(elements),
    )
