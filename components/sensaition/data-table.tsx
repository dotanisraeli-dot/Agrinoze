"use client"

import { READINGS_PER_DAY, theme } from "@/lib/theme"
import type { TableRow } from "@/lib/types"
import { cardStyle, labelStyle } from "./ui"

const COLUMNS = ["Day", "Date", "Stage", "T20 avg (mb)", "T40 avg (mb)", "VWC avg (%)", "Pulses"]

interface DataTableProps {
  rows: TableRow[]
  fileActive: boolean
  fileName: string
}

export function DataTable({ rows, fileActive, fileName }: DataTableProps) {
  if (rows.length === 0) return null
  return (
    <div style={cardStyle}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 16px",
          borderBottom: `1px solid ${theme.border}`,
        }}
      >
        <div style={labelStyle}>
          Sensor daily averages{" "}
          {fileActive ? (
            <span style={{ color: theme.blue }}>· from file</span>
          ) : (
            <span style={{ color: theme.blue }}>· simulated</span>
          )}
        </div>
        <div style={{ fontSize: 15, color: theme.dim }}>
          {fileActive ? `From file: ${fileName}` : `Mean of ${READINGS_PER_DAY} readings/day (1 per 10 min) — PRD 19.6.26`}
        </div>
      </div>
      <div style={{ overflowX: "auto", maxHeight: 240, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 18 }}>
          <thead>
            <tr style={{ position: "sticky", top: 0, background: theme.raised }}>
              {COLUMNS.map((c) => (
                <th
                  key={c}
                  style={{
                    padding: "7px 12px",
                    textAlign: "left",
                    color: theme.sub,
                    fontWeight: 600,
                    fontSize: 15.8,
                    borderBottom: `1px solid ${theme.border}`,
                  }}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...rows].reverse().map((row, i) => (
              <tr key={row.day} style={{ background: i % 2 === 0 ? "transparent" : `${theme.border}44` }}>
                <td style={{ padding: "5px 12px", color: theme.sub }}>{row.day}</td>
                <td style={{ padding: "5px 12px", color: theme.dim, fontSize: 15.8 }}>{row.date || "—"}</td>
                <td style={{ padding: "5px 12px", color: theme.chalk }}>{row.stage}</td>
                <td style={{ padding: "5px 12px", color: theme.green, fontVariantNumeric: "tabular-nums" }}>
                  {row.t20.toFixed(2)}
                </td>
                <td style={{ padding: "5px 12px", color: theme.sub, fontVariantNumeric: "tabular-nums" }}>
                  {row.t40.toFixed(2)}
                </td>
                <td style={{ padding: "5px 12px", color: theme.blue, fontVariantNumeric: "tabular-nums" }}>
                  {row.vwc.toFixed(2)}
                </td>
                <td style={{ padding: "5px 12px", color: theme.chalk }}>{row.pulses}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
