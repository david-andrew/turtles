"""
GLL (Generalized LL) Parser Implementation

A GLL parser that handles all context-free grammars including left-recursive
and ambiguous grammars. Uses a graph-structured stack (GSS) and shared packed
parse forest (SPPF) for efficient parsing.

Supports disambiguation via priority and associativity rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal
from pathlib import Path

from ..grammar import (
    GrammarElement,
    GrammarLiteral,
    GrammarCharClass,
    GrammarRef,
    GrammarCapture,
    GrammarRepeat,
    GrammarChoice,
    GrammarSequence,
    GrammarRule,
    lookup_by_name,
)


# =============================================================================
# Core Data Structures
# =============================================================================

@dataclass
class GrammarSlot:
    """
    A position within a grammar rule, used as GLL labels.
    Represents the state "we are at position `pos` within rule `rule_name`".
    """
    rule_name: str
    element: GrammarElement
    pos: int  # position within a sequence (0 = before first element)
    total: int  # total elements in sequence
    
    def __repr__(self) -> str:
        return f"Slot({self.rule_name}:{self.pos}/{self.total})"
    
    def __hash__(self) -> int:
        return hash((self.rule_name, self.pos, self.total))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GrammarSlot):
            return False
        return (self.rule_name == other.rule_name and 
                self.pos == other.pos and 
                self.total == other.total)


@dataclass
class GSSNode:
    """
    Graph-Structured Stack node.
    Represents a return point (slot, input position) in the parse.
    """
    slot: GrammarSlot | None  # None for the bottom of stack
    pos: int
    
    def __repr__(self) -> str:
        if self.slot is None:
            return f"GSS(⊥, {self.pos})"
        return f"GSS({self.slot}, {self.pos})"
    
    def __hash__(self) -> int:
        slot_hash = hash(self.slot) if self.slot else 0
        return hash((slot_hash, self.pos))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GSSNode):
            return False
        return self.slot == other.slot and self.pos == other.pos


@dataclass
class GSSEdge:
    """Edge in the GSS, connecting nodes with an SPPF node for the parsed content."""
    target: GSSNode
    sppf: SPPFNode | None


@dataclass
class SPPFNode:
    """
    Shared Packed Parse Forest node.
    Represents a parsed span of input, potentially with multiple derivations (ambiguity).
    """
    label: str  # rule name or terminal description
    start: int
    end: int
    # For ambiguous parses, we have multiple packed nodes (families)
    families: list[PackedNode] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"SPPF({self.label}, {self.start}:{self.end}, {len(self.families)} families)"
    
    def __hash__(self) -> int:
        return hash((self.label, self.start, self.end))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SPPFNode):
            return False
        return self.label == other.label and self.start == other.start and self.end == other.end


@dataclass
class PackedNode:
    """
    A single derivation within an SPPF node.
    Contains the slot that produced this derivation and child nodes.
    """
    slot: GrammarSlot | str  # slot or terminal label
    pivot: int  # split point for binary nodes
    children: list[SPPFNode] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"Packed({self.slot}, pivot={self.pivot}, {len(self.children)} children)"


@dataclass
class Descriptor:
    """
    A work item for the GLL parser.
    (label, GSS node, input position, SPPF node for accumulated parse)
    """
    slot: GrammarSlot
    gss: GSSNode
    pos: int
    sppf: SPPFNode | None
    
    def __repr__(self) -> str:
        return f"Desc({self.slot}, gss={self.gss.pos}, pos={self.pos})"
    
    def __hash__(self) -> int:
        return hash((hash(self.slot), hash(self.gss), self.pos, id(self.sppf)))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Descriptor):
            return False
        return (self.slot == other.slot and 
                self.gss == other.gss and 
                self.pos == other.pos and
                self.sppf is other.sppf)


# =============================================================================
# Disambiguation Rules
# =============================================================================

Associativity = Literal['left', 'right', 'none']


@dataclass
class DisambiguationRules:
    """Container for disambiguation rules: priority and associativity."""
    # Priority: list of rule names from highest to lowest precedence
    priority: list[str] = field(default_factory=list)
    # Associativity per rule name
    associativity: dict[str, Associativity] = field(default_factory=dict)
    
    def get_priority(self, rule_name: str) -> int:
        """
        Return priority score for disambiguation.
        Higher precedence operators should be NESTED (not at top level).
        So we invert: lower score = preferred at current level = LOWER precedence.
        """
        try:
            idx = self.priority.index(rule_name)
            # Invert: higher index in priority list = lower precedence = lower score = preferred at top
            return -idx
        except ValueError:
            # Unknown rules get very negative score (preferred at top over known operators)
            return -(len(self.priority) + 1000)
    
    def get_associativity(self, rule_name: str) -> Associativity:
        """Return associativity for a rule. Default is 'none'."""
        return self.associativity.get(rule_name, 'none')


# =============================================================================
# Character Class Matching
# =============================================================================

def _parse_escape_sequence(pattern: str, i: int) -> tuple[str, int]:
    """
    Parse an escape sequence starting at position i (after the backslash).
    Returns (character, new_position).
    """
    if i >= len(pattern):
        return '\\', i
    
    ch = pattern[i]
    
    # Simple escape sequences
    simple_escapes = {
        'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
        '\\': '\\', '-': '-', ']': ']', '^': '^',
    }
    if ch in simple_escapes:
        return simple_escapes[ch], i + 1
    
    # \xHH - 2 hex digits
    if ch == 'x' and i + 2 < len(pattern):
        try:
            code = int(pattern[i + 1:i + 3], 16)
            return chr(code), i + 3
        except ValueError:
            pass
    
    # \uHHHH - 4 hex digits
    if ch == 'u' and i + 4 < len(pattern):
        try:
            code = int(pattern[i + 1:i + 5], 16)
            return chr(code), i + 5
        except ValueError:
            pass
    
    # \UHHHHHHHH - 8 hex digits
    if ch == 'U' and i + 8 < len(pattern):
        try:
            code = int(pattern[i + 1:i + 9], 16)
            return chr(code), i + 9
        except ValueError:
            pass
    
    # Unknown escape - return the character literally
    return ch, i + 1


def compile_char_class(pattern: str) -> Callable[[str], bool]:
    r"""
    Compile a character class pattern like 'a-zA-Z0-9_' into a matcher function.
    
    Supports:
    - Ranges: a-z, 0-9, \x20-\x7E
    - Individual characters: abc
    - Escape sequences: \\, \-, \n, \r, \t, \xHH, \uHHHH, \UHHHHHHHH
    - Literal dash at start/end: -a-z or a-z-
    
    Uses range-based matching (not character enumeration) for efficiency with
    large Unicode ranges.
    """
    ranges: list[tuple[int, int]] = []  # (start_ord, end_ord) inclusive
    i = 0
    n = len(pattern)
    
    def parse_char(pos: int) -> tuple[str, int]:
        """Parse a single character or escape sequence at position pos."""
        if pos >= n:
            return '', pos
        if pattern[pos] == '\\':
            return _parse_escape_sequence(pattern, pos + 1)
        return pattern[pos], pos + 1
    
    while i < n:
        # Parse the first character
        ch, next_i = parse_char(i)
        if not ch:
            break
        
        # Check if this could be the start of a range
        # A dash is a range operator if:
        # - It's not at the start (i > 0)
        # - It's not at the end (there's a character after)
        # - It's not escaped (handled by parse_char)
        if next_i < n and pattern[next_i] == '-' and next_i + 1 < n:
            # Peek at what comes after the dash
            end_ch, end_next_i = parse_char(next_i + 1)
            if end_ch:
                # This is a range: ch-end_ch
                ranges.append((ord(ch), ord(end_ch)))
                i = end_next_i
                continue
        
        # Single character - add as a range of length 1
        ranges.append((ord(ch), ord(ch)))
        i = next_i
    
    # Optimize: merge adjacent/overlapping ranges
    if ranges:
        ranges.sort()
        merged: list[tuple[int, int]] = [ranges[0]]
        for start, end in ranges[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end + 1:
                # Overlapping or adjacent - merge
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))
        ranges = merged
    
    # Create matcher function
    def matcher(c: str) -> bool:
        if not c:
            return False
        code = ord(c)
        for start, end in ranges:
            if start <= code <= end:
                return True
        return False
    
    return matcher


# =============================================================================
# Grammar Compilation
# =============================================================================

@dataclass
class CompiledGrammar:
    """A grammar compiled for GLL parsing."""
    rules: dict[str, GrammarRule]
    slots: dict[str, list[GrammarSlot]]  # rule_name -> slots for that rule
    char_matchers: dict[str, Callable[[str], bool]]  # cached char class matchers
    body_to_rule: dict[str, str] = field(default_factory=dict)  # sequence description -> rule name
    
    @classmethod
    def from_rules(cls, rules: list[GrammarRule]) -> CompiledGrammar:
        """Compile a list of grammar rules."""
        rules_dict = {r.name: r for r in rules}
        slots: dict[str, list[GrammarSlot]] = {}
        char_matchers: dict[str, Callable[[str], bool]] = {}
        body_to_rule: dict[str, str] = {}
        
        for rule in rules:
            rule_slots = cls._compile_element(rule.name, rule.body, char_matchers)
            slots[rule.name] = rule_slots
            # Map body description to rule name for disambiguation
            body_desc = cls._element_description(rule.body)
            body_to_rule[body_desc] = rule.name
        
        return cls(rules_dict, slots, char_matchers, body_to_rule)
    
    @classmethod
    def _element_description(cls, elem: GrammarElement) -> str:
        """Generate a description string matching SPPF node labels."""
        if isinstance(elem, GrammarLiteral):
            return f'"{elem.value}"'
        elif isinstance(elem, GrammarCharClass):
            return f"[{elem.pattern}]"
        elif isinstance(elem, GrammarRef):
            return elem.name
        elif isinstance(elem, GrammarSequence):
            return "+".join(cls._element_description(e) for e in elem.elements)
        elif isinstance(elem, GrammarCapture):
            # For SPPF matching, use the inner element's description, not the capture name
            return cls._element_description(elem.rule)
        elif isinstance(elem, GrammarChoice):
            # Choices don't appear as combined labels in the same way
            return "|".join(cls._element_description(a) for a in elem.alternatives)
        elif isinstance(elem, GrammarRepeat):
            return cls._element_description(elem.element) + "*"
        else:
            return str(elem)
    
    @classmethod
    def _compile_element(
        cls,
        rule_name: str,
        element: GrammarElement,
        char_matchers: dict[str, Callable[[str], bool]],
    ) -> list[GrammarSlot]:
        """Compile a grammar element into slots."""
        if isinstance(element, GrammarSequence):
            elements = element.elements
        else:
            elements = [element]
        
        slots = []
        for i, elem in enumerate(elements):
            slot = GrammarSlot(rule_name, elem, i, len(elements))
            slots.append(slot)
            
            # Pre-compile character class matchers (recursively for nested elements)
            cls._compile_char_matchers(elem, char_matchers)
        
        # Add final slot (after last element)
        final_slot = GrammarSlot(rule_name, GrammarLiteral(""), len(elements), len(elements))
        slots.append(final_slot)
        
        return slots
    
    @classmethod
    def _compile_char_matchers(
        cls,
        elem: GrammarElement,
        char_matchers: dict[str, Callable[[str], bool]],
    ) -> None:
        """Recursively compile character class matchers for an element."""
        if isinstance(elem, GrammarCharClass):
            if elem.pattern not in char_matchers:
                char_matchers[elem.pattern] = compile_char_class(elem.pattern)
        elif isinstance(elem, GrammarCapture):
            cls._compile_char_matchers(elem.rule, char_matchers)
        elif isinstance(elem, GrammarRepeat):
            cls._compile_char_matchers(elem.element, char_matchers)
        elif isinstance(elem, GrammarChoice):
            for alt in elem.alternatives:
                cls._compile_char_matchers(alt, char_matchers)
        elif isinstance(elem, GrammarSequence):
            for sub in elem.elements:
                cls._compile_char_matchers(sub, char_matchers)


# =============================================================================
# GLL Parser
# =============================================================================

class GLLParser:
    """
    GLL Parser implementation.
    
    Parses input according to grammar rules, producing an SPPF that can
    represent ambiguous parses. Disambiguation is applied during result extraction.
    """
    
    def __init__(self, grammar: CompiledGrammar, disambig: DisambiguationRules | None = None):
        self.grammar = grammar
        self.disambig = disambig or DisambiguationRules()
        
        # Parser state (reset for each parse)
        self.input: str = ""
        self.input_len: int = 0
        
        # Worklist of descriptors to process
        self.R: list[Descriptor] = []
        # Set of descriptors already added (to avoid duplicates)
        self.U: set[tuple[str, int, int, int]] = set()  # (slot_key, gss_pos, pos)
        # Pop set: maps GSS nodes to their return SPPF nodes
        self.P: dict[GSSNode, list[SPPFNode]] = {}
        
        # GSS structure
        self.gss_nodes: dict[tuple[str | None, int], GSSNode] = {}
        self.gss_edges: dict[GSSNode, list[GSSEdge]] = {}
        
        # SPPF nodes (for sharing)
        self.sppf_nodes: dict[tuple[str, int, int], SPPFNode] = {}
    
    def _reset(self, input_str: str) -> None:
        """Reset parser state for a new parse."""
        self.input = input_str
        self.input_len = len(input_str)
        self.R.clear()
        self.U.clear()
        self.P.clear()
        self.gss_nodes.clear()
        self.gss_edges.clear()
        self.sppf_nodes.clear()
        self._pending_continuations: dict[tuple, list] = {}
        # Repeat continuation state: slot_name -> (element, separator, at_least, at_most, 
        #                                           items_parsed, capture_name, original_desc)
        self._repeat_state: dict[str, tuple] = {}
        self._repeat_counter = 0
    
    def _slot_key(self, slot: GrammarSlot) -> str:
        """Create a hashable key for a slot."""
        return f"{slot.rule_name}:{slot.pos}"
    
    def _hash_elements(self, elements: list[GrammarElement]) -> str:
        """Create a deterministic hash for a list of grammar elements."""
        parts = []
        for elem in elements:
            parts.append(self._hash_element(elem))
        return "_".join(parts)
    
    def _hash_element(self, elem: GrammarElement) -> str:
        """Create a deterministic hash for a grammar element."""
        if isinstance(elem, GrammarLiteral):
            return f"L{hash(elem.value) & 0xFFFF:04x}"
        elif isinstance(elem, GrammarCharClass):
            return f"C{hash(elem.pattern) & 0xFFFF:04x}"
        elif isinstance(elem, GrammarRef):
            return f"R{elem.name}"
        elif isinstance(elem, GrammarCapture):
            return f"Cap{elem.name}_{self._hash_element(elem.rule)}"
        elif isinstance(elem, GrammarRepeat):
            return f"Rep{self._hash_element(elem.element)}"
        elif isinstance(elem, GrammarChoice):
            alts = "_".join(self._hash_element(a) for a in elem.alternatives)
            return f"Ch{alts}"
        elif isinstance(elem, GrammarSequence):
            elems = "_".join(self._hash_element(e) for e in elem.elements)
            return f"Seq{elems}"
        return "X"
    
    def _add(self, desc: Descriptor) -> None:
        """Add a descriptor to the worklist if not already processed."""
        # U set key: (slot_key, gss_key, input_position, sppf_key)
        # Include SPPF to ensure different parse paths are all explored
        gss_key = (self._slot_key(desc.gss.slot) if desc.gss.slot else None, desc.gss.pos)
        sppf_key = (desc.sppf.label, desc.sppf.start, desc.sppf.end) if desc.sppf else None
        u_key = (self._slot_key(desc.slot), gss_key, desc.pos, sppf_key)
        if u_key not in self.U:
            self.U.add(u_key)
            self.R.append(desc)
    
    def _get_or_create_gss(self, slot: GrammarSlot | None, pos: int) -> GSSNode:
        """Get or create a GSS node."""
        slot_repr = self._slot_key(slot) if slot else None
        key = (slot_repr, pos)
        if key not in self.gss_nodes:
            self.gss_nodes[key] = GSSNode(slot, pos)
        return self.gss_nodes[key]
    
    def _get_or_create_sppf(self, label: str, start: int, end: int) -> SPPFNode:
        """Get or create an SPPF node for sharing."""
        key = (label, start, end)
        if key not in self.sppf_nodes:
            self.sppf_nodes[key] = SPPFNode(label, start, end)
        return self.sppf_nodes[key]
    
    def _create(self, slot: GrammarSlot, gss: GSSNode, pos: int, sppf: SPPFNode | None) -> GSSNode:
        """
        Create a new GSS node or return existing one.
        Add edge from new/existing node to current node.
        Handle any pending pops.
        
        The slot is the continuation point (where to resume when the called rule returns).
        """
        new_gss = self._get_or_create_gss(slot, pos)
        
        # Add edge
        if new_gss not in self.gss_edges:
            self.gss_edges[new_gss] = []
        
        # Check if this edge already exists
        edge_exists = any(e.target == gss for e in self.gss_edges[new_gss])
        if not edge_exists:
            self.gss_edges[new_gss] = self.gss_edges.get(new_gss, []) + [GSSEdge(gss, sppf)]
            
            # Process any pending pops for this GSS node
            if new_gss in self.P:
                for pop_sppf in self.P[new_gss]:
                    # Combine sppf with pop_sppf and continue at slot (the continuation)
                    combined = self._combine_sppf(sppf, pop_sppf)
                    self._add(Descriptor(slot, gss, pop_sppf.end, combined))
        
        return new_gss
    
    def _pop(self, gss: GSSNode, sppf: SPPFNode) -> None:
        """
        Pop from a GSS node, propagating results to all callers.
        The GSS node's slot is the continuation point (where to resume after the call).
        """
        if gss.slot is None:
            # Bottom of stack - we're done with this parse path
            return
        
        # Record the pop
        if gss not in self.P:
            self.P[gss] = []
        self.P[gss].append(sppf)
        
        # Propagate to all edges - continue at the stored slot (the continuation point)
        for edge in self.gss_edges.get(gss, []):
            combined = self._combine_sppf(edge.sppf, sppf)
            # Continue at gss.slot (the continuation), not the next slot after it
            self._add(Descriptor(gss.slot, edge.target, sppf.end, combined))
    
    def _next_slot(self, slot: GrammarSlot) -> GrammarSlot | None:
        """Get the next slot in the same rule, or None if at end."""
        if slot.pos >= slot.total:
            return None
        slots = self.grammar.slots.get(slot.rule_name, [])
        for s in slots:
            if s.pos == slot.pos + 1:
                return s
        return None
    
    def _combine_sppf(self, left: SPPFNode | None, right: SPPFNode | None) -> SPPFNode | None:
        """Combine two SPPF nodes into one."""
        if left is None:
            return right
        if right is None:
            return left
        
        # Create a combined node spanning both
        label = f"{left.label}+{right.label}"
        combined = self._get_or_create_sppf(label, left.start, right.end)
        
        # Add a packed node with both children
        packed = PackedNode(label, left.end, [left, right])
        if packed not in combined.families:
            combined.families.append(packed)
        
        return combined
    
    def _match_terminal(self, element: GrammarElement, pos: int) -> tuple[int, SPPFNode] | None:
        """
        Try to match a terminal at the given position.
        Returns (new_pos, sppf_node) or None if no match.
        """
        if isinstance(element, GrammarLiteral):
            if not element.value:
                # Empty/epsilon - always matches, consumes nothing
                return (pos, self._get_or_create_sppf("ε", pos, pos))
            
            end = pos + len(element.value)
            if end <= self.input_len and self.input[pos:end] == element.value:
                sppf = self._get_or_create_sppf(f'"{element.value}"', pos, end)
                sppf.families = [PackedNode(f'"{element.value}"', pos, [])]
                return (end, sppf)
            return None
        
        elif isinstance(element, GrammarCharClass):
            if pos >= self.input_len:
                return None
            char = self.input[pos]
            matcher = self.grammar.char_matchers.get(element.pattern)
            if matcher and matcher(char):
                sppf = self._get_or_create_sppf(f"[{element.pattern}]", pos, pos + 1)
                sppf.families = [PackedNode(char, pos, [])]
                return (pos + 1, sppf)
            return None
        
        return None
    
    def _process_slot(self, desc: Descriptor) -> None:
        """Process a single descriptor/slot."""
        slot = desc.slot
        element = slot.element
        pos = desc.pos
        gss = desc.gss
        current_sppf = desc.sppf
        
        # Handle synthetic final slots (complete parent rule and pop)
        if slot.rule_name.startswith("_final_"):
            # Extract parent rule name: _final_RuleName_pos
            parts = slot.rule_name.split("_")
            if len(parts) >= 3:
                parent_rule = parts[2]
                start_pos = current_sppf.start if current_sppf else pos
                rule_sppf = self._get_or_create_sppf(parent_rule, start_pos, pos)
                if current_sppf:
                    packed = PackedNode(parent_rule, start_pos, [current_sppf])
                else:
                    packed = PackedNode(parent_rule, start_pos, [])
                if packed not in rule_sppf.families:
                    rule_sppf.families.append(packed)
                self._pop(gss, rule_sppf)
            return
        
        # Handle synthetic continuation slots
        if slot.rule_name.startswith("_cont_"):
            # This is a continuation - process the remaining sequence elements
            # After completion, we need to continue at the parent rule's next slot
            if isinstance(element, GrammarSequence):
                # Extract parent rule name from continuation name: _cont_RuleName_pos_id
                parts = slot.rule_name.split("_")
                if len(parts) >= 3:
                    parent_rule = parts[2]
                    # Find the parent rule's final slot and use a modified descriptor
                    # that will complete the parent rule when the sequence finishes
                    self._process_continuation_sequence(
                        list(element.elements), desc, parent_rule
                    )
            return
        
        # Handle repeat-separator continuation (separator was parsed, now parse element)
        # Check this BEFORE _repeat_ since _repeat_sep_ starts with _repeat_
        if slot.rule_name.startswith("_repeat_sep_"):
            state = self._repeat_state.get(slot.rule_name)
            if state:
                rep_element, separator, at_least, at_most, items_parsed, capture_name, orig_desc, accumulated_sppf = state
                # Separator was parsed successfully, now parse the element
                # Use the stored accumulated SPPF, not current_sppf (which includes separator)
                self._parse_repeat_element(
                    rep_element, separator, at_least, at_most,
                    items_parsed, accumulated_sppf, capture_name, orig_desc, pos
                )
            return
        
        # Handle repeat continuation slots (element was parsed)
        if slot.rule_name.startswith("_repeat_"):
            state = self._repeat_state.get(slot.rule_name)
            if state:
                rep_element, separator, at_least, at_most, items_parsed, capture_name, orig_desc, accumulated_sppf = state
                # The current_sppf is the result of parsing one item
                # Combine with accumulated SPPF
                new_accumulated = self._combine_sppf(accumulated_sppf, current_sppf)
                items_parsed += 1
                
                # If we have enough items, we can stop here (emit a valid parse path)
                if items_parsed >= at_least:
                    if capture_name:
                        final_sppf = self._get_or_create_sppf(f":{capture_name}",
                            new_accumulated.start if new_accumulated else pos, pos)
                        if new_accumulated:
                            final_sppf.families = new_accumulated.families[:]
                    else:
                        final_sppf = new_accumulated
                    combined = self._combine_sppf(orig_desc.sppf, final_sppf)
                    next_slot = self._next_slot(orig_desc.slot)
                    if next_slot:
                        self._add(Descriptor(next_slot, orig_desc.gss, pos, combined))
                
                # Try to parse more items if we haven't hit maximum
                if at_most is None or items_parsed < at_most:
                    if separator:
                        if self._is_simple_separator(separator):
                            # Simple separator - match synchronously
                            sep_pos = self._match_separator(separator, pos)
                            if sep_pos is not None:
                                self._parse_repeat_element(
                                    rep_element, separator, at_least, at_most,
                                    items_parsed, new_accumulated, capture_name, orig_desc, sep_pos
                                )
                        elif isinstance(separator, GrammarRef):
                            # Complex separator - parse asynchronously
                            sep_rule = self.grammar.rules.get(separator.name)
                            if sep_rule:
                                called_slots = self.grammar.slots.get(separator.name, [])
                                if called_slots:
                                    first_slot = called_slots[0]
                                    self._repeat_counter += 1
                                    cont_name = f"_repeat_sep_{self._repeat_counter}"
                                    cont_slot = GrammarSlot(cont_name, separator, 0, 1)
                                    # Store state for after separator is parsed, including accumulated SPPF
                                    self._repeat_state[cont_name] = (
                                        rep_element, separator, at_least, at_most,
                                        items_parsed, capture_name, orig_desc, new_accumulated  # Include accumulated SPPF
                                    )
                                    new_gss = self._create(cont_slot, orig_desc.gss, pos, None)  # Don't pass SPPF through edge
                                    self._add(Descriptor(first_slot, new_gss, pos, None))
                    else:
                        # No separator needed
                        self._parse_repeat_element(
                            rep_element, separator, at_least, at_most,
                            items_parsed, new_accumulated, capture_name, orig_desc, pos
                        )
            return
        
        # If we're at the end of a rule (past last element)
        if slot.pos >= slot.total:
            # Create result SPPF for this rule
            start_pos = current_sppf.start if current_sppf else pos
            rule_sppf = self._get_or_create_sppf(slot.rule_name, start_pos, pos)
            if current_sppf:
                packed = PackedNode(slot, start_pos, [current_sppf])
            else:
                packed = PackedNode(slot, start_pos, [])
            if packed not in rule_sppf.families:
                rule_sppf.families.append(packed)
            
            self._pop(gss, rule_sppf)
            return
        
        # Handle different element types
        if isinstance(element, (GrammarLiteral, GrammarCharClass)):
            result = self._match_terminal(element, pos)
            if result:
                new_pos, term_sppf = result
                combined = self._combine_sppf(current_sppf, term_sppf)
                next_slot = self._next_slot(slot)
                if next_slot:
                    self._add(Descriptor(next_slot, gss, new_pos, combined))
        
        elif isinstance(element, GrammarRef):
            # Call another rule
            rule = self.grammar.rules.get(element.name)
            if rule:
                # Get first slot of the called rule
                called_slots = self.grammar.slots.get(element.name, [])
                if called_slots:
                    first_slot = called_slots[0]
                    # Create return point
                    next_slot = self._next_slot(slot)
                    if next_slot:
                        new_gss = self._create(next_slot, gss, pos, current_sppf)
                        self._add(Descriptor(first_slot, new_gss, pos, None))
        
        elif isinstance(element, GrammarCapture):
            # Capture wraps an inner element - process the inner element
            inner = element.rule
            if isinstance(inner, (GrammarLiteral, GrammarCharClass)):
                result = self._match_terminal(inner, pos)
                if result:
                    new_pos, term_sppf = result
                    # Tag the SPPF with the capture name
                    capture_sppf = self._get_or_create_sppf(f":{element.name}", term_sppf.start, term_sppf.end)
                    capture_sppf.families = term_sppf.families[:]
                    combined = self._combine_sppf(current_sppf, capture_sppf)
                    next_slot = self._next_slot(slot)
                    if next_slot:
                        self._add(Descriptor(next_slot, gss, new_pos, combined))
            elif isinstance(inner, GrammarRef):
                # Captured reference - handle like regular ref but tag result
                rule = self.grammar.rules.get(inner.name)
                if rule:
                    called_slots = self.grammar.slots.get(inner.name, [])
                    if called_slots:
                        first_slot = called_slots[0]
                        next_slot = self._next_slot(slot)
                        if next_slot:
                            # Create a wrapper slot that will tag the result
                            new_gss = self._create(next_slot, gss, pos, current_sppf)
                            self._add(Descriptor(first_slot, new_gss, pos, None))
            elif isinstance(inner, GrammarChoice):
                self._process_choice(inner, desc, element.name)
            elif isinstance(inner, GrammarRepeat):
                self._process_repeat(inner, desc, element.name)
            elif isinstance(inner, GrammarSequence):
                self._process_sequence(inner, desc, element.name)
        
        elif isinstance(element, GrammarChoice):
            self._process_choice(element, desc)
        
        elif isinstance(element, GrammarRepeat):
            self._process_repeat(element, desc)
        
        elif isinstance(element, GrammarSequence):
            self._process_sequence(element, desc)
    
    def _process_choice(self, choice: GrammarChoice, desc: Descriptor, capture_name: str | None = None) -> None:
        """Process a choice element by trying all alternatives."""
        for i, alt in enumerate(choice.alternatives):
            # For each alternative, try to match it
            if isinstance(alt, (GrammarLiteral, GrammarCharClass)):
                result = self._match_terminal(alt, desc.pos)
                if result:
                    new_pos, term_sppf = result
                    if capture_name:
                        capture_sppf = self._get_or_create_sppf(f":{capture_name}", term_sppf.start, term_sppf.end)
                        capture_sppf.families = term_sppf.families[:]
                        term_sppf = capture_sppf
                    combined = self._combine_sppf(desc.sppf, term_sppf)
                    next_slot = self._next_slot(desc.slot)
                    if next_slot:
                        self._add(Descriptor(next_slot, desc.gss, new_pos, combined))
            elif isinstance(alt, GrammarRef):
                rule = self.grammar.rules.get(alt.name)
                if rule:
                    called_slots = self.grammar.slots.get(alt.name, [])
                    if called_slots:
                        first_slot = called_slots[0]
                        next_slot = self._next_slot(desc.slot)
                        if next_slot:
                            new_gss = self._create(next_slot, desc.gss, desc.pos, desc.sppf)
                            self._add(Descriptor(first_slot, new_gss, desc.pos, None))
            elif isinstance(alt, GrammarSequence):
                # Inline sequence in choice
                self._process_sequence(alt, desc, capture_name)
    
    def _process_repeat(self, repeat: GrammarRepeat, desc: Descriptor, capture_name: str | None = None) -> None:
        """Process a repeat element."""
        # For repeat, we need to handle:
        # - at_least: minimum repetitions
        # - at_most: maximum repetitions (None = unbounded)
        # - separator: optional separator between items
        
        # Start a repeat parse
        self._parse_repeat_items(
            repeat.element,
            repeat.separator,
            repeat.at_least,
            repeat.at_most,
            desc,
            items_parsed=0,
            accumulated_sppf=None,
            capture_name=capture_name,
        )
    
    def _match_separator(self, separator: GrammarElement, pos: int) -> int | None:
        """
        Try to match a simple separator at the given position.
        Returns the new position after the separator, or None if no match.
        Only handles GrammarLiteral and GrammarCharClass. 
        For GrammarRef separators, returns None (requires async handling).
        """
        if isinstance(separator, GrammarLiteral):
            sep_end = pos + len(separator.value)
            if sep_end <= self.input_len and self.input[pos:sep_end] == separator.value:
                return sep_end
            return None
        elif isinstance(separator, GrammarCharClass):
            if pos >= self.input_len:
                return None
            char = self.input[pos]
            matcher = self.grammar.char_matchers.get(separator.pattern)
            if matcher and matcher(char):
                return pos + 1
            return None
        # GrammarRef and complex separators require async handling
        return None
    
    def _is_simple_separator(self, separator: GrammarElement) -> bool:
        """Check if separator can be matched synchronously."""
        return isinstance(separator, (GrammarLiteral, GrammarCharClass))
    
    def _parse_repeat_items(
        self,
        element: GrammarElement,
        separator: GrammarElement | None,
        at_least: int,
        at_most: int | None,
        desc: Descriptor,
        items_parsed: int,
        accumulated_sppf: SPPFNode | None,
        capture_name: str | None,
    ) -> None:
        """Parse repeated items."""
        pos = desc.pos
        
        # Check if we've reached maximum
        if at_most is not None and items_parsed >= at_most:
            # Must stop here
            if items_parsed >= at_least:
                if capture_name:
                    final_sppf = self._get_or_create_sppf(f":{capture_name}", 
                        accumulated_sppf.start if accumulated_sppf else pos, pos)
                    if accumulated_sppf:
                        final_sppf.families = accumulated_sppf.families[:]
                else:
                    final_sppf = accumulated_sppf
                combined = self._combine_sppf(desc.sppf, final_sppf)
                next_slot = self._next_slot(desc.slot)
                if next_slot:
                    self._add(Descriptor(next_slot, desc.gss, pos, combined))
            return
        
        # If we have enough items, we can stop here (but may also continue)
        if items_parsed >= at_least:
            if capture_name:
                final_sppf = self._get_or_create_sppf(f":{capture_name}",
                    accumulated_sppf.start if accumulated_sppf else pos, pos)
                if accumulated_sppf:
                    final_sppf.families = accumulated_sppf.families[:]
            else:
                final_sppf = accumulated_sppf
            combined = self._combine_sppf(desc.sppf, final_sppf)
            next_slot = self._next_slot(desc.slot)
            if next_slot:
                self._add(Descriptor(next_slot, desc.gss, pos, combined))
        
        # Try to parse one more item
        # If not first item and separator exists, match separator first
        if items_parsed > 0 and separator:
            if self._is_simple_separator(separator):
                sep_pos = self._match_separator(separator, pos)
                if sep_pos is not None:
                    pos = sep_pos
                else:
                    return  # Can't continue without separator
            elif isinstance(separator, GrammarRef):
                # Complex separator - parse asynchronously
                sep_rule = self.grammar.rules.get(separator.name)
                if sep_rule:
                    called_slots = self.grammar.slots.get(separator.name, [])
                    if called_slots:
                        first_slot = called_slots[0]
                        self._repeat_counter += 1
                        cont_name = f"_repeat_sep_{self._repeat_counter}"
                        cont_slot = GrammarSlot(cont_name, separator, 0, 1)
                        # Store state for after separator is parsed, including accumulated SPPF
                        self._repeat_state[cont_name] = (
                            element, separator, at_least, at_most,
                            items_parsed, capture_name, desc, accumulated_sppf  # Include accumulated SPPF
                        )
                        new_gss = self._create(cont_slot, desc.gss, pos, None)  # Don't pass SPPF through edge
                        self._add(Descriptor(first_slot, new_gss, pos, None))
                return  # Separator parsing is async, we'll continue when it returns
            else:
                return  # Unsupported separator type
        
        # Try to match the repeated element
        if isinstance(element, (GrammarLiteral, GrammarCharClass)):
            result = self._match_terminal(element, pos)
            if result:
                new_pos, item_sppf = result
                new_acc = self._combine_sppf(accumulated_sppf, item_sppf)
                # Continue parsing more items
                new_desc = Descriptor(desc.slot, desc.gss, new_pos, desc.sppf)
                self._parse_repeat_items(
                    element, separator, at_least, at_most, new_desc,
                    items_parsed + 1, new_acc, capture_name,
                )
        elif isinstance(element, GrammarRef):
            # Need to call the referenced rule and continue from result
            rule = self.grammar.rules.get(element.name)
            if rule:
                called_slots = self.grammar.slots.get(element.name, [])
                if called_slots:
                    first_slot = called_slots[0]
                    # Create a repeat continuation slot
                    self._repeat_counter += 1
                    cont_name = f"_repeat_{self._repeat_counter}"
                    cont_slot = GrammarSlot(cont_name, element, 0, 1)
                    # Store repeat state for when we return, including accumulated SPPF
                    self._repeat_state[cont_name] = (
                        element, separator, at_least, at_most,
                        items_parsed, capture_name, desc, accumulated_sppf
                    )
                    # Create GSS edge to continue at repeat continuation
                    new_gss = self._create(cont_slot, desc.gss, pos, desc.sppf)
                    self._add(Descriptor(first_slot, new_gss, pos, None))
        
        elif isinstance(element, GrammarChoice):
            # Handle choice within repeat - try each alternative
            self._parse_repeat_choice(
                element, separator, at_least, at_most, desc,
                items_parsed, accumulated_sppf, capture_name, pos
            )
    
    def _parse_repeat_element(
        self,
        element: GrammarElement,
        separator: GrammarElement | None,
        at_least: int,
        at_most: int | None,
        items_parsed: int,
        accumulated_sppf: SPPFNode | None,
        capture_name: str | None,
        orig_desc: Descriptor,
        pos: int,
    ) -> None:
        """Parse a single repeat element (separator already matched if needed)."""
        if isinstance(element, (GrammarLiteral, GrammarCharClass)):
            result = self._match_terminal(element, pos)
            if result:
                new_pos, item_sppf = result
                new_acc = self._combine_sppf(accumulated_sppf, item_sppf)
                # Continue parsing more items
                new_desc = Descriptor(orig_desc.slot, orig_desc.gss, new_pos, orig_desc.sppf)
                self._parse_repeat_items(
                    element, separator, at_least, at_most, new_desc,
                    items_parsed + 1, new_acc, capture_name,
                )
        elif isinstance(element, GrammarRef):
            rule = self.grammar.rules.get(element.name)
            if rule:
                called_slots = self.grammar.slots.get(element.name, [])
                if called_slots:
                    first_slot = called_slots[0]
                    self._repeat_counter += 1
                    cont_name = f"_repeat_{self._repeat_counter}"
                    cont_slot = GrammarSlot(cont_name, element, 0, 1)
                    self._repeat_state[cont_name] = (
                        element, separator, at_least, at_most,
                        items_parsed, capture_name, orig_desc, accumulated_sppf
                    )
                    new_gss = self._create(cont_slot, orig_desc.gss, pos, orig_desc.sppf)
                    self._add(Descriptor(first_slot, new_gss, pos, None))
        elif isinstance(element, GrammarChoice):
            self._parse_repeat_choice(
                element, separator, at_least, at_most, orig_desc,
                items_parsed, accumulated_sppf, capture_name, pos
            )
    
    def _parse_repeat_choice(
        self,
        choice: GrammarChoice,
        separator: GrammarElement | None,
        at_least: int,
        at_most: int | None,
        desc: Descriptor,
        items_parsed: int,
        accumulated_sppf: SPPFNode | None,
        capture_name: str | None,
        pos: int,
    ) -> None:
        """Parse a choice element within a repeat."""
        for alt in choice.alternatives:
            if isinstance(alt, (GrammarLiteral, GrammarCharClass)):
                result = self._match_terminal(alt, pos)
                if result:
                    new_pos, item_sppf = result
                    new_acc = self._combine_sppf(accumulated_sppf, item_sppf)
                    new_desc = Descriptor(desc.slot, desc.gss, new_pos, desc.sppf)
                    self._parse_repeat_items(
                        choice, separator, at_least, at_most, new_desc,
                        items_parsed + 1, new_acc, capture_name,
                    )
            elif isinstance(alt, GrammarRef):
                rule = self.grammar.rules.get(alt.name)
                if rule:
                    called_slots = self.grammar.slots.get(alt.name, [])
                    if called_slots:
                        first_slot = called_slots[0]
                        self._repeat_counter += 1
                        cont_name = f"_repeat_{self._repeat_counter}"
                        cont_slot = GrammarSlot(cont_name, choice, 0, 1)
                        self._repeat_state[cont_name] = (
                            choice, separator, at_least, at_most,
                            items_parsed, capture_name, desc, accumulated_sppf
                        )
                        new_gss = self._create(cont_slot, desc.gss, pos, desc.sppf)
                        self._add(Descriptor(first_slot, new_gss, pos, None))
    
    def _process_sequence(self, seq: GrammarSequence, desc: Descriptor, capture_name: str | None = None) -> None:
        """Process an inline sequence."""
        self._process_sequence_elements(seq.elements, desc, capture_name)
    
    def _process_continuation_sequence(
        self,
        elements: list[GrammarElement],
        desc: Descriptor,
        parent_rule: str,
    ) -> None:
        """
        Process continuation sequence elements.
        When done, complete the parent rule and pop.
        """
        if not elements:
            # Done with continuation - complete the parent rule
            start_pos = desc.sppf.start if desc.sppf else desc.pos
            rule_sppf = self._get_or_create_sppf(parent_rule, start_pos, desc.pos)
            if desc.sppf:
                packed = PackedNode(parent_rule, start_pos, [desc.sppf])
            else:
                packed = PackedNode(parent_rule, start_pos, [])
            if packed not in rule_sppf.families:
                rule_sppf.families.append(packed)
            self._pop(desc.gss, rule_sppf)
            return
        
        first_elem = elements[0]
        rest = elements[1:]
        
        if isinstance(first_elem, (GrammarLiteral, GrammarCharClass)):
            result = self._match_terminal(first_elem, desc.pos)
            if result:
                new_pos, term_sppf = result
                combined = self._combine_sppf(desc.sppf, term_sppf)
                rest_desc = Descriptor(desc.slot, desc.gss, new_pos, combined)
                self._process_continuation_sequence(rest, rest_desc, parent_rule)
        
        elif isinstance(first_elem, GrammarRef):
            rule = self.grammar.rules.get(first_elem.name)
            if rule:
                called_slots = self.grammar.slots.get(first_elem.name, [])
                if called_slots:
                    first_slot = called_slots[0]
                    if not rest:
                        # Last element - create continuation that will complete parent
                        cont_slot = GrammarSlot(
                            f"_final_{parent_rule}_{desc.pos}",
                            GrammarSequence([]),  # empty - just complete
                            0, 1
                        )
                        new_gss = self._create(cont_slot, desc.gss, desc.pos, desc.sppf)
                        self._add(Descriptor(first_slot, new_gss, desc.pos, None))
                    else:
                        # More elements after ref
                        rest_hash = self._hash_elements(rest)
                        cont_name = f"_cont_{parent_rule}_{rest_hash}"
                        cont_slot = GrammarSlot(cont_name, GrammarSequence(rest), 0, 1)
                        new_gss = self._create(cont_slot, desc.gss, desc.pos, desc.sppf)
                        self._add(Descriptor(first_slot, new_gss, desc.pos, None))
    
    def _process_sequence_elements(
        self, 
        elements: list[GrammarElement], 
        desc: Descriptor, 
        capture_name: str | None = None
    ) -> None:
        """Process a list of sequence elements."""
        if not elements:
            # Empty sequence - epsilon, continue to next slot
            next_slot = self._next_slot(desc.slot)
            if next_slot:
                self._add(Descriptor(next_slot, desc.gss, desc.pos, desc.sppf))
            return
        
        first_elem = elements[0]
        rest = elements[1:]
        
        if isinstance(first_elem, (GrammarLiteral, GrammarCharClass)):
            result = self._match_terminal(first_elem, desc.pos)
            if result:
                new_pos, term_sppf = result
                combined = self._combine_sppf(desc.sppf, term_sppf)
                if not rest:
                    # Last element - continue to next slot in parent rule
                    next_slot = self._next_slot(desc.slot)
                    if next_slot:
                        self._add(Descriptor(next_slot, desc.gss, new_pos, combined))
                else:
                    # More elements - continue processing rest of sequence
                    rest_desc = Descriptor(desc.slot, desc.gss, new_pos, combined)
                    self._process_sequence_elements(rest, rest_desc, capture_name)
        
        elif isinstance(first_elem, GrammarRef):
            rule = self.grammar.rules.get(first_elem.name)
            if rule:
                called_slots = self.grammar.slots.get(first_elem.name, [])
                if called_slots:
                    first_slot = called_slots[0]
                    
                    if not rest:
                        # Last element - after ref returns, continue to next slot in parent
                        next_slot = self._next_slot(desc.slot)
                        if next_slot:
                            new_gss = self._create(next_slot, desc.gss, desc.pos, desc.sppf)
                            self._add(Descriptor(first_slot, new_gss, desc.pos, None))
                    else:
                        # More elements after ref - need to create a continuation
                        # Use a deterministic name based on the element content
                        rest_hash = self._hash_elements(rest)
                        cont_name = f"_cont_{desc.slot.rule_name}_{rest_hash}"
                        
                        # Create a synthetic continuation slot
                        cont_slot = GrammarSlot(cont_name, GrammarSequence(rest), 0, 1)
                        new_gss = self._create(cont_slot, desc.gss, desc.pos, desc.sppf)
                        self._add(Descriptor(first_slot, new_gss, desc.pos, None))
        
        elif isinstance(first_elem, GrammarChoice):
            # Process choice inline - each alternative may lead to different continuations
            for alt in first_elem.alternatives:
                if isinstance(alt, (GrammarLiteral, GrammarCharClass)):
                    result = self._match_terminal(alt, desc.pos)
                    if result:
                        new_pos, term_sppf = result
                        combined = self._combine_sppf(desc.sppf, term_sppf)
                        if not rest:
                            next_slot = self._next_slot(desc.slot)
                            if next_slot:
                                self._add(Descriptor(next_slot, desc.gss, new_pos, combined))
                        else:
                            rest_desc = Descriptor(desc.slot, desc.gss, new_pos, combined)
                            self._process_sequence_elements(rest, rest_desc, capture_name)
                elif isinstance(alt, GrammarRef):
                    rule = self.grammar.rules.get(alt.name)
                    if rule:
                        called_slots = self.grammar.slots.get(alt.name, [])
                        if called_slots:
                            first_slot = called_slots[0]
                            if not rest:
                                next_slot = self._next_slot(desc.slot)
                                if next_slot:
                                    new_gss = self._create(next_slot, desc.gss, desc.pos, desc.sppf)
                                    self._add(Descriptor(first_slot, new_gss, desc.pos, None))
                            else:
                                # More elements after ref
                                rest_hash = self._hash_elements(rest)
                                cont_name = f"_cont_{desc.slot.rule_name}_{rest_hash}"
                                cont_slot = GrammarSlot(cont_name, GrammarSequence(rest), 0, 1)
                                new_gss = self._create(cont_slot, desc.gss, desc.pos, desc.sppf)
                                self._add(Descriptor(first_slot, new_gss, desc.pos, None))
                elif isinstance(alt, GrammarSequence):
                    # Nested sequence - flatten
                    combined_elements = list(alt.elements) + list(rest)
                    self._process_sequence_elements(combined_elements, desc, capture_name)
        
        elif isinstance(first_elem, GrammarRepeat):
            # Handle repeat in sequence - process repeat, then continue with rest
            self._process_repeat_in_sequence(first_elem, rest, desc, capture_name)
        
        elif isinstance(first_elem, GrammarCapture):
            # Unwrap capture and process inner element
            inner_elements = [first_elem.rule] + list(rest)
            self._process_sequence_elements(inner_elements, desc, first_elem.name)
        
        elif isinstance(first_elem, GrammarSequence):
            # Nested sequence - flatten
            combined_elements = list(first_elem.elements) + list(rest)
            self._process_sequence_elements(combined_elements, desc, capture_name)
    
    def _process_repeat_in_sequence(
        self,
        repeat: GrammarRepeat,
        rest_elements: list[GrammarElement],
        desc: Descriptor,
        capture_name: str | None = None
    ) -> None:
        """Process a repeat element followed by more sequence elements."""
        # For simplicity, parse repeat items then continue with rest
        self._parse_repeat_items_then_continue(
            repeat.element,
            repeat.separator,
            repeat.at_least,
            repeat.at_most,
            desc,
            items_parsed=0,
            accumulated_sppf=None,
            capture_name=capture_name,
            rest_elements=rest_elements,
        )
    
    def _parse_repeat_items_then_continue(
        self,
        element: GrammarElement,
        separator: GrammarElement | None,
        at_least: int,
        at_most: int | None,
        desc: Descriptor,
        items_parsed: int,
        accumulated_sppf: SPPFNode | None,
        capture_name: str | None,
        rest_elements: list[GrammarElement],
    ) -> None:
        """Parse repeated items, then continue with rest of sequence."""
        pos = desc.pos
        
        # Check if we've reached maximum
        if at_most is not None and items_parsed >= at_most:
            if items_parsed >= at_least:
                if capture_name:
                    final_sppf = self._get_or_create_sppf(f":{capture_name}",
                        accumulated_sppf.start if accumulated_sppf else pos, pos)
                    if accumulated_sppf:
                        final_sppf.families = accumulated_sppf.families[:]
                else:
                    final_sppf = accumulated_sppf
                combined = self._combine_sppf(desc.sppf, final_sppf)
                # Continue with rest of sequence
                rest_desc = Descriptor(desc.slot, desc.gss, pos, combined)
                self._process_sequence_elements(rest_elements, rest_desc, None)
            return
        
        # If we have enough items, we can stop here (but may also continue)
        if items_parsed >= at_least:
            if capture_name:
                final_sppf = self._get_or_create_sppf(f":{capture_name}",
                    accumulated_sppf.start if accumulated_sppf else pos, pos)
                if accumulated_sppf:
                    final_sppf.families = accumulated_sppf.families[:]
            else:
                final_sppf = accumulated_sppf
            combined = self._combine_sppf(desc.sppf, final_sppf)
            # Continue with rest of sequence
            rest_desc = Descriptor(desc.slot, desc.gss, pos, combined)
            self._process_sequence_elements(rest_elements, rest_desc, None)
        
        # Try to parse one more item
        if items_parsed > 0 and separator:
            sep_end = pos + len(separator)
            if sep_end <= self.input_len and self.input[pos:sep_end] == separator:
                pos = sep_end
            else:
                return
        
        if isinstance(element, (GrammarLiteral, GrammarCharClass)):
            result = self._match_terminal(element, pos)
            if result:
                new_pos, item_sppf = result
                new_acc = self._combine_sppf(accumulated_sppf, item_sppf)
                new_desc = Descriptor(desc.slot, desc.gss, new_pos, desc.sppf)
                self._parse_repeat_items_then_continue(
                    element, separator, at_least, at_most, new_desc,
                    items_parsed + 1, new_acc, capture_name, rest_elements,
                )
    
    def parse(self, start_rule: str, input_str: str) -> SPPFNode | None:
        """
        Parse input starting from the given rule.
        Returns the root SPPF node or None if parse fails.
        """
        self._reset(input_str)
        
        # Get the start rule
        if start_rule not in self.grammar.rules:
            raise ValueError(f"Unknown start rule: {start_rule}")
        
        start_slots = self.grammar.slots.get(start_rule, [])
        if not start_slots:
            raise ValueError(f"No slots for start rule: {start_rule}")
        
        # Create bottom GSS node
        bottom_gss = self._get_or_create_gss(None, 0)
        
        # Add initial descriptor
        first_slot = start_slots[0]
        self._add(Descriptor(first_slot, bottom_gss, 0, None))
        
        # Process worklist
        while self.R:
            desc = self.R.pop()
            self._process_slot(desc)
        
        # Find successful parses (complete parses ending at input end)
        result = self.sppf_nodes.get((start_rule, 0, self.input_len))
        return result
    
    def extract_tree(self, sppf: SPPFNode) -> ParseTree:
        """Extract a single parse tree from SPPF, applying disambiguation."""
        return self._extract_with_disambig(sppf)
    
    def _extract_with_disambig(self, sppf: SPPFNode) -> ParseTree:
        """Extract parse tree with disambiguation rules applied."""
        if not sppf.families:
            # Leaf node
            return ParseTree(sppf.label, sppf.start, sppf.end, [])
        
        # Apply disambiguation to select best family
        best_family = self._select_best_family(sppf)
        
        # Recursively extract children
        children = [self._extract_with_disambig(child) for child in best_family.children]
        
        return ParseTree(sppf.label, sppf.start, sppf.end, children)
    
    def _select_best_family(self, sppf: SPPFNode) -> PackedNode:
        """Select the best packed node based on disambiguation rules."""
        if len(sppf.families) == 1:
            return sppf.families[0]
        
        # Score each family
        scored = []
        for family in sppf.families:
            score = self._score_family(family, sppf)
            scored.append((score, family))
        
        # Sort by score (lower is better)
        scored.sort(key=lambda x: x[0])
        return scored[0][1]
    
    def _score_family(self, family: PackedNode, parent: SPPFNode) -> tuple[int, int, int]:
        """
        Score a family for disambiguation.
        Returns (priority_score, associativity_score, arbitrary_tiebreaker).
        Lower scores are preferred.
        """
        # Extract rule name from slot
        rule_name = ""
        if isinstance(family.slot, GrammarSlot):
            rule_name = family.slot.rule_name
        elif isinstance(family.slot, str):
            rule_name = family.slot
        
        # For union/choice disambiguation, we need to look at the child's label
        # to determine which alternative was actually chosen
        effective_rule = rule_name
        if family.children and len(family.children) == 1:
            child = family.children[0]
            # If the child's label is in the priority list, use that for disambiguation
            if child.label in [p for p in self.disambig.priority]:
                effective_rule = child.label
        
        # For sequence nodes (like Expr+"+"+Expr), look up the enclosing rule
        # using the body_to_rule map
        if effective_rule not in self.disambig.associativity and effective_rule not in self.disambig.priority:
            # Try to find the rule that has this as its body
            mapped_rule = self.grammar.body_to_rule.get(parent.label)
            if mapped_rule:
                effective_rule = mapped_rule
        
        # Priority score - use effective_rule for disambiguation
        priority = self.disambig.get_priority(effective_rule)
        
        # Associativity score - also use effective_rule
        assoc = self.disambig.get_associativity(effective_rule)
        assoc_score = 0
        if assoc == 'left':
            # Prefer left-recursive parse (right child should be smaller)
            if len(family.children) >= 2:
                left_size = family.children[0].end - family.children[0].start
                right_size = family.children[-1].end - family.children[-1].start
                assoc_score = -left_size + right_size  # Prefer larger left
        elif assoc == 'right':
            # Prefer right-recursive parse (left child should be smaller)
            if len(family.children) >= 2:
                left_size = family.children[0].end - family.children[0].start
                right_size = family.children[-1].end - family.children[-1].start
                assoc_score = left_size - right_size  # Prefer larger right
        
        return (priority, assoc_score, id(family))


# =============================================================================
# Parse Tree and Result Hydration
# =============================================================================

@dataclass
class ParseTree:
    """A concrete parse tree node."""
    label: str
    start: int
    end: int
    children: list[ParseTree]
    
    def __repr__(self) -> str:
        if self.children:
            children_str = ", ".join(repr(c) for c in self.children)
            return f"Tree({self.label}, [{children_str}])"
        return f"Tree({self.label}, {self.start}:{self.end})"
    
    def get_text(self, input_str: str) -> str:
        """Get the matched text from the input."""
        return input_str[self.start:self.end]
    
    def find_captures(self) -> dict[str, list[ParseTree]]:
        """Find all capture nodes (labels starting with ':')."""
        captures: dict[str, list[ParseTree]] = {}
        self._collect_captures(captures)
        return captures
    
    def _collect_captures(self, captures: dict[str, list[ParseTree]]) -> None:
        if self.label.startswith(':'):
            name = self.label[1:]
            if name not in captures:
                captures[name] = []
            captures[name].append(self)
        for child in self.children:
            child._collect_captures(captures)


class ParseError(Exception):
    """Raised when parsing fails."""
    def __init__(self, message: str, position: int, input_str: str):
        self.position = position
        self.input_str = input_str
        
        # Create helpful error message with context
        line = input_str.count('\n', 0, position) + 1
        col = position - input_str.rfind('\n', 0, position)
        context_start = max(0, position - 20)
        context_end = min(len(input_str), position + 20)
        context = input_str[context_start:context_end]
        pointer_pos = position - context_start
        
        full_message = f"{message} at line {line}, column {col}\n"
        full_message += f"  {context}\n"
        full_message += f"  {' ' * pointer_pos}^"
        
        super().__init__(full_message)


def hydrate_rule(
    tree: ParseTree,
    input_str: str,
    rule_class: type,
    grammar: CompiledGrammar,
) -> object:
    """
    Hydrate a parse tree into a Rule instance.
    Populates fields based on GrammarCapture names in the tree.
    """
    # Create instance without calling __init__
    instance = object.__new__(rule_class)
    
    # Get matched text
    text = tree.get_text(input_str)
    
    # Find all captures in the tree
    captures = tree.find_captures()
    
    # Populate captured fields
    for name, capture_trees in captures.items():
        if len(capture_trees) == 1:
            # Single capture - extract value
            value = _extract_capture_value(capture_trees[0], input_str, grammar)
            setattr(instance, name, value)
        else:
            # Multiple captures - list
            values = [_extract_capture_value(ct, input_str, grammar) for ct in capture_trees]
            setattr(instance, name, values)
    
    # Handle mixin types (Rule, int), (Rule, str), etc.
    for base in rule_class.__mro__:
        if base in (int, float, str, bool) and base is not object:
            # Try to convert the matched text to the mixin type
            try:
                converted = base(text)
                # Store converted value for comparison
                instance._value = converted
            except (ValueError, TypeError):
                pass
            break
    
    return instance


def _extract_capture_value(tree: ParseTree, input_str: str, grammar: CompiledGrammar) -> object:
    """Extract a value from a capture tree."""
    text = tree.get_text(input_str)
    
    # Check if this maps to a known rule
    label = tree.label
    if label.startswith(':'):
        label = label[1:]
    
    rule = grammar.rules.get(label)
    if rule:
        # Recursively hydrate as that rule type
        # Note: This requires access to the Rule class, which we don't have here
        # For now, return the text
        pass
    
    return text


# =============================================================================
# Public API
# =============================================================================

_current_backend: Callable[..., object] | None = None


def set_backend(backend: Callable[..., object]) -> None:
    """Set the current parsing backend."""
    global _current_backend
    _current_backend = backend


def get_backend() -> Callable[..., object] | None:
    """Get the current parsing backend."""
    return _current_backend


def parse(
    rules: list[GrammarRule],
    start_rule: str,
    input_str: str,
    disambig: DisambiguationRules | None = None,
) -> SPPFNode | None:
    """
    Parse input using the given grammar rules.
    
    Args:
        rules: List of grammar rules
        start_rule: Name of the rule to start parsing from
        input_str: Input string to parse
        disambig: Optional disambiguation rules
    
    Returns:
        Root SPPF node of the parse, or None if parse fails
    """
    grammar = CompiledGrammar.from_rules(rules)
    parser = GLLParser(grammar, disambig)
    return parser.parse(start_rule, input_str)


# =============================================================================
# Test Cases
# =============================================================================

def _test_math_expressions():
    """Test parsing math expressions with precedence and associativity."""
    from ..grammar import GrammarRule, GrammarSequence, GrammarChoice, GrammarRef, GrammarLiteral, GrammarCharClass, GrammarCapture, GrammarRepeat
    
    # Define grammar for math expressions
    # Expr ::= Add | Mul | Pow | Group | Num
    # Add ::= Expr ('+' | '-') Expr
    # Mul ::= Expr ('*' | '/') Expr  
    # Pow ::= Expr '^' Expr
    # Group ::= '(' Expr ')'
    # Num ::= [0-9]+
    
    rules = [
        GrammarRule("Expr", "", 0, GrammarSequence([
            GrammarChoice([
                GrammarRef("Add", "", 0),
                GrammarRef("Mul", "", 0),
                GrammarRef("Pow", "", 0),
                GrammarRef("Group", "", 0),
                GrammarRef("Num", "", 0),
            ])
        ])),
        GrammarRule("Add", "", 0, GrammarSequence([
            GrammarCapture("left", GrammarRef("Expr", "", 0)),
            GrammarCharClass("+-"),
            GrammarCapture("right", GrammarRef("Expr", "", 0)),
        ])),
        GrammarRule("Mul", "", 0, GrammarSequence([
            GrammarCapture("left", GrammarRef("Expr", "", 0)),
            GrammarCharClass("*/"),
            GrammarCapture("right", GrammarRef("Expr", "", 0)),
        ])),
        GrammarRule("Pow", "", 0, GrammarSequence([
            GrammarCapture("left", GrammarRef("Expr", "", 0)),
            GrammarLiteral("^"),
            GrammarCapture("right", GrammarRef("Expr", "", 0)),
        ])),
        GrammarRule("Group", "", 0, GrammarSequence([
            GrammarLiteral("("),
            GrammarCapture("expr", GrammarRef("Expr", "", 0)),
            GrammarLiteral(")"),
        ])),
        GrammarRule("Num", "", 0, GrammarSequence([
            GrammarCapture("num", GrammarRepeat(GrammarCharClass("0-9"), at_least=1)),
        ])),
    ]
    
    # Disambiguation: Pow > Mul > Add, Pow is right-assoc, others left-assoc
    disambig = DisambiguationRules(
        priority=["Pow", "Mul", "Add"],
        associativity={"Add": "left", "Mul": "left", "Pow": "right"},
    )
    
    grammar = CompiledGrammar.from_rules(rules)
    parser = GLLParser(grammar, disambig)
    
    # Test: 1+2*3 should parse as 1+(2*3)
    result = parser.parse("Expr", "1+2*3")
    if result:
        print("Math expression parse successful!")
        tree = parser.extract_tree(result)
        print(f"Parse tree: {tree}")
    else:
        print("Math expression parse failed!")
    
    return result


def _test_semver():
    """Test parsing semantic versions."""
    from ..grammar import GrammarRule, GrammarSequence, GrammarChoice, GrammarRef, GrammarLiteral, GrammarCharClass, GrammarCapture, GrammarRepeat
    
    # SemVer ::= major '.' minor '.' patch prerelease? build?
    # major/minor/patch ::= NumId
    # NumId ::= '0' | [1-9][0-9]*
    # prerelease ::= '-' Id ('.' Id)*
    # build ::= '+' Id ('.' Id)*
    # Id ::= [a-zA-Z0-9-]+
    
    rules = [
        GrammarRule("SemVer", "", 0, GrammarSequence([
            GrammarCapture("major", GrammarRef("NumId", "", 0)),
            GrammarLiteral("."),
            GrammarCapture("minor", GrammarRef("NumId", "", 0)),
            GrammarLiteral("."),
            GrammarCapture("patch", GrammarRef("NumId", "", 0)),
            GrammarCapture("prerelease", GrammarChoice([
                GrammarRef("Prerelease", "", 0),
                GrammarLiteral(""),  # optional
            ])),
            GrammarCapture("build", GrammarChoice([
                GrammarRef("Build", "", 0),
                GrammarLiteral(""),  # optional
            ])),
        ])),
        GrammarRule("NumId", "", 0, GrammarSequence([
            GrammarChoice([
                GrammarLiteral("0"),
                GrammarSequence([
                    GrammarCharClass("1-9"),
                    GrammarRepeat(GrammarCharClass("0-9")),
                ]),
            ])
        ])),
        GrammarRule("Prerelease", "", 0, GrammarSequence([
            GrammarLiteral("-"),
            GrammarCapture("ids", GrammarRepeat(GrammarRef("Id", "", 0), at_least=1, separator=".")),
        ])),
        GrammarRule("Build", "", 0, GrammarSequence([
            GrammarLiteral("+"),
            GrammarCapture("ids", GrammarRepeat(GrammarRef("Id", "", 0), at_least=1, separator=".")),
        ])),
        GrammarRule("Id", "", 0, GrammarSequence([
            GrammarRepeat(GrammarCharClass("a-zA-Z0-9-"), at_least=1),
        ])),
    ]
    
    grammar = CompiledGrammar.from_rules(rules)
    parser = GLLParser(grammar)
    
    # Test parsing
    test_versions = ["1.2.3", "1.0.0-alpha", "2.1.0+build.123", "1.2.3-beta.1+build"]
    
    for version in test_versions:
        result = parser.parse("SemVer", version)
        if result:
            print(f"SemVer '{version}' parsed successfully!")
            tree = parser.extract_tree(result)
            print(f"  Tree: {tree}")
        else:
            print(f"SemVer '{version}' failed to parse")
    
    return True


if __name__ == "__main__":
    print("=== Testing Math Expressions ===")
    _test_math_expressions()
    print()
    print("=== Testing Semantic Versions ===")
    _test_semver()
