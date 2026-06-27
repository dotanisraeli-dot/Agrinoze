import type { SensorReading } from "./types"

// Parses uploaded CSV/TXT sensor data in two supported shapes:
//   Wide:  date,T20,T40,VWC      (one row per day)
//   Tall:  date,sensor,value     (one row per sensor/day)
export function parseCsv(text: string): SensorReading[] {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
  if (lines.length === 0) return []

  // Detect delimiter from the header row.
  const delim = lines[0].includes("\t") ? "\t" : lines[0].includes(";") ? ";" : ","

  // Drop the header row if it contains non-numeric, non-date labels.
  const headerCells = lines[0].split(delim).map((c) => c.trim().toLowerCase())
  const hasHeader = headerCells.some((c) => isNaN(Number(c)) && !/^\d{4}/.test(c) && c !== "")
  const rows = hasHeader ? lines.slice(1) : lines

  const sensorKeys = ["t20", "t40", "vwc"] as const
  const firstCells = rows[0]?.split(delim).map((c) => c.trim()) ?? []
  const isTall = firstCells.length === 3 && sensorKeys.includes(firstCells[1].toLowerCase() as never)
  const isWide = firstCells.length >= 4

  if (isTall) {
    const byDate: Record<string, { date: string; t20: number | null; t40: number | null; vwc: number | null }> = {}
    for (const row of rows) {
      const [date, sensor, value] = row.split(delim).map((c) => c.trim())
      if (!date || !sensor || !value) continue
      const num = parseFloat(value)
      if (isNaN(num)) continue
      byDate[date] ||= { date, t20: null, t40: null, vwc: null }
      const key = sensor.toLowerCase() as (typeof sensorKeys)[number]
      if (sensorKeys.includes(key)) byDate[date][key] = num
    }
    return Object.values(byDate)
      .filter((d) => d.t20 !== null && d.t40 !== null && d.vwc !== null)
      .map((d) => ({ date: d.date, t20: d.t20 as number, t40: d.t40 as number, vwc: d.vwc as number }))
      .sort((a, b) => a.date!.localeCompare(b.date!))
  }

  if (isWide) {
    const out: SensorReading[] = []
    for (const row of rows) {
      const [date, a, b, c] = row.split(delim).map((g) => g.trim())
      if (!date) continue
      const t20 = parseFloat(a)
      const t40 = parseFloat(b)
      const vwc = parseFloat(c)
      if (isNaN(t20) || isNaN(t40) || isNaN(vwc)) continue
      out.push({ date, t20, t40, vwc })
    }
    return out.sort((a, b) => a.date!.localeCompare(b.date!))
  }

  return []
}
