"use client"

import { STAGE_INDEX, STAGE_LABELS, theme } from "@/lib/theme"
import { describeProgram } from "@/lib/engine"
import type { Engine } from "@/lib/types"
import { cardStyle } from "./ui"

export function StageStepper({ engine, day }: { engine: Engine; day: number }) {
  const current = STAGE_INDEX[engine.stage]

  return (
    <div style={{ ...cardStyle, padding: "14px 18px" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {STAGE_LABELS.map((label, i) => {
          const done = i < current
          const active = i === current
          return (
            <div
              key={label}
              style={{ display: "flex", alignItems: "center", flex: i < STAGE_LABELS.length - 1 ? 1 : "none" }}
            >
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 16.5,
                    fontWeight: 700,
                    flexShrink: 0,
                    background: done ? theme.greenDim : active ? theme.green : theme.raised,
                    color: done ? theme.green : active ? theme.bg : theme.dim,
                    border: active ? `2px solid ${theme.green}` : "none",
                    boxShadow: active ? `0 0 12px ${theme.green}55` : "none",
                  }}
                >
                  {done ? "✓" : i}
                </div>
                <div
                  style={{
                    fontSize: 15,
                    color: active ? theme.chalk : theme.dim,
                    fontWeight: active ? 700 : 400,
                    whiteSpace: "nowrap",
                  }}
                >
                  {label}
                </div>
              </div>
              {i < STAGE_LABELS.length - 1 && (
                <div
                  style={{
                    flex: 1,
                    height: 2,
                    margin: "0 4px",
                    marginBottom: 18,
                    background: done ? theme.greenDim : theme.border,
                  }}
                />
              )}
            </div>
          )
        })}
      </div>

      {engine.stage !== "awaiting" && (
        <div style={{ marginTop: 12, fontSize: 18, color: theme.sub, display: "flex", gap: 20, flexWrap: "wrap" }}>
          <span>
            Day in stage:{" "}
            <strong style={{ color: theme.chalk }}>{day - engine.stageEnteredDay}</strong>
          </span>
          <span>
            Active program: <strong style={{ color: theme.chalk }}>{describeProgram(engine.program)}</strong>
          </span>
          {engine.frozen && (
            <span style={{ color: theme.frost }}>
              Delivering: <strong>0 pulses (frozen)</strong>
            </span>
          )}
        </div>
      )}
    </div>
  )
}
