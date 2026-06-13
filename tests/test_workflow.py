# tests/test_workflow.py — Tests for src/workflow/builder.py
"""Comprehensive tests for the WorkflowBuilder and WorkflowDefinition."""

from __future__ import annotations

import json

import pytest
import yaml

from src.workflow.builder import (
    WorkflowBuilder,
    WorkflowDefinition,
    ml_training_workflow,
    self_healing_workflow,
    spark_ignition_workflow,
)
from src.workflow.nodes import NodeType

# ── WorkflowDefinition tests ────────────────────────────────────────────────


class TestWorkflowDefinition:
    def test_defaults(self):
        wf = WorkflowDefinition()
        assert wf.id != ""
        assert wf.name == ""
        assert wf.description == ""
        assert wf.version == "1.0"
        assert wf.nodes == {}
        assert wf.edges == []
        assert wf.triggers == []
        assert wf.metadata == {}

    def test_to_dict(self):
        wf = WorkflowDefinition(name="test", description="desc")
        d = wf.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "desc"
        assert d["engine"] == "the-digital-grid"

    def test_to_json(self):
        wf = WorkflowDefinition(name="test")
        j = wf.to_json()
        parsed = json.loads(j)
        assert parsed["name"] == "test"

    def test_to_yaml(self):
        wf = WorkflowDefinition(name="test")
        y = wf.to_yaml()
        parsed = yaml.safe_load(y)
        assert parsed["name"] == "test"

    def test_from_dict_roundtrip(self):
        wf = WorkflowDefinition(name="roundtrip", description="test", version="2.0")
        d = wf.to_dict()
        restored = WorkflowDefinition.from_dict(d)
        assert restored.name == "roundtrip"
        assert restored.description == "test"
        assert restored.version == "2.0"

    def test_from_json_roundtrip(self):
        wf = WorkflowDefinition(name="json-test")
        j = wf.to_json()
        restored = WorkflowDefinition.from_json(j)
        assert restored.name == "json-test"

    def test_from_yaml_roundtrip(self):
        wf = WorkflowDefinition(name="yaml-test")
        y = wf.to_yaml()
        restored = WorkflowDefinition.from_yaml(y)
        assert restored.name == "yaml-test"


# ── WorkflowBuilder tests ───────────────────────────────────────────────────


class TestWorkflowBuilder:
    def test_minimal_workflow(self):
        wf = WorkflowBuilder("minimal").build()
        assert wf.name == "minimal"

    def test_add_node_returns_id(self):
        b = WorkflowBuilder("test")
        nid = b.add_node(NodeType.OUTPUT, "out")
        assert nid != ""

    def test_custom_node_id(self):
        b = WorkflowBuilder("test")
        nid = b.add_node(NodeType.OUTPUT, "out", node_id="my-node")
        assert nid == "my-node"

    def test_multiple_nodes(self):
        b = WorkflowBuilder("test")
        b.add_node(NodeType.TRIGGER, "start")
        b.add_node(NodeType.OUTPUT, "end")
        wf = b.build()
        assert len(wf.nodes) == 2

    def test_connect_nodes(self):
        b = WorkflowBuilder("test")
        n1 = b.add_node(NodeType.TRIGGER, "start")
        n2 = b.add_node(NodeType.OUTPUT, "end")
        b.connect(n1, n2)
        wf = b.build()
        assert len(wf.edges) == 1
        assert wf.edges[0][0] == n1
        assert wf.edges[0][1] == n2
        assert wf.edges[0][2] == "default"

    def test_connect_with_label(self):
        b = WorkflowBuilder("test")
        n1 = b.add_node(NodeType.CONDITION, "check")
        n2 = b.add_node(NodeType.OUTPUT, "yes")
        b.connect(n1, n2, label="true")
        wf = b.build()
        assert wf.edges[0][2] == "true"

    def test_connect_unknown_source_raises(self):
        b = WorkflowBuilder("test")
        b.add_node(NodeType.OUTPUT, "end", node_id="end")
        with pytest.raises(ValueError, match="Source node"):
            b.connect("nonexistent", "end")

    def test_connect_unknown_target_raises(self):
        b = WorkflowBuilder("test")
        b.add_node(NodeType.TRIGGER, "start", node_id="start")
        with pytest.raises(ValueError, match="Target node"):
            b.connect("start", "nonexistent")

    def test_set_trigger(self):
        b = WorkflowBuilder("test")
        b.add_node(NodeType.TRIGGER, "start")
        b.set_trigger("event.a", "event.b")
        wf = b.build()
        assert "event.a" in wf.triggers
        assert "event.b" in wf.triggers

    def test_set_metadata(self):
        b = WorkflowBuilder("test")
        b.set_metadata(category="ops", priority="high")
        wf = b.build()
        assert wf.metadata["category"] == "ops"
        assert wf.metadata["priority"] == "high"

    def test_build_copies_data(self):
        """build() should snapshot data, not reference the builder's internal dicts."""
        b = WorkflowBuilder("test")
        b.add_node(NodeType.OUTPUT, "out")
        wf = b.build()
        # Modify builder after build
        b.set_metadata(new_key="value")
        assert "new_key" not in wf.metadata


# ── Validation tests ────────────────────────────────────────────────────────


class TestWorkflowBuilderValidation:
    def test_valid_workflow(self):
        b = WorkflowBuilder("valid")
        n1 = b.add_node(NodeType.TRIGGER, "start")
        n2 = b.add_node(NodeType.OUTPUT, "end")
        b.connect(n1, n2)
        assert b.validate() == []

    def test_missing_name(self):
        b = WorkflowBuilder("")
        b.add_node(NodeType.OUTPUT, "out")
        errors = b.validate()
        assert any("name" in e.lower() for e in errors)

    def test_no_nodes(self):
        b = WorkflowBuilder("empty")
        errors = b.validate()
        assert any("no nodes" in e.lower() for e in errors)

    def test_cycle_detection(self):
        b = WorkflowBuilder("cyclic")
        n1 = b.add_node(NodeType.TRIGGER, "A")
        n2 = b.add_node(NodeType.CONDITION, "B")
        n3 = b.add_node(NodeType.OUTPUT, "C")
        b.connect(n1, n2)
        b.connect(n2, n3)
        b.connect(n3, n1)  # cycle!
        errors = b.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_orphan_nodes(self):
        b = WorkflowBuilder("orphans")
        n1 = b.add_node(NodeType.TRIGGER, "connected")
        n2 = b.add_node(NodeType.OUTPUT, "connected-out")
        b.add_node(NodeType.OUTPUT, "orphan")
        b.connect(n1, n2)
        errors = b.validate()
        assert any("orphan" in e.lower() for e in errors)

    def test_triggers_without_trigger_node(self):
        b = WorkflowBuilder("triggers-no-node")
        b.add_node(NodeType.OUTPUT, "out")
        b.set_trigger("some.event")
        errors = b.validate()
        assert any("trigger" in e.lower() for e in errors)

    def test_single_node_no_orphan_warning(self):
        b = WorkflowBuilder("single")
        b.add_node(NodeType.OUTPUT, "only")
        errors = b.validate()
        assert not any("orphan" in e.lower() for e in errors)


# ── Pre-built workflow tests ────────────────────────────────────────────────


class TestPrebuiltWorkflows:
    def test_spark_ignition_structure(self):
        wf = spark_ignition_workflow()
        assert wf.name == "Spark Ignition"
        assert len(wf.nodes) >= 4
        assert len(wf.edges) >= 3

    def test_spark_ignition_valid(self):
        wf = spark_ignition_workflow()
        # Build a builder from the definition for validation
        b2 = WorkflowBuilder(wf.name, wf.description)
        b2._nodes = wf.nodes
        b2._edges = wf.edges
        b2._triggers = wf.triggers
        b2._metadata = wf.metadata
        errors = b2.validate()
        assert errors == []

    def test_self_healing_structure(self):
        wf = self_healing_workflow()
        assert wf.name == "Self-Healing"
        assert len(wf.nodes) >= 5

    def test_ml_training_structure(self):
        wf = ml_training_workflow()
        assert wf.name == "ML Training Pipeline"
        assert len(wf.nodes) >= 5

    def test_spark_ignition_serialization_roundtrip(self):
        wf = spark_ignition_workflow()
        json_str = wf.to_json()
        restored = WorkflowDefinition.from_json(json_str)
        assert restored.name == wf.name
        assert len(restored.nodes) == len(wf.nodes)

    def test_self_healing_serialization_roundtrip(self):
        wf = self_healing_workflow()
        yaml_str = wf.to_yaml()
        restored = WorkflowDefinition.from_yaml(yaml_str)
        assert restored.name == wf.name

    def test_ml_training_serialization_roundtrip(self):
        wf = ml_training_workflow()
        d = wf.to_dict()
        restored = WorkflowDefinition.from_dict(d)
        assert restored.name == wf.name
        assert len(restored.edges) == len(wf.edges)
