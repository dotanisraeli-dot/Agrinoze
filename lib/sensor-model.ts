// Simplified soil-physics model used to synthesize a virtual field.
// (Demonstration model — Agrinoze PRD 19.6.26)

import { READINGS_PER_DAY, TEMP_NOISE_SD, VWC_NOISE_SD, type SoilType } from "./theme"
import type { Program, SensorModel, SensorReading } from "./types"

const SOIL_PROFILES: Record<SoilType, Omit<SensorModel, "soilType" | "curT" | "curVwc">> = {
  heavy: { A: 88, b: 1.55, k: 0.3, vwcDry: 14, vwcWet: 60, tFloor: 3, t0: 72, vwc0: 24 },
  medium: { A: 82, b: 1.59, k: 0.33, vwcDry: 16, vwcWet: 54, tFloor: 2, t0: 66, vwc0: 26 },
  sandy: { A: 84, b: 1.6, k: 0.4, vwcDry: 11, vwcWet: 38, tFloor: 2, t0: 58, vwc0: 20 },
  soilless: { A: 80, b: 1.55, k: 0.42, vwcDry: 22, vwcWet: 52, tFloor: 1, t0: 22, vwc0: 30 },
}

export function initSensorModel(soilType: SoilType): SensorModel {
  const p = SOIL_PROFILES[soilType]
  return { ...p, soilType, curT: p.t0, curVwc: p.vwc0 }
}

// Tension (mb) as a decreasing power function of water applied (L/day).
function tensionFromWater(water: number, A: number, b: number, tFloor: number): number {
  return Math.max(tFloor, Math.min(88, A * Math.pow(Math.max(water, 0.05), -b)))
}

// VWC interpolated between dry/wet endpoints based on tension.
function vwcFromTension(tension: number, vwcDry: number, vwcWet: number): number {
  const n = Math.max(0, Math.min(1, 1 - tension / 80))
  return vwcDry + (vwcWet - vwcDry) * n
}

// Advance the field one day given the active program.
export function stepSensorModel(
  model: SensorModel,
  program: Program,
  dischargeLph: number,
  frozen: boolean,
): SensorModel {
  const water = frozen ? 0 : program.pulses * (program.sec / 3600) * dischargeLph
  const targetT = tensionFromWater(water, model.A, model.b, model.tFloor)
  const targetVwc = vwcFromTension(targetT, model.vwcDry, model.vwcWet)
  const jitter = () => (Math.random() - 0.5) * 1
  const curT = Math.max(0, model.curT + (targetT - model.curT) * model.k + jitter())
  const curVwc = Math.max(0, Math.min(100, model.curVwc + (targetVwc - model.curVwc) * model.k * 0.7))
  return { ...model, curT, curVwc }
}

// Current "true" sensor values (before per-reading noise).
export function readSensors(model: SensorModel): { t20: number; t40: number; vwc: number } {
  return {
    t20: model.curT,
    t40: model.soilType === "soilless" ? 0 : model.curT * 0.82,
    vwc: model.curVwc,
  }
}

// Box–Muller normal sample.
function gaussian(): number {
  const u = 1 - Math.random()
  const v = Math.random()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

// Generate a full day of noisy readings (1 per 10 min).
export function generateReadings(t20: number, t40: number, vwc: number): SensorReading[] {
  const out: SensorReading[] = []
  for (let i = 0; i < READINGS_PER_DAY; i++) {
    out.push({
      t20: Math.max(0, t20 + gaussian() * TEMP_NOISE_SD),
      t40: Math.max(0, t40 + gaussian() * TEMP_NOISE_SD),
      vwc: Math.max(0, Math.min(100, vwc + gaussian() * VWC_NOISE_SD)),
    })
  }
  return out
}

// Average a day's worth of readings into a single daily mean.
export function averageReadings(readings: SensorReading[]): SensorReading {
  const n = readings.length
  const acc = { t20: 0, t40: 0, vwc: 0, n }
  for (const r of readings) {
    acc.t20 += r.t20
    acc.t40 += r.t40
    acc.vwc += r.vwc
  }
  acc.t20 = +(acc.t20 / n).toFixed(2)
  acc.t40 = +(acc.t40 / n).toFixed(2)
  acc.vwc = +(acc.vwc / n).toFixed(2)
  return acc
}
