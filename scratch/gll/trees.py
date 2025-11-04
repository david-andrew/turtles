from dataclasses import dataclass, field
from grammar import Slot, Grammar, Sentence, NonTerminal, Terminal, Symbol

import pdb



############################### Binary Subtree Representation ###############################

BSR = tuple[Slot, int, int, int]            #(g:Slot, l:int, k:int, r:int)


def find_roots(start:NonTerminal, Y:set[BSR], length:int) -> set[BSR]:
    """Find all BSRs in Y that are roots of the parse tree

    Args:
        start (NonTerminal): The start symbol of the grammar
        Y (set[BSR]): The BSR set
        length (int): The length of the input string

    Returns:
        set[BSR]: The set of BSRs that are roots of the parse tree
    """

    result = set()
    for y in Y:
        g, l, k, r = y
        if g.X == start and l == 0 and r == length and len(g.beta) == 0:
            result.add(y)

    return result

#TODO: broken
# def find_children(Y: set[BSR], y0: BSR) -> list[BSR]:
#         g0, l0, k0, r0 = y0
#         lefts, rights = [], []
#         for y in Y:
#             g, l, k, r = y
#             if l == l0 and r == k0: #TODO: other checks...
#                 lefts.append(y)
#             elif l == k0 and r == r0: #TODO: other checks...
#                 rights.append(y)

#         if r0 - k0 == 1:
#             #tau[k0:r0]
#             assert isinstance(g0.alpha[-1], Terminal)
#             rights.append(g0.alpha[-1])

#         pdb.set_trace()
#         # return children


# def build_tree(Y: set[BSR], node: BSR) -> list[tuple[BSR, list]]:
#     children = find_children(Y, node)
#     tree = []
#     for child in children:
#         subtree = build_tree(Y, child)
#         tree.append((child, subtree))
#     return tree

# def bsr_tree_str(X:NonTerminal, Y:set[BSR], length:int) -> str:
#     roots = find_roots(X, Y, length)
#     if len(roots) == 0:
#         return "No roots found in the BSR set."

#     trees = [build_tree(Y, root) for root in roots]
#     pdb.set_trace()
#     # return tree_to_string(tree)






############################### Shared Packed Parse Forest ################################

# class SPPF:
#     def __init__(self):
#         self.nodes: set[SPPFNode] = set()
#         self.edges: dict[SPPFNode, list[SPPFNode]] = {}
#     # add node labelled (S, 0, n)
#     # add node labelled (X ::= α·δ, k)
#     # check if there are any extendable leaf nodes
#     # (μ, i, j) is an extendable leaf node
#     # node labelled (Ω, i, j)
#     # add an edge from y to the node (Ω, i, j)

# class SPPFNode:...
#     #ambiguous nodes...
#     #...

# def extractSPPF(*args, **kwargs):
#     raise NotImplementedError

# def sppf_tree_str(*args, **kwargs):
#     raise NotImplementedError

"""
extractSPPF (Υ, Γ)
{
    G := empty graph
    let S be the start symbol of Γ
    let n be the extent of Υ
    if Υ has an element of the form (S ::= α, 0, k, n)
    {
        create a node labelled (S, 0, n) in G
        while G has an extendable leaf node
        {
            let w = (μ, i, j) be an extendable leaf node of G
            if (μ is a nonterminal X in Γ)
            {
                for each (X ::= γ, i, k, j) ∈ Υ
                {
                    mkPN(X ::= γ·, i, k, j, G)
                }
            }
            else
            {
                suppose μ is X ::= α·δ
                if (|α| = 1)
                {
                    mkPN(X ::= α·δ, i, i, j, G)
                }
                else for each (α, i, k, j) ∈ Υ
                {
                    mkPN(X ::= α·δ, i, k, j, G)
                }
            }
        }
    }
    return G
}

mkPN(X ::= α·δ, i, k, j, G)
{
    make a node y in G labelled (X ::= α·δ, k)
    if (α = ϵ)
    {
        mkN(ϵ, i, i, y, G)
    }
    if (α = βx, where |x| = 1)
    {
        mkN(x, k, j, y, G)
        if (|β| = 1)
        {
            mkN(β, i, k, y, G)
        }
        if (|β| > 1)
        {
            mkN(X ::= β·xδ, i, k, y, G)
        }
    }
}

mkN (Ω, i, j, y, G)
{
    if there is not a node labelled (Ω, i, j) in G make one
    add an edge from y to the node (Ω, i, j)
}
"""


############################### Shared Packed Parse Forest ################################

# --- Helpers ------------------------------------------------------------------------------

def _sent_tuple(s: Sentence) -> tuple:
    return tuple(s.symbols)  # stable, hashable

# We’ll use a sentinel to represent epsilon in SPPF symbol nodes.
class _Epsilon:
    def __repr__(self): return "ϵ"
EPSILON = _Epsilon()


# --- SPPF node types ----------------------------------------------------------------------

@dataclass(frozen=True, eq=True)
class SPPFNode:
    """Base node identity for SPPF graph.
    We model two kinds:
      - kind == 'sym'  : a symbol node labelled (Ω, i, j) where Ω is NonTerminal/Terminal/ϵ
      - kind == 'item' : an (intermediate/packed) node labelled (X ::= α·δ, k) over span [i,j]
    """
    kind: str
    i: int
    j: int
    # For 'sym': set 'sym' field and leave others None
    sym: object|None = None  # NonTerminal | Terminal | EPSILON
    # For 'item': set X, alpha, delta, k
    X: NonTerminal|None = None
    alpha: tuple|None = None
    delta: tuple|None = None
    k: int|None = None

    def short(self) -> str:
        if self.kind == 'sym':
            if isinstance(self.sym, NonTerminal):
                return f"({self.sym}, {self.i}, {self.j})"
            if isinstance(self.sym, Terminal):
                return f"('{self.sym.t}', {self.i}, {self.j})"
            return f"(ϵ, {self.i}, {self.j})"
        # item
        def seq_to_str(tup):
            return " ".join(map(str, tup)) if tup else "ϵ"
        return f"({self.X} ::= {seq_to_str(self.alpha)}•{seq_to_str(self.delta)}, k={self.k}) [{self.i},{self.j}]"

    def __str__(self) -> str:
        return self.short()


@dataclass
class SPPF:
    """A compact graph with packed alternatives."""
    nodes: set[SPPFNode] = field(default_factory=set)
    # For each parent node, store a list of alternatives; each alternative is a tuple of child nodes.
    alts: dict[SPPFNode, list[tuple[SPPFNode, ...]]] = field(default_factory=dict)
    # Entrypoints (usually a single NonTerminal node (Start, 0, n))
    roots: list[SPPFNode] = field(default_factory=list)

    def ensure_alt(self, parent: SPPFNode, children: tuple[SPPFNode, ...]):
        self.nodes.add(parent)
        for ch in children:
            self.nodes.add(ch)
        self.alts.setdefault(parent, [])
        # avoid duplicate alternatives
        if children not in self.alts[parent]:
            self.alts[parent].append(children)

    def ensure_node(self, node: SPPFNode) -> SPPFNode:
        self.nodes.add(node)
        self.alts.setdefault(node, [])
        return node


# --- SPPF extraction from BSR -------------------------------------------------------------

def extractSPPF(Y: set[BSR], Γ: Grammar) -> SPPF:
    """Build a full SPPF (with all packed alternatives) from the BSR set Y.

    This follows the functional GLL paper's extractSPPF/mkPN/mkN outline,
    adapted to the data we recorded in Y:
      - Completed items: (X ::= γ•, i, k, j)  => len(beta)==0
      - Intermediate items: (X ::= α•δ, i, k, j) for various α splits.
    """
    sppf = SPPF()

    if not Y:
        return sppf

    # Compute the overall input extent n from Y
    n = max(r for (_g, _l, _k, r) in Y)
    S = Γ.start

    # We only build an SPPF if there's a successful completion for the start symbol over [0, n].
    has_success = any(g.X == S and l == 0 and r == n and len(g.beta) == 0 for (g, l, k, r) in Y)
    if not has_success:
        return sppf

    # Indices for fast lookup:
    # 1) Completed rules for a nonterminal over [i,j]: (X, i, j) -> list[(rule γ, k)]
    complete_map: dict[tuple[NonTerminal, int, int], list[tuple[Sentence, int]]] = {}
    # 2) All splits "k" seen for a given (X ::= α·δ, i, j): (X, α_tuple, i, j) -> set{k}
    alpha_splits: dict[tuple[NonTerminal, tuple, int, int], set[int]] = {}

    for g, l, k, r in Y:
        # record completed
        if len(g.beta) == 0:
            complete_map.setdefault((g.X, l, r), []).append((g.rule, k))
        # record any split seen for this alpha
        αt = _sent_tuple(g.alpha)
        alpha_splits.setdefault((g.X, αt, l, r), set()).add(k)

    # Root is a symbol node (S, 0, n)
    root = SPPFNode(kind='sym', sym=S, i=0, j=n)
    sppf.ensure_node(root)
    sppf.roots = [root]

    # Worklist-based expansion of "extendable" leaves.
    # Leaves are nodes currently present whose alternatives haven't been added yet.
    to_expand: list[SPPFNode] = [root]
    expanded: set[SPPFNode] = set()

    def sym_node(Ω: object, i: int, j: int) -> SPPFNode:
        return sppf.ensure_node(SPPFNode(kind='sym', sym=Ω, i=i, j=j))

    def item_node(X: NonTerminal, α: tuple, δ: tuple, k: int, i: int, j: int) -> SPPFNode:
        return sppf.ensure_node(SPPFNode(kind='item', X=X, alpha=α, delta=δ, k=k, i=i, j=j))

    while to_expand:
        node = to_expand.pop()
        if node in expanded:
            continue
        expanded.add(node)

        if node.kind == 'sym':
            # Only nonterminals expand; terminals and epsilon are leaves.
            if isinstance(node.sym, NonTerminal):
                key = (node.sym, node.i, node.j)
                for (γ, k) in complete_map.get(key, []):
                    α = _sent_tuple(γ)  # α = γ, δ = ε at completion
                    child = item_node(node.sym, α, tuple(), k, node.i, node.j)
                    sppf.ensure_alt(node, (child,))
                    # expand the child later
                    if child not in expanded:
                        to_expand.append(child)

        else:  # 'item'
            X, α, δ, k, i, j = node.X, node.alpha, node.delta, node.k, node.i, node.j
            α_len = len(α) if α else 0

            # mkPN(X ::= α·δ, i, kx, j) for appropriate kx (possibly a single kx=i if |α|==1)
            if α_len == 0:
                # α = ϵ
                ch = sym_node(EPSILON, i, i)
                sppf.ensure_alt(node, (ch,))
                # epsilon leaf; nothing more to expand
            elif α_len == 1:
                # α = x (|x|=1) -> one packed alternative with kx = i
                x = α[0]
                right = sym_node(x, i, j)
                sppf.ensure_alt(node, (right,))
                # 'right' may be a NonTerminal; if so, it might need expansion
                if isinstance(x, NonTerminal) and right not in expanded:
                    to_expand.append(right)
            else:
                # |α| > 1: we need all splits kx for α over span [i,j] witnessed in Y
                kxs = alpha_splits.get((X, α, i, j), set())
                if not kxs:
                    # No recorded split for this α over [i,j]; nothing to add.
                    # (This can happen if the input is invalid or due to partial Υ.)
                    continue

                x = α[-1]
                β = α[:-1]
                for kx in sorted(kxs):
                    right = sym_node(x, kx, j)
                    # Left child depends on |β|
                    if len(β) == 1:
                        left = sym_node(β[0], i, kx)
                    else:
                        # Recurse with (X ::= β·xδ, kx) over [i, kx]
                        left = item_node(X, β, (x,) + (δ or ()), kx, i, kx)

                    sppf.ensure_alt(node, (left, right))

                    # Schedule possible expansions
                    if isinstance(x, NonTerminal) and right not in expanded:
                        to_expand.append(right)
                    if left.kind == 'sym':
                        if isinstance(left.sym, NonTerminal) and left not in expanded:
                            to_expand.append(left)
                    else:
                        if left not in expanded:
                            to_expand.append(left)

    return sppf


# --- Pretty printer that shows the WHOLE SPPF (with packed alts) --------------------------

def sppf_tree_str(forest: SPPF, Γ: Grammar, input_text:str|None = None) -> str:
    """Return a readable string for the entire SPPF, showing ALL packed alternatives.

    Format:
      - We assign stable numeric IDs to nodes reachable from roots.
      - Each node is printed once, followed by its alternatives:
          Node #id: <label>
            alt 1 -> [#child_id, ...]
            alt 2 -> [#child_id, ...]
      - Terminals also show the matched substring if 'input_text' is provided.
    """
    if not forest.roots:
        return "<empty SPPF>"

    # Collect reachable nodes
    reachable: set[SPPFNode] = set()
    stack = list(forest.roots)
    while stack:
        u = stack.pop()
        if u in reachable:
            continue
        reachable.add(u)
        for alt in forest.alts.get(u, []):
            for v in alt:
                if v not in reachable:
                    stack.append(v)

    # Assign IDs in a deterministic BFS order from roots
    order: list[SPPFNode] = []
    seen = set()
    from collections import deque
    dq = deque(forest.roots)
    while dq:
        u = dq.popleft()
        if u in seen:
            continue
        if u not in reachable:
            continue
        seen.add(u)
        order.append(u)
        for alt in forest.alts.get(u, []):
            for v in alt:
                if v not in seen:
                    dq.append(v)

    id_of: dict[SPPFNode, int] = {node: i+1 for i, node in enumerate(order)}

    lines: list[str] = []
    def node_header(n: SPPFNode) -> str:
        s = n.short()
        if n.kind == 'sym' and isinstance(n.sym, Terminal) and input_text is not None:
            frag = input_text[n.i:n.j] if 0 <= n.i <= n.j <= len(input_text) else ""
            s += f" -> '{frag}'"
        return s

    # Print nodes and their packed alternatives
    for n in order:
        lines.append(f"[#{id_of[n]}] {node_header(n)}")
        alts = forest.alts.get(n, [])
        if not alts:
            continue
        for idx, alt in enumerate(alts, start=1):
            child_ids = ", ".join(f"#{id_of[ch]}" for ch in alt)
            lines.append(f"  alt {idx} -> [{child_ids}]")
        # spacer
        lines.append("")

    # Also print a tiny “roots” header at the end
    root_ids = ", ".join(f"#{id_of[r]}" for r in forest.roots if r in id_of)
    lines.append(f"Roots: [{root_ids}]")

    return "\n".join(lines)
