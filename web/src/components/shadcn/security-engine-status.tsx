"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "./card";

export interface SecurityEngine {
  engine: string;
  healthy: boolean;
  pheromone: number;
  requests_in_window: number;
  threshold: number;
  blocked: boolean;
}

interface SecurityEngineStatusProps {
  engines: SecurityEngine[];
  variant?: "default" | "glass";
  className?: string;
}

const ENGINE_META: Record<
  string,
  { label: string; icon: string; tier: number; entity: string }
> = {
  internal: { label: "Internal IOC DB", icon: "🗄️", tier: 0, entity: "Cryptex" },
  wazuh: { label: "Wazuh SIEM/EDR", icon: "🛡️", tier: 1, entity: "Cryptex" },
  misp: { label: "MISP Threat Intel", icon: "🔍", tier: 2, entity: "Cryptex" },
  openvas: { label: "OpenVAS/Greenbone", icon: "🔬", tier: 3, entity: "Cryptex" },
  clamav: { label: "ClamAV AV", icon: "🦠", tier: 4, entity: "The Ice Box" },
  yara: { label: "YARA Rules", icon: "📋", tier: 5, entity: "The Ice Box" },
  suricata: { label: "Suricata IDS", icon: "🌊", tier: 6, entity: "Cryptex" },
  semgrep: { label: "Semgrep SAST", icon: "🔎", tier: 7, entity: "Cryptex" },
  offline: { label: "Offline Stub", icon: "📴", tier: 8, entity: "—" },
};

function PheromoneBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.7 ? "bg-green-500" : value >= 0.4 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}

function ThresholdBar({
  current,
  max,
  blocked,
}: {
  current: number;
  max: number;
  blocked: boolean;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((current / max) * 100)) : 0;
  const color = blocked ? "bg-red-500" : pct >= 80 ? "bg-yellow-500" : "bg-blue-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums w-12 text-right">
        {current}/{max}
      </span>
    </div>
  );
}

export function SecurityEngineStatus({
  engines,
  variant = "default",
  className,
}: SecurityEngineStatusProps) {
  return (
    <Card
      className={cn(
        "overflow-hidden",
        variant === "glass" && "backdrop-blur-sm bg-white/10 border-white/20",
        className,
      )}
    >
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          🔐 Security Engine Status — Cryptex + The Ice Box
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-3">
          {engines.map((eng) => {
            const meta = ENGINE_META[eng.engine] ?? {
              label: eng.engine,
              icon: "⚙️",
              tier: 9,
              entity: "—",
            };
            return (
              <div key={eng.engine} className="space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm">{meta.icon}</span>
                    <span className="text-xs font-medium">{meta.label}</span>
                    <span className="text-xs text-muted-foreground">T{meta.tier}</span>
                    <span className="text-xs text-muted-foreground">· {meta.entity}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {eng.blocked && (
                      <span className="text-xs text-red-600 font-semibold">BLOCKED</span>
                    )}
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full",
                        eng.healthy ? "bg-green-500" : "bg-red-500",
                      )}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                  <div>
                    <p className="text-xs text-muted-foreground">pheromone</p>
                    <PheromoneBar value={eng.pheromone} />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">threshold</p>
                    <ThresholdBar
                      current={eng.requests_in_window}
                      max={eng.threshold}
                      blocked={eng.blocked}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
