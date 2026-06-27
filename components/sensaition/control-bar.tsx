"use client"

import { theme } from "@/lib/theme"
import type { Engine, RunMode } from "@/lib/types"
import { ghostButton, primaryButton } from "./ui"

export const RUN_MODE_META: Record<RunMode, { color: string; bg: string; label: string; icon: string; note: string }> = {
  auto: { color: theme.green, bg: `${theme.green}1A`, label: "Automatic", icon: "⟳", note: "Engine in full control" },
  semi_auto: {
    color: theme.amber,
    bg: `${theme.amber}1A`,
    label: "Semi-Auto Override",
    icon: "◐",
    note: "Auto logic running from your manual baseline",
  },
  full_manual: {
    color: theme.purple,
    bg: `${theme.purple}1A`,
    label: "Full Manual",
    icon: "✋",
    note: "Auto logic PAUSED — manual control only",
  },
  frozen: {
    color: theme.frost,
    bg: `${theme.frost}1A`,
    label: "Irrigation Frozen",
    icon: "❄",
    note: "Tap closed — logic & timers still running",
  },
}

interface ControlBarProps {
  engine: Engine
  day: number
  running: boolean
  logLength: number
  showLog: boolean
  fileActive: boolean
  fileName: string
  pendingChange: boolean
  onStart: () => void
  onToggleRun: () => void
  onToggleLog: () => void
  onExportLog: () => void
  onOverride: () => void
  onExitOverride: () => void
  onFreeze: () => void
  onUnfreeze: () => void
  onReset: () => void
}

export function ControlBar(props: ControlBarProps) {
  const {
    engine,
    day,
    running,
    logLength,
    showLog,
    fileActive,
    fileName,
    pendingChange,
    onStart,
    onToggleRun,
    onToggleLog,
    onExportLog,
    onOverride,
    onExitOverride,
    onFreeze,
    onUnfreeze,
    onReset,
  } = props
  const meta = RUN_MODE_META[engine.runMode]

  return (
    <>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          background: meta.bg,
          border: `1.5px solid ${meta.color}66`,
          borderRadius: 10,
          padding: "12px 18px",
        }}
      >
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: 9,
            background: `${meta.color}22`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 28.5,
            color: meta.color,
            flexShrink: 0,
          }}
        >
          {meta.icon}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 22.5, color: meta.color }}>
            {meta.label}
            {fileActive && (
              <span style={{ fontSize: 16.5, color: theme.blue, marginLeft: 10, fontWeight: 400 }}>
                · 📂 File mode — replaying {fileName}
              </span>
            )}
          </div>
          <div style={{ fontSize: 18, color: theme.sub, marginTop: 1 }}>{meta.note}</div>
        </div>
        {pendingChange && (
          <div
            style={{
              fontSize: 16.5,
              color: theme.amber,
              background: `${theme.amber}1A`,
              padding: "5px 10px",
              borderRadius: 6,
              border: `1px solid ${theme.amber}44`,
            }}
          >
            ⏱ Change staged — applies next midnight (Day {day + 1})
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {engine.stage === "awaiting" ? (
          <button onClick={onStart} style={primaryButton(theme.green, theme.bg)}>
            ▶ Start system
          </button>
        ) : (
          <>
            <button
              onClick={onToggleRun}
              style={primaryButton(running ? theme.raised : theme.green, running ? theme.chalk : theme.bg)}
            >
              {running ? "❚❚ Pause sim" : "▶ Run sim"}
            </button>
            <div style={{ flex: 1 }} />
            <button onClick={onToggleLog} style={{ ...ghostButton, color: logLength > 0 ? theme.chalk : theme.dim }}>
              📋 {showLog ? "Hide log" : "Show log"}
              {logLength > 0 && (
                <span style={{ marginLeft: 5, fontSize: 15, color: theme.sub }}>({Math.round(logLength / 7)} days)</span>
              )}
            </button>
            {logLength > 0 && (
              <button onClick={onExportLog} style={primaryButton(`${theme.green}22`, theme.green)}>
                📄 Export Log
              </button>
            )}
            {engine.overrideMode === "none" ? (
              <button onClick={onOverride} style={primaryButton(theme.purple, "#fff")}>
                ✋ Manual override
              </button>
            ) : (
              <button onClick={onExitOverride} style={primaryButton(theme.purple, "#fff")}>
                ↩ Exit override
              </button>
            )}
            {engine.frozen ? (
              <button onClick={onUnfreeze} style={primaryButton(theme.frost, theme.bg)}>
                ❄ Unfreeze
              </button>
            ) : (
              <button onClick={onFreeze} style={primaryButton(`${theme.frost}22`, theme.frost)}>
                ❄ Freeze irrigation
              </button>
            )}
            <button onClick={onReset} style={ghostButton}>
              ↺ Reset
            </button>
          </>
        )}
      </div>
    </>
  )
}
