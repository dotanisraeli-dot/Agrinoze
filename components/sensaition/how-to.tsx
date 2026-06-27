"use client"

import { theme } from "@/lib/theme"
import { cardStyle, labelStyle } from "./ui"

export function HowTo({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div style={{ ...cardStyle, borderColor: `${theme.green}44` }}>
      <button
        onClick={onToggle}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "13px 18px",
          color: theme.chalk,
          textAlign: "left",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 9, fontWeight: 700, fontSize: 21 }}>
          <span style={{ color: theme.green }}>📋</span> How to test this simulator
        </span>
        <span style={{ color: theme.sub, fontSize: 19.5 }}>{open ? "Hide ▲" : "Show ▼"}</span>
      </button>

      {open && (
        <div style={{ padding: "0 18px 18px", fontSize: 19.5, color: theme.sub, lineHeight: 1.65 }}>
          <p style={{ margin: "0 0 12px" }}>
            This runs the <strong style={{ color: theme.chalk }}>real SensAItion irrigation engine</strong> — every
            stage transition, threshold, alert, and the manual-override logic — either against a simulated field or
            against <strong style={{ color: theme.chalk }}>your own sensor data</strong> (upload a CSV/TXT file).
          </p>

          <div style={{ ...labelStyle, color: theme.blue, marginBottom: 6 }}>Loading real or synthetic sensor data</div>
          <p
            style={{
              margin: "0 0 12px",
              padding: "10px 12px",
              background: `${theme.blue}12`,
              border: `1px solid ${theme.blue}33`,
              borderRadius: 7,
              color: theme.chalk,
            }}
          >
            Click <strong>📥 Load data file</strong> (top right). Supported formats:
            <br />
            <code style={{ color: theme.green, fontSize: 16.5 }}>Wide: date,T20,T40,VWC</code> (one row per day, e.g.
            2026-01-01,45.2,38.1,32.5)
            <br />
            <code style={{ color: theme.green, fontSize: 16.5 }}>Tall: date,sensor,value</code> (e.g. 2026-01-01,T20,45.2
            — one row per sensor/day)
          </p>

          <div style={{ ...labelStyle, color: theme.green, marginBottom: 6 }}>Getting started (simulation mode)</div>
          <ol style={{ margin: "0 0 18px", paddingLeft: 20 }}>
            <li>
              Pick a soil type · Press <strong style={{ color: theme.chalk }}>Start system</strong> · Confirm · Press{" "}
              <strong style={{ color: theme.chalk }}>Run sim</strong>
            </li>
            <li>
              Use the speed slider or <strong style={{ color: theme.chalk }}>Step 1 day</strong> to inspect one cycle at a
              time
            </li>
            <li>
              Press <strong style={{ color: theme.chalk }}>📄 Export Log</strong> to download a full narrative of every
              algorithm decision
            </li>
          </ol>

          <div
            style={{
              fontSize: 16.5,
              color: theme.dim,
              padding: "10px 12px",
              background: `${theme.amber}0A`,
              border: `1px solid ${theme.amber}33`,
              borderRadius: 7,
              lineHeight: 1.6,
            }}
          >
            <strong style={{ color: theme.amber }}>⚠ Demonstration soil model</strong>
            <br />
            The simulated field uses a simplified physics model (Agrinoze PRD 19.6.26) for illustration only. Real soil
            behaves differently based on texture, compaction, climate, and field history. Always validate the engine
            against <strong>your actual field data</strong> before deployment.
          </div>
        </div>
      )}
    </div>
  )
}
