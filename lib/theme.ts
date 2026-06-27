// SensAItion Agronomist Simulator — design tokens & engine constants
// Extracted and rebuilt as editable source.

export const theme = {
  bg: "#F4F7F5",
  surface: "#FFFFFF",
  raised: "#EDF2EF",
  border: "#D4E2DA",
  borderLit: "#B0CABB",
  chalk: "#1A2B22",
  sub: "#4A6B57",
  dim: "#8FAF9C",
  green: "#1E8A4C",
  greenDim: "#C6E8D4",
  blue: "#1A72B8",
  amber: "#B86A00",
  red: "#C0352F",
  purple: "#6B42C8",
  frost: "#1A9AB0",
} as const

export type Theme = typeof theme

// Calibration / optimization stage labels (index 0..4)
export const STAGE_LABELS = ["Awaiting", "Cal 1", "Cal 2", "Cal 3", "Optimize"] as const

// Maps engine stage -> stepper index
export const STAGE_INDEX: Record<string, number> = {
  awaiting: 0,
  cal1: 1,
  cal2: 2,
  cal3: 3,
  optimize: 4,
}

// Core engine thresholds / tuning parameters
export const ENGINE = {
  CAL1_PULSES: 200,
  CAL1_SEC: 120,
  CAL1_TRIGGER: 10,
  CAL1_ALERT_MB: 40,
  CAL1_ALERT_DAYS: 5,
  CAL1_CONSEC: 3,
  CAL2_PULSES: 180,
  CAL2_SEC: 30,
  CAL2_RISE: 40,
  CAL2_CONSEC: 3,
  CAL2_MAX_DAYS: 14,
  CAL3_LOW: 10,
  CAL3_HIGH: 40,
  CAL3_STABLE_LOW: 20,
  CAL3_STABLE_HIGH: 40,
  CAL3_ADJUST: 20,
  OPT_SEC: 30,
  OPT_ADJUST: 20,
  OPT_HIGH: 40,
  OPT_LOW: 10,
  PULSE_CEIL: 200,
  PULSE_FLOOR: 0,
  OVERRIDE_STUCK_DAYS: 3,
} as const

// Optimal VWC (%) range per soil type: [low, high]
export const VWC_RANGE: Record<SoilType, [number, number]> = {
  heavy: [50, 100],
  medium: [40, 50],
  sandy: [30, 35],
  soilless: [30, 50],
}

// Synthetic field sampling
export const READINGS_PER_DAY = 144 // 1 reading / 10 min
export const TEMP_NOISE_SD = 1.5
export const VWC_NOISE_SD = 0.3

export type SoilType = "heavy" | "medium" | "sandy" | "soilless"

export const SPEED_INTERVALS = [2000, 1000, 500, 333, 250, 200]
export const SPEED_LABELS = ["0.5×", "1×", "2×", "3×", "4×", "5×"]
