"use client"

import { theme } from "@/lib/theme"
import { cardStyle, ghostButton, labelStyle, primaryButton } from "./ui"

function lineColor(line: string): string {
  if (line.startsWith("=")) return theme.dim
  if (line.startsWith("DAY")) return theme.chalk
  if (line.includes("TRANSITION") || line.startsWith("✓")) return theme.green
  if (line.includes("ALERT")) return theme.red
  if (line.includes("Decision:")) return theme.amber
  if (line.includes("---")) return theme.borderLit
  return theme.sub
}

interface DecisionLogProps {
  log: string[]
  onExport: () => void
  onClear: () => void
}

export function DecisionLog({ log, onExport, onClear }: DecisionLogProps) {
  return (
    <div style={cardStyle}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 16px",
          borderBottom: `1px solid ${theme.border}`,
        }}
      >
        <div style={labelStyle}>Algorithm Decision Log</div>
        <div style={{ display: "flex", gap: 8 }}>
          {log.length > 0 && (
            <button onClick={onExport} style={{ ...primaryButton(`${theme.green}22`, theme.green), padding: "5px 12px", fontSize: 16.5 }}>
              📄 Export as .txt
            </button>
          )}
          <button onClick={onClear} style={{ ...ghostButton, padding: "5px 12px", fontSize: 16.5 }}>
            Clear
          </button>
        </div>
      </div>
      <div
        style={{
          fontFamily: "'JetBrains Mono','Fira Code','Consolas',monospace",
          fontSize: 16.5,
          lineHeight: 1.6,
          padding: "10px 16px",
          maxHeight: 320,
          overflowY: "auto",
          whiteSpace: "pre-wrap",
          color: theme.sub,
        }}
      >
        {log.length === 0 ? (
          <span style={{ color: theme.dim }}>No log entries yet. Start the simulation and run a few days.</span>
        ) : (
          log.slice(-200).map((line, i) => (
            <div key={i} style={{ color: lineColor(line) }}>
              {line || " "}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
