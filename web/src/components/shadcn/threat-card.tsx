"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Badge } from "./badge";
import { Card, CardContent, CardHeader, CardTitle } from "./card";

export type ThreatSeverity = "critical" | "high" | "medium" | "low" | "info" | "unknown";
export type ScanStatus = "pending" | "running" | "completed" | "failed";

export interface ThreatCardProps {
  scanId: string;
  scanType: string;
  target: string;
  status: ScanStatus;
  engineUsed?: string;
  threatFound: boolean;
  severity: ThreatSeverity;
  findings?: Array<{ [key: string]: unknown }>;
  startedAt?: string;
  completedAt?: string;
  variant?: "default" | "glass";
  className?: string;
}

const SEVERITY_CONFIG: Record<ThreatSeverity, { label: string; class: string }> = {
  critical: { label: "CRITICAL", class: "bg-red-600 text-white" },
  high: { label: "HIGH", class: "bg-orange-500 text-white" },
  medium: { label: "MEDIUM", class: "bg-yellow-500 text-black" },
  low: { label: "LOW", class: "bg-blue-500 text-white" },
  info: { label: "INFO", class: "bg-gray-500 text-white" },
  unknown: { label: "UNKNOWN", class: "bg-gray-400 text-white" },
};

const STATUS_CONFIG: Record<ScanStatus, { label: string; class: string }> = {
  pending: { label: "Pending", class: "bg-gray-200 text-gray-700" },
  running: { label: "Running", class: "bg-blue-100 text-blue-700 animate-pulse" },
  completed: { label: "Completed", class: "bg-green-100 text-green-700" },
  failed: { label: "Failed", class: "bg-red-100 text-red-700" },
};

const ENGINE_ICONS: Record<string, string> = {
  internal: "🗄️",
  wazuh: "🛡️",
  misp: "🔍",
  openvas: "🔬",
  clamav: "🦠",
  yara: "📋",
  suricata: "🌊",
  semgrep: "🔎",
  offline: "📴",
};

export function ThreatCard({
  scanId,
  scanType,
  target,
  status,
  engineUsed,
  threatFound,
  severity,
  findings = [],
  startedAt,
  completedAt,
  variant = "default",
  className,
}: ThreatCardProps) {
  const sev = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.unknown;
  const stat = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;

  return (
    <Card
      className={cn(
        "relative overflow-hidden transition-all",
        variant === "glass" && "backdrop-blur-sm bg-white/10 border-white/20",
        threatFound && "border-l-4",
        threatFound && severity === "critical" && "border-l-red-600",
        threatFound && severity === "high" && "border-l-orange-500",
        threatFound && severity === "medium" && "border-l-yellow-500",
        threatFound && severity === "low" && "border-l-blue-500",
        className,
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm font-mono truncate">{target}</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              {scanType} · {scanId.slice(0, 8)}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <Badge className={cn("text-xs px-1.5", stat.class)}>{stat.label}</Badge>
            {threatFound && (
              <Badge className={cn("text-xs px-1.5", sev.class)}>{sev.label}</Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0 space-y-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {engineUsed && (
            <span>
              {ENGINE_ICONS[engineUsed] ?? "⚙️"} {engineUsed}
            </span>
          )}
          {threatFound ? (
            <span className="font-semibold text-red-600">⚠ Threat detected</span>
          ) : (
            status === "completed" && (
              <span className="font-semibold text-green-600">✓ Clean</span>
            )
          )}
        </div>

        {findings.length > 0 && (
          <div className="space-y-1">
            {findings.slice(0, 3).map((f, i) => (
              <div key={i} className="text-xs bg-muted rounded px-2 py-1 font-mono truncate">
                {JSON.stringify(f).slice(0, 120)}
              </div>
            ))}
            {findings.length > 3 && (
              <p className="text-xs text-muted-foreground">+{findings.length - 3} more findings</p>
            )}
          </div>
        )}

        {(startedAt || completedAt) && (
          <p className="text-xs text-muted-foreground">
            {completedAt
              ? `Completed ${new Date(completedAt).toLocaleTimeString()}`
              : startedAt
              ? `Started ${new Date(startedAt).toLocaleTimeString()}`
              : ""}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
