import { describe, it, expect } from "vitest";
import type { WorkflowDef } from "./types";
import {
  encodeWorkflow,
  decodeWorkflow,
  decodeWorkflowList,
  decodeSaveResponse,
  decodeExecution,
  decodeCancellation,
} from "./gridContract";

const graph: WorkflowDef = {
  id: "wf-1",
  name: "Signal and output",
  description: "An offline-safe example",
  version: "1.0",
  triggers: ["demo.started"],
  metadata: { owner: "integration-test" },
  nodes: [
    { id: "t", type: "trigger", label: "Start", x: 21, y: 34, config: {}, timeout_sec: 20, retry_count: 2, outputs: [{ id: "next", label: "Next" }] },
    { id: "o", type: "output", label: "Finish", x: 202, y: 98, config: { key: "result" }, timeout_sec: 30, retry_count: 3 },
  ],
  edges: [{ id: "edge-123", sourceId: "t", targetId: "o", sourcePort: "next" }],
};

describe("Digital Grid API contract", () => {
  it("encodes editor arrays as the Python ID-keyed graph and round-trips layout", () => {
    const payload = encodeWorkflow(graph);
    expect(Array.isArray(payload.nodes)).toBe(false);
    expect(payload.nodes.t.type).toBe("TRIGGER");
    expect(payload.nodes.o.type).toBe("OUTPUT");
    expect(payload.nodes.t.outputs).toEqual(["o"]);
    expect(payload.nodes.o.inputs).toEqual(["t"]);
    expect(payload.edges).toEqual([{ from: "t", to: "o", label: "default" }]);
    const loaded = decodeWorkflow(payload);
    expect(loaded.nodes).toEqual(graph.nodes);
    expect(loaded.edges).toEqual(graph.edges);
    expect(loaded.triggers).toEqual(["demo.started"]);
    expect(loaded.metadata?.owner).toBe("integration-test");
    expect(loaded.id).toBe("wf-1");
  });

  it("shows existing SKILL_CALL workflow nodes instead of hiding entire workflows", () => {
    const payload = encodeWorkflow({
      ...graph, nodes: [{ id: "skill", type: "skill_call", label: "Resolve skill", x: 10, y: 10, config: { skill: "demo" } }], edges: [],
    });
    expect(payload.nodes.skill.type).toBe("SKILL_CALL");
    expect(decodeWorkflow(payload).nodes[0].type).toBe("skill_call");
  });

  it("decodes a canonical list response", () => {
    expect(decodeWorkflowList([encodeWorkflow(graph)])).toHaveLength(1);
    expect(decodeWorkflowList([encodeWorkflow(graph)])[0].nodes[0].x).toBe(21);
  });

  it("rejects unsupported Delay/Notify steps, rather than silently treating them as executed", () => {
    for (const type of ["delay", "notify"] as const) {
      expect(() => encodeWorkflow({
        ...graph, nodes: [{ id: "x", type, label: type, x: 0, y: 0, config: {} }], edges: [],
      })).toThrow(/not supported/i);
    }
  });

  it("rejects missing edge endpoints and cyclic workflows before submission", () => {
    expect(() => encodeWorkflow({ ...graph, edges: [{ id: "bad", sourceId: "missing", targetId: "o" }] })).toThrow(/unknown/i);
    expect(() => encodeWorkflow({ ...graph, edges: [...graph.edges, { id: "back", sourceId: "o", targetId: "t" }] })).toThrow(/cycle/i);
  });

  it("rejects invalid or misleading workflow records", () => {
    expect(() => encodeWorkflow({ ...graph, name: "   " })).toThrow(/name/i);
    expect(() => decodeWorkflow({ nodes: [], name: "not backend schema" })).toThrow(/invalid/i);
    expect(() => decodeWorkflow({ name: "bad", nodes: { n: { id: "n", type: "UNKNOWN", config: {} } }, edges: [] })).toThrow(/unsupported/i);
  });

  it("normalises the actual monolith save, run, polling and cancel responses", () => {
    expect(decodeSaveResponse({ registered: "wf-1", name: "Signal and output" })).toEqual({ id: "wf-1" });
    const fromRun = decodeExecution({
      execution_id: "exec-1", workflow_id: "wf-1", status: "completed",
      outputs: { o: 42 }, node_statuses: { t: "completed", o: "completed" },
    });
    expect(fromRun.id).toBe("exec-1");
    expect(fromRun.outputs.o).toBe(42);
    expect(decodeCancellation({ cancelled: "exec-1" })).toEqual({ cancelled: true });
    expect(decodeCancellation({ cancelled: false })).toEqual({ cancelled: false });
  });

  it("does not invent a successful execution when the API omits status or execution ID", () => {
    expect(() => decodeExecution({ status: "completed" })).toThrow(/id/i);
    expect(() => decodeExecution({ execution_id: "e" })).toThrow(/status/i);
    expect(() => decodeSaveResponse({ name: "work" })).toThrow(/id/i);
  });
});
