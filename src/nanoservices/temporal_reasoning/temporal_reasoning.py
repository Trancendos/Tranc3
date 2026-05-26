"""Temporal Reasoning Engine — Phase 10

Time-aware inference engine supporting Allen's interval algebra,
point-based temporal logic, LTL model checking, and event
calculus for reasoning about change over time.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class TemporalRelation(Enum):
    BEFORE = "before"
    AFTER = "after"
    DURING = "during"
    CONTAINS = "contains"
    OVERLAPS = "overlaps"
    MEETS = "meets"
    MET_BY = "met_by"
    STARTS = "starts"
    FINISHES = "finishes"
    EQUALS = "equals"
    SIMULTANEOUS = "simultaneous"


class LTLFormulaType(Enum):
    ATOMIC = "atomic"
    NOT = "not"
    AND = "and"
    OR = "or"
    IMPLIES = "implies"
    NEXT = "next"          # X
    EVENTUALLY = "eventually"  # F
    ALWAYS = "always"      # G
    UNTIL = "until"        # U
    RELEASE = "release"    # R


@dataclass
class TimePoint:
    """A point in time."""
    timestamp: float = 0.0
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"timestamp": self.timestamp, "label": self.label}


@dataclass
class TimeInterval:
    """A closed interval of time [start, end]."""
    start: float = 0.0
    end: float = 1.0
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0, self.end - self.start)

    def contains_point(self, t: float) -> bool:
        return self.start <= t <= self.end

    def relation_to(self, other: TimeInterval) -> TemporalRelation:
        if self.start == other.start and self.end == other.end:
            return TemporalRelation.EQUALS
        if self.end < other.start:
            return TemporalRelation.BEFORE
        if self.start > other.end:
            return TemporalRelation.AFTER
        if self.start >= other.start and self.end <= other.end:
            return TemporalRelation.DURING
        if self.start <= other.start and self.end >= other.end:
            return TemporalRelation.CONTAINS
        if self.end == other.start:
            return TemporalRelation.MEETS
        if self.start == other.end:
            return TemporalRelation.MET_BY
        if self.start < other.start < self.end < other.end:
            return TemporalRelation.OVERLAPS
        if self.start == other.start and self.end < other.end:
            return TemporalRelation.STARTS
        if self.end == other.end and self.start > other.start:
            return TemporalRelation.FINISHES
        return TemporalRelation.BEFORE

    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start, "end": self.end, "duration": self.duration, "label": self.label}


@dataclass
class TemporalEvent:
    """An event occurring at a time point or interval."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    interval: TimeInterval = field(default_factory=TimeInterval)
    properties: Dict[str, Any] = field(default_factory=dict)
    fluents: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "interval": self.interval.to_dict(),
            "properties": self.properties,
        }


@dataclass
class TemporalFact:
    """A fact that holds during a time interval."""
    fact_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    predicate: str = ""
    arguments: List[str] = field(default_factory=list)
    interval: TimeInterval = field(default_factory=TimeInterval)
    confidence: float = 1.0

    def holds_at(self, t: float) -> bool:
        return self.interval.contains_point(t)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "predicate": self.predicate,
            "arguments": self.arguments,
            "interval": self.interval.to_dict(),
            "confidence": self.confidence,
        }


@dataclass
class LTLFormula:
    """Linear Temporal Logic formula."""
    formula_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    formula_type: LTLFormulaType = LTLFormulaType.ATOMIC
    proposition: str = ""
    left: Optional[LTLFormula] = None
    right: Optional[LTLFormula] = None
    negated: bool = False

    def to_string(self) -> str:
        if self.formula_type == LTLFormulaType.ATOMIC:
            return f"¬{self.proposition}" if self.negated else self.proposition
        elif self.formula_type == LTLFormulaType.NOT:
            return f"¬({self.left.to_string() if self.left else ''})"
        elif self.formula_type == LTLFormulaType.AND:
            return f"({self.left.to_string() if self.left else ''} ∧ {self.right.to_string() if self.right else ''})"
        elif self.formula_type == LTLFormulaType.OR:
            return f"({self.left.to_string() if self.left else ''} ∨ {self.right.to_string() if self.right else ''})"
        elif self.formula_type == LTLFormulaType.NEXT:
            return f"X({self.left.to_string() if self.left else ''})"
        elif self.formula_type == LTLFormulaType.EVENTUALLY:
            return f"F({self.left.to_string() if self.left else ''})"
        elif self.formula_type == LTLFormulaType.ALWAYS:
            return f"G({self.left.to_string() if self.left else ''})"
        elif self.formula_type == LTLFormulaType.UNTIL:
            return f"({self.left.to_string() if self.left else ''} U {self.right.to_string() if self.right else ''})"
        elif self.formula_type == LTLFormulaType.IMPLIES:
            return f"({self.left.to_string() if self.left else ''} → {self.right.to_string() if self.right else ''})"
        return self.proposition


class AllenAlgebraEngine:
    """Allen's interval algebra for temporal reasoning."""

    INVERSE = {
        TemporalRelation.BEFORE: TemporalRelation.AFTER,
        TemporalRelation.AFTER: TemporalRelation.BEFORE,
        TemporalRelation.DURING: TemporalRelation.CONTAINS,
        TemporalRelation.CONTAINS: TemporalRelation.DURING,
        TemporalRelation.OVERLAPS: TemporalRelation.OVERLAPS,
        TemporalRelation.MEETS: TemporalRelation.MET_BY,
        TemporalRelation.MET_BY: TemporalRelation.MEETS,
        TemporalRelation.STARTS: TemporalRelation.STARTS,
        TemporalRelation.FINISHES: TemporalRelation.FINISHES,
        TemporalRelation.EQUALS: TemporalRelation.EQUALS,
    }

    def relate(self, a: TimeInterval, b: TimeInterval) -> TemporalRelation:
        return a.relation_to(b)

    def compose(self, r1: TemporalRelation, r2: TemporalRelation) -> Set[TemporalRelation]:
        if r1 == TemporalRelation.BEFORE and r2 == TemporalRelation.BEFORE:
            return {TemporalRelation.BEFORE}
        if r1 == TemporalRelation.DURING and r2 == TemporalRelation.BEFORE:
            return {TemporalRelation.BEFORE, TemporalRelation.DURING, TemporalRelation.OVERLAPS}
        if r1 == TemporalRelation.CONTAINS and r2 == TemporalRelation.CONTAINS:
            return {TemporalRelation.CONTAINS}
        if r1 == TemporalRelation.EQUALS:
            return {r2}
        if r2 == TemporalRelation.EQUALS:
            return {r1}
        return {TemporalRelation.BEFORE, TemporalRelation.AFTER, TemporalRelation.DURING,
                TemporalRelation.CONTAINS, TemporalRelation.OVERLAPS, TemporalRelation.EQUALS}


class EventCalculusEngine:
    """Event calculus for reasoning about change over time.

    Models fluents that are initiated and terminated by events.
    """

    def __init__(self):
        self.events: List[TemporalEvent] = []
        self.initiated: Dict[str, List[Tuple[str, TimeInterval]]] = {}
        self.terminated: Dict[str, List[Tuple[str, TimeInterval]]] = {}

    def happens(self, event: TemporalEvent):
        self.events.append(event)

    def initiates(self, event_name: str, fluent: str, interval: TimeInterval):
        if fluent not in self.initiated:
            self.initiated[fluent] = []
        self.initiated[fluent].append((event_name, interval))

    def terminates(self, event_name: str, fluent: str, interval: TimeInterval):
        if fluent not in self.terminated:
            self.terminated[fluent] = []
        self.terminated[fluent].append((event_name, interval))

    def holds_at(self, fluent: str, t: float) -> bool:
        initiated = False
        for event_name, interval in self.initiated.get(fluent, []):
            if interval.start <= t:
                initiated = True
                break
        if not initiated:
            return False
        for event_name, interval in self.terminated.get(fluent, []):
            if interval.start <= t:
                return False
        return True

    def trajectory(self, fluent: str, start: float, end: float,
                    step: float = 1.0) -> List[Tuple[float, bool]]:
        result = []
        t = start
        while t <= end:
            result.append((t, self.holds_at(fluent, t)))
            t += step
        return result


class LTLModelChecker:
    """Simple LTL model checker over discrete time traces."""

    def check(self, formula: LTLFormula, trace: List[Set[str]]) -> bool:
        return self._check_at(formula, trace, 0)

    def _check_at(self, formula: LTLFormula, trace: List[Set[str]], pos: int) -> bool:
        if pos >= len(trace):
            return False

        if formula.formula_type == LTLFormulaType.ATOMIC:
            result = formula.proposition in trace[pos]
            return not result if formula.negated else result

        elif formula.formula_type == LTLFormulaType.NOT:
            return not self._check_at(formula.left, trace, pos) if formula.left else False

        elif formula.formula_type == LTLFormulaType.AND:
            left = self._check_at(formula.left, trace, pos) if formula.left else True
            right = self._check_at(formula.right, trace, pos) if formula.right else True
            return left and right

        elif formula.formula_type == LTLFormulaType.OR:
            left = self._check_at(formula.left, trace, pos) if formula.left else False
            right = self._check_at(formula.right, trace, pos) if formula.right else False
            return left or right

        elif formula.formula_type == LTLFormulaType.IMPLIES:
            left = self._check_at(formula.left, trace, pos) if formula.left else True
            right = self._check_at(formula.right, trace, pos) if formula.right else True
            return not left or right

        elif formula.formula_type == LTLFormulaType.NEXT:
            return self._check_at(formula.left, trace, pos + 1) if formula.left else False

        elif formula.formula_type == LTLFormulaType.EVENTUALLY:
            for i in range(pos, len(trace)):
                if formula.left and self._check_at(formula.left, trace, i):
                    return True
            return False

        elif formula.formula_type == LTLFormulaType.ALWAYS:
            for i in range(pos, len(trace)):
                if formula.left and not self._check_at(formula.left, trace, i):
                    return False
            return True

        elif formula.formula_type == LTLFormulaType.UNTIL:
            for i in range(pos, len(trace)):
                if formula.right and self._check_at(formula.right, trace, i):
                    return True
                if formula.left and not self._check_at(formula.left, trace, i):
                    return False
            return False

        return False


class TemporalReasoningEngine:
    """Time-aware inference engine.

    Features:
    - Allen's interval algebra for interval relations
    - Point-based temporal queries (holds-at, holds-during)
    - Event calculus for reasoning about change
    - LTL model checking over discrete traces
    - Temporal fact management with confidence decay
    - Event timeline construction and querying
    """

    def __init__(self):
        self.facts: Dict[str, TemporalFact] = {}
        self.events: Dict[str, TemporalEvent] = {}
        self.allen = AllenAlgebraEngine()
        self.event_calculus = EventCalculusEngine()
        self.ltl_checker = LTLModelChecker()
        self._id = str(uuid.uuid4())[:8]

    def add_fact(self, predicate: str, arguments: List[str],
                  start: float, end: float,
                  confidence: float = 1.0) -> TemporalFact:
        fact = TemporalFact(
            predicate=predicate,
            arguments=arguments,
            interval=TimeInterval(start=start, end=end),
            confidence=confidence,
        )
        self.facts[fact.fact_id] = fact
        return fact

    def add_event(self, name: str, start: float, end: float,
                   properties: Optional[Dict[str, Any]] = None) -> TemporalEvent:
        event = TemporalEvent(
            name=name,
            interval=TimeInterval(start=start, end=end),
            properties=properties or {},
        )
        self.events[event.event_id] = event
        self.event_calculus.happens(event)
        return event

    def query_holds_at(self, predicate: str, t: float) -> List[TemporalFact]:
        return [f for f in self.facts.values()
                if f.predicate == predicate and f.holds_at(t)]

    def query_holds_during(self, predicate: str, start: float,
                            end: float) -> List[TemporalFact]:
        interval = TimeInterval(start=start, end=end)
        return [f for f in self.facts.values()
                if f.predicate == predicate
                and f.interval.relation_to(interval) in (
                    TemporalRelation.DURING, TemporalRelation.EQUALS,
                    TemporalRelation.OVERLAPS, TemporalRelation.STARTS,
                    TemporalRelation.FINISHES, TemporalRelation.CONTAINS,
                )]

    def query_interval_relation(self, interval_a: TimeInterval,
                                 interval_b: TimeInterval) -> TemporalRelation:
        return self.allen.relate(interval_a, interval_b)

    def check_ltl(self, formula: LTLFormula, trace: List[Set[str]]) -> bool:
        return self.ltl_checker.check(formula, trace)

    def event_calculus_initiates(self, event_name: str, fluent: str,
                                  interval: TimeInterval):
        self.event_calculus.initiates(event_name, fluent, interval)

    def event_calculus_terminates(self, event_name: str, fluent: str,
                                   interval: TimeInterval):
        self.event_calculus.terminates(event_name, fluent, interval)

    def fluent_holds_at(self, fluent: str, t: float) -> bool:
        return self.event_calculus.holds_at(fluent, t)

    def get_timeline(self, start: float, end: float,
                      step: float = 1.0) -> List[Dict[str, Any]]:
        timeline = []
        t = start
        while t <= end:
            active_facts = [f.to_dict() for f in self.facts.values() if f.holds_at(t)]
            active_events = [e.to_dict() for e in self.events.values()
                           if e.interval.contains_point(t)]
            timeline.append({
                "time": t,
                "active_facts": len(active_facts),
                "active_events": len(active_events),
            })
            t += step
        return timeline

    def get_engine_status(self) -> Dict[str, Any]:
        return {
            "engine_id": self._id,
            "total_facts": len(self.facts),
            "total_events": len(self.events),
            "predicates": list(set(f.predicate for f in self.facts.values())),
            "event_names": list(set(e.name for e in self.events.values())),
        }
