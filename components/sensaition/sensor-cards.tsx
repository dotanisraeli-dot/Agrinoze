"use client"

import { theme } from "@/lib/theme"
import { cardStyle, labelStyle } from "./ui"

// Status colour/label for a sensor reading given thresholds.
function status(
  value: number,
  min: number,
  highWarn: number | null,
  optLow: number | null,
  optHigh: number | null,
): { c: string; t: string } {
  if (value < min) return { c: theme.red, t: "Too low" }
  if (highWarn != null && value > highWarn) return { c: theme.amber, t: "High" }
  if (optLow != null && optHigh != null && value >= optLow && value <= optHigh) return { c: theme.green, t: "Optimal" }
  return { c: theme.amber, t: "Watch" }
}

interface SensorCardsProps {
  t20: number
  t40: number
  vwc: number
  has40cm: boolean
  vwcRange: [number, number]
  fileActive: boolean
}

function FileTag({ active }: { active: boolean }) {
  return active ? <span style={{ color: theme.blue }}>· file</span> : null
}

export function SensorCards({ t20, t40, vwc, has40cm, vwcRange, fileActive }: SensorCardsProps) {
  const t20s = status(t20, 1, null, has40cm ? 20 : 10, has40cm ? 40 : 20)
  const vwcs = status(vwc, 0, null, vwcRange[0], vwcRange[1])

  return (
    <div style={{ display: "grid", gridTemplateColumns: has40cm ? "1fr 1fr 1fr" : "1fr 1fr", gap: 12 }}>
      <div style={{ ...cardStyle, padding: "14px 16px" }}>
        <div style={labelStyle}>
          Tensiometer 20cm <FileTag active={fileActive} />
        </div>
        <div style={{ marginTop: 6 }}>
          <span style={{ fontSize: 48, fontWeight: 800, color: t20s.c, fontVariantNumeric: "tabular-nums" }}>
            {t20.toFixed(1)}
          </span>
          <span style={{ fontSize: 19.5, color: theme.sub, marginLeft: 4 }}>mb daily avg</span>
        </div>
        <div style={{ fontSize: 16.5, color: t20s.c, marginTop: 4 }}>{t20s.t} · controls irrigation</div>
      </div>

      {has40cm && (
        <div style={{ ...cardStyle, padding: "14px 16px" }}>
          <div style={labelStyle}>
            Tensiometer 40cm <FileTag active={fileActive} />
          </div>
          <div style={{ marginTop: 6 }}>
            <span
              style={{
                fontSize: 48,
                fontWeight: 800,
                color: t40 < 10 ? theme.red : theme.amber,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {t40.toFixed(1)}
            </span>
            <span style={{ fontSize: 19.5, color: theme.sub, marginLeft: 4 }}>mb daily avg</span>
          </div>
          <div style={{ fontSize: 16.5, color: t40 < 10 ? theme.red : theme.sub, marginTop: 4 }}>
            {t40 < 10 ? "Below 10mb — alert" : "Depth monitor"}
          </div>
        </div>
      )}

      <div style={{ ...cardStyle, padding: "14px 16px" }}>
        <div style={labelStyle}>
          VWC <FileTag active={fileActive} />
        </div>
        <div style={{ marginTop: 6 }}>
          <span style={{ fontSize: 48, fontWeight: 800, color: vwcs.c, fontVariantNumeric: "tabular-nums" }}>
            {vwc.toFixed(1)}
          </span>
          <span style={{ fontSize: 19.5, color: theme.sub, marginLeft: 4 }}>%</span>
        </div>
        <div style={{ fontSize: 16.5, color: vwcs.c, marginTop: 4 }}>
          Optimal {vwcRange[0]}–{vwcRange[1]}%
        </div>
      </div>
    </div>
  )
}
