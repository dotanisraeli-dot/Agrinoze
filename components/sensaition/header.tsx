"use client"

import type { ChangeEvent } from "react"
import { theme, type SoilType } from "@/lib/theme"

interface HeaderProps {
  day: number
  soilType: SoilType
  onSoilChange: (s: SoilType) => void
  fileActive: boolean
  fileName: string
  fileCursor: number
  fileTotal: number
  onLoadFile: (e: ChangeEvent<HTMLInputElement>) => void
  onClearFile: () => void
}

export function Header({
  day,
  soilType,
  onSoilChange,
  fileActive,
  fileName,
  fileCursor,
  fileTotal,
  onLoadFile,
  onClearFile,
}: HeaderProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 20px",
        borderBottom: `1px solid ${theme.border}`,
        flexWrap: "wrap",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <img
          src="/sensaition-logo.jpg"
          alt="SensAItion — smart sensed irrigation"
          style={{ height: 108, borderRadius: 6, background: "#fff", padding: "3px 6px", objectFit: "contain" }}
        />
        <div>
          <div style={{ fontSize: 30, color: theme.chalk, marginTop: 1 }}>
            Agronomist Simulator{" "}
            <span style={{ fontSize: 24, color: theme.sub, marginLeft: 6 }}>v2.1</span>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 18, color: theme.sub, flexWrap: "wrap" }}>
        <span>
          Day{" "}
          <strong style={{ color: theme.chalk, fontVariantNumeric: "tabular-nums" }}>{day}</strong>
        </span>

        {fileActive && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: `${theme.blue}22`,
              border: `1px solid ${theme.blue}55`,
              borderRadius: 6,
              padding: "4px 10px",
              fontSize: 16.5,
            }}
          >
            <span style={{ color: theme.blue }}>📂</span>
            <span style={{ color: theme.blue, fontWeight: 600 }}>{fileName}</span>
            <span style={{ color: theme.dim }}>
              ({fileCursor}/{fileTotal} days)
            </span>
            <button
              onClick={onClearFile}
              style={{ background: "none", border: "none", color: theme.dim, cursor: "pointer", fontSize: 18, padding: 0, marginLeft: 2 }}
            >
              ✕
            </button>
          </div>
        )}

        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            background: theme.raised,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
            padding: "5px 10px",
            fontSize: 16.5,
            cursor: "pointer",
            color: theme.sub,
            fontWeight: 600,
          }}
        >
          <span>📥 Load data file</span>
          <input type="file" accept=".csv,.txt" onChange={onLoadFile} style={{ display: "none" }} />
        </label>

        <select
          value={soilType}
          onChange={(e) => onSoilChange(e.target.value as SoilType)}
          style={{
            background: theme.raised,
            color: theme.chalk,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
            padding: "5px 8px",
            fontSize: 18,
          }}
        >
          <option value="medium">Medium soil</option>
          <option value="heavy">Heavy soil</option>
          <option value="sandy">Sandy soil</option>
          <option value="soilless">Soilless</option>
        </select>
      </div>
    </div>
  )
}
