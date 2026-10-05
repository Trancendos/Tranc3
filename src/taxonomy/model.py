"""Node and Tree — a deliberately small shape.

The taxonomy is read far more often than it is walked, and its value is that
every node says *where its content came from*. A node with no source is a gap,
and a gap that looks identical to a filled node is how a register becomes
decorative. `source` is therefore not optional metadata: it is the field that
separates "the platform has this" from "the diagram has this".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class Node:
    name: str
    kind: str
    #: Where this node's content was read from — a repo path, a dotted symbol,
    #: or "" when nothing supplies it. Empty means gap, and `gaps()` counts it.
    source: str = ""
    detail: str = ""
    children: List["Node"] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def add(self, child: "Node") -> "Node":
        self.children.append(child)
        return child

    def walk(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, name: str) -> Optional["Node"]:
        for node in self.walk():
            if node.name == name:
                return node
        return None

    @property
    def populated(self) -> bool:
        """A node counts as populated when something supplies it.

        Either it names a source, or it has children that do. A branch node with
        populated children is populated even though the branch itself is a label.
        """
        return bool(self.source) or any(c.populated for c in self.children)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"name": self.name, "kind": self.kind}
        if self.source:
            out["source"] = self.source
        if self.detail:
            out["detail"] = self.detail
        if self.meta:
            out["meta"] = self.meta
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        return out


@dataclass
class Tree:
    root: Node

    def to_dict(self) -> Dict[str, Any]:
        return self.root.to_dict()

    def count(self, kind: str) -> int:
        return sum(1 for n in self.root.walk() if n.kind == kind)
