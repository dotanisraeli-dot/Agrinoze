"use client"

import { theme } from "@/lib/theme"
import type { Alert, Engine } from "@/lib/types"
import { RUN_MODE_META } from "./control-bar"
import { cardStyle, labelStyle } from "./ui"

interface StatusPanelsProps {
  engine: Engine
  alerts: Alert[]
  onAck: () => void
}

export function StatusPanels({ engine, alerts, onAck }: StatusPanelsProps) {
  const meta = RUN_MODE_META[engine.runMode]

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
      <div style={{ ...cardStyle, padding: "14px 16px" }}>
        <div style={labelStyle}>Override snapshot & baseline</div>
        {engine.overrideMode === "none" && !engine.snapshot ? (
          <div style={{ fontSize: 19.5, color: theme.dim, marginTop: 10 }}>No override active.</div>
        ) : (
          <div style={{ marginTop: 10, fontSize: 19.5, display: "flex", flexDirection: "column", gap: 8 }}>
            {engine.snapshot && (
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: theme.sub }}>Saved auto snapshot</span>
                <span style={{ fontWeight: 600 }}>
                  {engine.snapshot.pulses} pulses · {engine.snapshot.sec}s · {engine.snapshot.stage}
                </span>
              </div>
            )}
            {engine.baseline && (
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: theme.sub }}>Manual baseline</span>
                <span style={{ fontWeight: 600, color: theme.purple }}>
                  {engine.baseline.pulses} pulses · {engine.baseline.sec}s
                </span>
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: theme.sub }}>Mode</span>
              <span style={{ fontWeight: 600, color: meta.color }}>{meta.label}</span>
            </div>
          </div>
        )}
      </div>

      <div style={{ ...cardStyle, padding: "14px 16px", maxHeight: 220, overflow: "auto" }}>
        <div style={labelStyle}>Alert log</div>
        {alerts.length === 0 ? (
          <div style={{ fontSize: 19.5, color: theme.dim, marginTop: 10 }}>No alerts. System nominal.</div>
        ) : (
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 0 }}>
            {alerts.map((a) => (
              <div
                key={a.id}
                style={{
                  display: "flex",
                  gap: 9,
                  padding: "8px 0",
                  borderBottom: `1px solid ${theme.border}`,
                  alignItems: "flex-start",
                }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    marginTop: 5,
                    flexShrink: 0,
                    background: a.level === "red" ? theme.red : theme.amber,
                  }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 18.8, lineHeight: 1.4 }}>{a.msg}</div>
                  <div style={{ fontSize: 15, color: theme.dim, marginTop: 2 }}>
                    Day {a.day} · {a.level === "red" ? "Action required" : "Monitor"}
                  </div>
                </div>
                {a.msg.includes("40cm") && engine.t40Active && !engine.t40Acked && (
                  <button
                    onClick={onAck}
                    style={{
                      fontSize: 15,
                      padding: "3px 8px",
                      borderRadius: 5,
                      border: `1px solid ${theme.border}`,
                      background: theme.raised,
                      color: theme.sub,
                      cursor: "pointer",
                      flexShrink: 0,
                    }}
                  >
                    Ack
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
