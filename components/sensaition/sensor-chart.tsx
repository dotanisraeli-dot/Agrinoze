"use client"

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { theme } from "@/lib/theme"
import type { ChartPoint } from "@/lib/types"
import { cardStyle, ghostButton, labelStyle } from "./ui"

export type ChartView = "combined" | "t20" | "vwc"

interface SensorChartProps {
  data: ChartPoint[]
  view: ChartView
  has40cm: boolean
  fileActive: boolean
  speedIdx: number
  speedLabel: string
  onSpeedChange: (i: number) => void
  onStep: () => void
  stepDisabled: boolean
  canStep: boolean
  onViewChange: (v: ChartView) => void
}

const T20_COLOR = "#5BE89A"

export function SensorChart(props: SensorChartProps) {
  const { data, view, has40cm, fileActive, speedIdx, speedLabel, onSpeedChange, onStep, stepDisabled, canStep, onViewChange } =
    props

  return (
    <div style={cardStyle}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 16px",
          borderBottom: `1px solid ${theme.border}`,
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <div style={labelStyle}>
          Sensor history {fileActive && <span style={{ color: theme.blue }}>· from file</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 15, color: theme.dim, fontWeight: 600 }}>Speed</span>
          <input
            type="range"
            min={0}
            max={5}
            step={1}
            value={speedIdx}
            onChange={(e) => onSpeedChange(+e.target.value)}
            style={{ width: 100, accentColor: theme.green }}
          />
          <span
            style={{
              fontSize: 15,
              color: theme.sub,
              fontWeight: 700,
              minWidth: 28,
              textAlign: "center",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {speedLabel}
          </span>
          <span style={{ fontSize: 15, color: theme.dim, marginLeft: -4 }}>day</span>
          {canStep && (
            <button onClick={onStep} disabled={stepDisabled} style={{ ...ghostButton, padding: "4px 12px", fontSize: 15, marginLeft: 4 }}>
              Step 1 day
            </button>
          )}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {(
            [
              ["combined", "Combined"],
              ["t20", "T20 only"],
              ["vwc", "VWC only"],
            ] as [ChartView, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => onViewChange(key)}
              style={{
                padding: "4px 11px",
                borderRadius: 5,
                border: "none",
                cursor: "pointer",
                fontSize: 16.5,
                fontWeight: 600,
                background: view === key ? theme.borderLit : "transparent",
                color: view === key ? theme.chalk : theme.dim,
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: "12px 12px 6px", height: 250 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 16, left: 4, bottom: 18 }}>
            <CartesianGrid stroke={theme.border} vertical={false} />
            <XAxis
              dataKey="day"
              tick={{ fill: theme.dim, fontSize: 15 }}
              tickLine={false}
              axisLine={false}
              label={{ value: "Day (cycle)", position: "insideBottom", offset: -10, fill: theme.sub, fontSize: 16.5 }}
            />
            <YAxis
              yAxisId="mb"
              tick={{ fill: theme.dim, fontSize: 15 }}
              tickLine={false}
              axisLine={false}
              domain={[0, 90]}
              label={{
                value: view === "vwc" ? "VWC (%)" : "Tension (mb)",
                angle: -90,
                position: "insideLeft",
                offset: 14,
                fill: theme.sub,
                fontSize: 16.5,
                style: { textAnchor: "middle" },
              }}
            />
            {view === "combined" && (
              <YAxis
                yAxisId="pct"
                orientation="right"
                tick={{ fill: theme.dim, fontSize: 15 }}
                tickLine={false}
                axisLine={false}
                domain={[0, 70]}
                label={{
                  value: "VWC (%)",
                  angle: 90,
                  position: "insideRight",
                  offset: 14,
                  fill: theme.sub,
                  fontSize: 16.5,
                  style: { textAnchor: "middle" },
                }}
              />
            )}
            <Tooltip
              contentStyle={{ background: theme.bg, border: `1px solid ${theme.borderLit}`, borderRadius: 6, fontSize: 18 }}
              labelStyle={{ color: theme.sub }}
            />
            {(view === "combined" || view === "t20") && (
              <ReferenceLine yAxisId="mb" y={40} stroke={`${theme.amber}66`} strokeDasharray="4 3" />
            )}
            {(view === "combined" || view === "t20") && (
              <ReferenceLine yAxisId="mb" y={10} stroke={`${theme.red}66`} strokeDasharray="4 3" />
            )}
            {(view === "combined" || view === "t20") && (
              <Line
                yAxisId="mb"
                dataKey="t20"
                name="T20 (mb)"
                stroke={T20_COLOR}
                dot={false}
                strokeWidth={2.5}
                isAnimationActive={false}
                connectNulls
              />
            )}
            {(view === "combined" || view === "t20") && has40cm && (
              <Line
                yAxisId="mb"
                dataKey="t40"
                name="T40 (mb)"
                stroke={theme.sub}
                dot={false}
                strokeWidth={1.3}
                strokeDasharray="4 3"
                isAnimationActive={false}
                connectNulls
              />
            )}
            {(view === "combined" || view === "vwc") && (
              <Line
                yAxisId={view === "combined" ? "pct" : "mb"}
                dataKey="vwc"
                name="VWC (%)"
                stroke={theme.blue}
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
                connectNulls
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div
        style={{
          display: "flex",
          gap: 16,
          padding: "0 16px 12px",
          fontSize: 16.5,
          color: theme.sub,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 14, height: 3, background: T20_COLOR, borderRadius: 2 }} /> T20 (mb)
        </span>
        {has40cm && (
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 14, height: 2, background: theme.sub, borderRadius: 2 }} /> T40 (mb)
          </span>
        )}
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 14, height: 3, background: theme.blue, borderRadius: 2 }} /> VWC (%)
        </span>
        <span style={{ marginLeft: "auto", color: theme.dim }}>dashed lines: 40mb / 10mb thresholds</span>
      </div>
    </div>
  )
}
