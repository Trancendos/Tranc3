import React from "react";
import { NODE_META, type NodeType } from "./types";
import { isSupportedNodeType } from "./gridContract";

interface Props {
  onDragStart: (type: NodeType) => void;
}

const PALETTE_GROUPS: { label: string; types: NodeType[] }[] = [
  { label: "Control", types: ["trigger", "condition", "loop", "parallel", "merge"] },
  { label: "AI / ML", types: ["llm", "ml_predict", "vector_search", "spark_tool"] },
  { label: "Data", types: ["transform", "http", "code"] },
  { label: "Output", types: ["output", "notify", "delay"] },
];

export default function NodePalette({ onDragStart }: Props) {
  return (
    <aside className="w-52 bg-gray-900 border-r border-gray-700 overflow-y-auto flex-shrink-0">
      <div className="p-3 border-b border-gray-700">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Node Palette</p>
      </div>
      {PALETTE_GROUPS.map((g) => (
        <div key={g.label} className="p-2">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1 px-1">{g.label}</p>
          {g.types.map((type) => {
            const m = NODE_META[type];
            const supported = isSupportedNodeType(type);
            return (
              <div
                key={type}
                draggable={supported}
                aria-disabled={!supported}
                onDragStart={supported ? () => onDragStart(type) : undefined}
                className={`flex items-center gap-2 px-2 py-1.5 mb-1 rounded select-none ${supported ? "cursor-grab active:cursor-grabbing hover:bg-gray-700" : "cursor-not-allowed opacity-40"}`}
                title={supported ? m.description : `${m.label} is not supported by the current workflow engine`}
              >
                <span
                  className="w-6 h-6 rounded flex items-center justify-center text-xs font-bold flex-shrink-0"
                  style={{ backgroundColor: m.color + "33", color: m.color }}
                >
                  {m.icon}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-gray-200 font-medium truncate">{m.label}{!supported && " (unavailable)"}</p>
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </aside>
  );
}
