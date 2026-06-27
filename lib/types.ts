import type { SoilType } from "./theme"

export type Stage = "awaiting" | "cal1" | "cal2" | "cal3" | "optimize"
export type RunMode = "auto" | "semi_auto" | "full_manual" | "frozen"
export type OverrideMode = "none" | "semi_auto" | "full_manual"

export interface Program {
  pulses: number
  sec: number
}

export interface EngineConfig {
  soilType: SoilType
  has40cm: boolean
  extPulse: boolean
  cal2MaxDays: number
  dischargeLph: number
  drippers: number
}

export interface SensorReading {
  t20: number
  t40: number
  vwc: number
  n?: number
  date?: string
}

export interface Alert {
  level: "red" | "yellow"
  msg: string
  day: number
  id: number
}

export interface Snapshot {
  stage: Stage
  pulses: number
  sec: number
  stageEnteredDay: number
  windowStart: number
  vwcAtWindowStart: number | null
  daysBelow10: number
  daysAbove40: number
}

export interface Engine {
  cfg: EngineConfig
  stage: Stage
  program: Program
  stageEnteredDay: number
  daysBelow10: number
  daysAbove40: number
  daysBelow1: number
  windowStart: number
  vwcAtWindowStart: number | null
  overrideMode: OverrideMode
  runMode: RunMode
  snapshot: Snapshot | null
  baseline: Program | null
  overrideEnteredDay: number | null
  overrideStuckFired: boolean
  pendingProgram: Program | null
  pendingStage: Stage | null
  pendingOverrideMode: OverrideMode | null
  pendingBaseline: Program | null
  lastCycleDay: number | null
  frozen: boolean
  cal1NoDropCounter: number
  t40Acked: boolean
  cal1AlertFired: boolean
  cal2NoRiseFired: boolean
  vwcNotRisingFired: boolean
  cal2Below10Fired: boolean
  cal3Below10Fired: boolean
  cal3Above40Fired: boolean
  t40Active: boolean
  t20Below1Active: boolean
  t20Below1Cooldown: number
  alerts: Alert[]
  logBuffer: string[]
}

// Soil physics model state
export interface SensorModel {
  A: number
  b: number
  k: number
  vwcDry: number
  vwcWet: number
  tFloor: number
  t0: number
  vwc0: number
  soilType: SoilType
  curT: number
  curVwc: number
}

export interface ChartPoint {
  day: number
  t20: number
  t40: number
  vwc: number
  pulses: number
  stage: Stage
}

export interface TableRow {
  day: number
  t20: number
  t40: number
  vwc: number
  n: number
  stage: Stage
  pulses: number
  date?: string
}
