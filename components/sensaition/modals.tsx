"use client"

import { theme, type SoilType } from "@/lib/theme"
import { describeProgram } from "@/lib/engine"
import type { Engine, OverrideMode } from "@/lib/types"
import { ghostButton, labelStyle, Modal, primaryButton } from "./ui"

export function StartModal({
  soilType,
  fileActive,
  fileTotal,
  fileName,
  onCancel,
  onConfirm,
}: {
  soilType: SoilType
  fileActive: boolean
  fileTotal: number
  fileName: string
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <Modal onClose={onCancel}>
      <h3 style={{ fontSize: 24, fontWeight: 700, margin: "0 0 8px" }}>Start irrigation system?</h3>
      <p style={{ fontSize: 19.5, color: theme.sub, lineHeight: 1.6, margin: "0 0 18px" }}>
        This confirms the initial setup ({soilType} soil) and begins Calibration Sub-Stage 1: 200 pulses × 2 min per day.
        {fileActive && (
          <>
            <br />
            <strong style={{ color: theme.blue }}>📂 File mode:</strong> Algorithm will run over {fileTotal} days from{" "}
            {fileName}.
          </>
        )}
      </p>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onCancel} style={ghostButton}>
          Cancel
        </button>
        <button onClick={onConfirm} style={primaryButton(theme.green, theme.bg)}>
          Confirm & start
        </button>
      </div>
    </Modal>
  )
}

export function FreezeModal({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  return (
    <Modal onClose={onCancel}>
      <h3 style={{ fontSize: 24, fontWeight: 700, margin: "0 0 8px", color: theme.frost }}>❄ Freeze irrigation?</h3>
      <p style={{ fontSize: 19.5, color: theme.sub, lineHeight: 1.6, margin: "0 0 18px" }}>
        Closes the tap — zero water delivered. Logic and timers keep running. Water resumes only on unfreeze.
      </p>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onCancel} style={ghostButton}>
          Cancel
        </button>
        <button onClick={onConfirm} style={primaryButton(theme.frost, theme.bg)}>
          Confirm freeze
        </button>
      </div>
    </Modal>
  )
}

export function OverrideModal({
  mode,
  setMode,
  pulses,
  setPulses,
  sec,
  setSec,
  onCancel,
  onExecute,
}: {
  mode: OverrideMode
  setMode: (m: OverrideMode) => void
  pulses: number
  setPulses: (n: number) => void
  sec: number
  setSec: (n: number) => void
  onCancel: () => void
  onExecute: () => void
}) {
  const options: [OverrideMode, string, string][] = [
    ["semi_auto", "Semi-Auto", "Auto logic continues from your manual baseline as the fixed anchor."],
    ["full_manual", "Full Manual", "Auto logic fully paused. Manual continuous program only."],
  ]
  return (
    <Modal onClose={onCancel} wide>
      <h3 style={{ fontSize: 24, fontWeight: 700, margin: "0 0 4px", color: theme.purple }}>Manual override</h3>
      <p style={{ fontSize: 18, color: theme.sub, margin: "0 0 16px" }}>
        System saves a snapshot first, then stages your values. Takes effect at the next midnight cycle.
      </p>

      <div style={{ ...labelStyle, marginBottom: 8 }}>Override mode</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 18 }}>
        {options.map(([key, title, desc]) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            style={{
              textAlign: "left",
              padding: "12px 14px",
              borderRadius: 8,
              cursor: "pointer",
              background: mode === key ? `${theme.purple}1A` : theme.raised,
              border: `1.5px solid ${mode === key ? theme.purple : theme.border}`,
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 19.5, color: mode === key ? theme.purple : theme.chalk }}>{title}</div>
            <div style={{ fontSize: 17.2, color: theme.sub, marginTop: 4, lineHeight: 1.45 }}>{desc}</div>
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 8 }}>
        <div>
          <div style={{ ...labelStyle, marginBottom: 6 }}>Pulses / day</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input type="range" min={0} max={200} step={10} value={pulses} onChange={(e) => setPulses(+e.target.value)} style={{ flex: 1 }} />
            <span style={{ fontSize: 30, fontWeight: 800, minWidth: 38, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
              {pulses}
            </span>
          </div>
        </div>
        <div>
          <div style={{ ...labelStyle, marginBottom: 6 }}>Pulse duration (sec)</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input type="range" min={10} max={180} step={10} value={sec} onChange={(e) => setSec(+e.target.value)} style={{ flex: 1 }} />
            <span style={{ fontSize: 30, fontWeight: 800, minWidth: 38, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
              {sec}
            </span>
          </div>
        </div>
      </div>

      <div style={{ fontSize: 18, color: theme.sub, marginBottom: 18 }}>
        Staged: <strong style={{ color: theme.chalk }}>{describeProgram({ pulses, sec })}</strong>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onCancel} style={ghostButton}>
          Cancel
        </button>
        <button onClick={onExecute} style={primaryButton(theme.purple, "#fff")}>
          Execute (saves snapshot)
        </button>
      </div>
    </Modal>
  )
}

export function ExitOverrideModal({
  engine,
  onCancel,
  onChoose,
}: {
  engine: Engine
  onCancel: () => void
  onChoose: (choice: "resume_last_auto" | "resume_modified_auto") => void
}) {
  const snapNote = engine.snapshot
    ? ` (${engine.snapshot.pulses} pulses · ${engine.snapshot.sec}s · ${engine.snapshot.stage})`
    : ""
  const baseNote = engine.baseline ? ` (${engine.baseline.pulses} pulses · ${engine.baseline.sec}s)` : ""
  const options: [("resume_last_auto" | "resume_modified_auto"), string, string][] = [
    ["resume_last_auto", "Resume last auto", `Restore the pre-override snapshot${snapNote} and continue.`],
    ["resume_modified_auto", "Resume modified-auto", `Keep your manual values${baseNote} as the new auto baseline.`],
  ]
  return (
    <Modal onClose={onCancel} wide>
      <h3 style={{ fontSize: 24, fontWeight: 700, margin: "0 0 4px", color: theme.purple }}>Exit manual override</h3>
      <p style={{ fontSize: 18, color: theme.sub, margin: "0 0 16px" }}>
        Choose how to hand control back. Takes effect at the next midnight cycle.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 18 }}>
        {options.map(([key, title, desc]) => (
          <button
            key={key}
            onClick={() => onChoose(key)}
            style={{
              textAlign: "left",
              padding: "14px 16px",
              borderRadius: 8,
              cursor: "pointer",
              background: theme.raised,
              border: `1px solid ${theme.border}`,
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 20.2, color: theme.purple }}>{title}</div>
            <div style={{ fontSize: 18, color: theme.sub, marginTop: 4, lineHeight: 1.5 }}>{desc}</div>
          </button>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button onClick={onCancel} style={ghostButton}>
          Cancel
        </button>
      </div>
    </Modal>
  )
}
