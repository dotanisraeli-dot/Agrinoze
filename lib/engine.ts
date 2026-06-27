// SensAItion irrigation decision engine.
// Faithful rebuild of the calibration/optimization state machine, alerts,
// and manual-override logic. The engine object is mutated in place; callers
// snapshot it into React state after each step.

import { ENGINE, VWC_RANGE } from "./theme"
import type {
  Engine,
  EngineConfig,
  OverrideMode,
  Program,
  SensorReading,
  Stage,
} from "./types"

export function createEngine(cfg: EngineConfig): Engine {
  return {
    cfg,
    stage: "awaiting",
    program: { pulses: 200, sec: 120 },
    stageEnteredDay: 0,
    daysBelow10: 0,
    daysAbove40: 0,
    daysBelow1: 0,
    windowStart: 0,
    vwcAtWindowStart: null,
    overrideMode: "none",
    runMode: "auto",
    snapshot: null,
    baseline: null,
    overrideEnteredDay: null,
    overrideStuckFired: false,
    pendingProgram: null,
    pendingStage: null,
    pendingOverrideMode: null,
    pendingBaseline: null,
    lastCycleDay: null,
    frozen: false,
    cal1NoDropCounter: 0,
    t40Acked: false,
    cal1AlertFired: false,
    cal2NoRiseFired: false,
    vwcNotRisingFired: false,
    cal2Below10Fired: false,
    cal3Below10Fired: false,
    cal3Above40Fired: false,
    t40Active: false,
    t20Below1Active: false,
    t20Below1Cooldown: 0,
    alerts: [],
    logBuffer: [],
  }
}

export function clampPulses(p: number): number {
  return Math.max(ENGINE.PULSE_FLOOR, Math.min(ENGINE.PULSE_CEIL, p))
}

function pushAlert(e: Engine, level: "red" | "yellow", msg: string, day: number) {
  e.alerts.push({ level, msg, day, id: Math.random() })
  e.logBuffer.push(`  ALERT [${level.toUpperCase()}]: ${msg}`)
}

function setProgram(e: Engine, pulses: number, sec: number) {
  e.program = { pulses: clampPulses(pulses), sec }
}

function setStage(e: Engine, stage: Stage, day: number) {
  e.stage = stage
  e.stageEnteredDay = day
  e.daysBelow10 = 0
  e.daysAbove40 = 0
  e.cal1AlertFired = false
  e.cal2NoRiseFired = false
  e.vwcNotRisingFired = false
  e.cal2Below10Fired = false
  e.cal3Below10Fired = false
  e.cal3Above40Fired = false
}

// Begin: awaiting -> cal1
export function startSystem(e: Engine, day: number) {
  if (e.stage === "awaiting") {
    setStage(e, "cal1", day)
    setProgram(e, ENGINE.CAL1_PULSES, ENGINE.CAL1_SEC)
  }
}

// Apply any changes staged for the next midnight cycle.
function applyPendingChanges(e: Engine, day: number) {
  if (e.lastCycleDay === null) {
    e.lastCycleDay = day
    return
  }
  if (day === e.lastCycleDay) return
  e.lastCycleDay = day
  if (e.pendingOverrideMode !== null) {
    e.overrideMode = e.pendingOverrideMode
    e.runMode = (
      { none: "auto", full_manual: "full_manual", semi_auto: "semi_auto" } as const
    )[e.pendingOverrideMode]
    e.pendingOverrideMode = null
  }
  if (e.pendingBaseline !== null) {
    e.baseline = e.pendingBaseline
    e.pendingBaseline = null
  }
  if (e.pendingProgram !== null) {
    e.program = e.pendingProgram
    e.pendingProgram = null
  }
  if (e.pendingStage !== null) {
    e.stage = e.pendingStage
    e.pendingStage = null
  }
}

// Stage a manual override; takes effect next midnight. Saves an auto snapshot.
export function applyOverride(
  e: Engine,
  mode: OverrideMode,
  pulses: number,
  sec: number,
  day: number,
) {
  pulses = clampPulses(pulses)
  e.snapshot = {
    stage: e.stage,
    pulses: e.program.pulses,
    sec: e.program.sec,
    stageEnteredDay: e.stageEnteredDay,
    windowStart: e.windowStart,
    vwcAtWindowStart: e.vwcAtWindowStart,
    daysBelow10: e.daysBelow10,
    daysAbove40: e.daysAbove40,
  }
  const prog: Program = { pulses, sec }
  e.pendingProgram = prog
  e.pendingOverrideMode = mode
  e.pendingBaseline = prog
  e.overrideEnteredDay = day
  e.overrideStuckFired = false
}

// Exit override: either restore pre-override snapshot or keep manual baseline.
export function exitOverride(e: Engine, choice: "resume_last_auto" | "resume_modified_auto", _day: number) {
  if (choice === "resume_last_auto") {
    const s = e.snapshot
    if (!s) return
    e.pendingProgram = { pulses: s.pulses, sec: s.sec }
    e.pendingStage = s.stage
    e.pendingOverrideMode = "none"
    e.pendingBaseline = null
    e.stageEnteredDay = s.stageEnteredDay
    e.windowStart = s.windowStart
    e.vwcAtWindowStart = s.vwcAtWindowStart
    e.daysBelow10 = s.daysBelow10
    e.daysAbove40 = s.daysAbove40
  } else {
    const b = e.baseline
    if (!b) return
    e.pendingProgram = { pulses: b.pulses, sec: b.sec }
    e.pendingOverrideMode = "none"
    e.pendingBaseline = null
  }
  e.snapshot = null
  e.overrideEnteredDay = null
}

export function freeze(e: Engine) {
  e.frozen = true
  e.runMode = "frozen"
}

export function unfreeze(e: Engine) {
  e.frozen = false
  e.runMode = ({ none: "auto", full_manual: "full_manual", semi_auto: "semi_auto" } as const)[e.overrideMode]
}

// Sensor-driven safety alerts (saturation, low tension).
function checkSensorAlerts(e: Engine, r: SensorReading, day: number) {
  if (e.cfg.has40cm) {
    if (r.t40 < 10) {
      if (!e.t40Acked)
        pushAlert(
          e,
          "red",
          `40cm tensiometer daily avg below 10mb (${r.t40.toFixed(1)}mb) — over-saturation risk at depth. Acknowledge to silence.`,
          day,
        )
      e.t40Active = true
    } else {
      e.t40Active = false
      e.t40Acked = false
    }
  } else if (r.t20 < 10 && !e.t40Active) {
    pushAlert(e, "red", `Soilless: 20cm daily avg below 10mb (${r.t20.toFixed(1)}mb) — over-saturation risk.`, day)
    e.t40Active = true
  } else if (r.t20 >= 10) {
    e.t40Active = false
  }

  if (e.t20Below1Cooldown > 0) e.t20Below1Cooldown--
  if (r.t20 < 1) {
    if (!e.t20Below1Active && e.t20Below1Cooldown === 0) {
      pushAlert(e, "yellow", `20cm tensiometer daily avg below 1mb (${r.t20.toFixed(1)}mb).`, day)
      e.t20Below1Active = true
      e.t20Below1Cooldown = 14
    }
  } else if (r.t20 > 3) {
    e.t20Below1Active = false
  }

  if (r.t20 < 1) e.daysBelow1++
  else e.daysBelow1 = 0
  if (e.daysBelow1 >= 3) {
    pushAlert(e, "red", "20cm daily avg below 1mb for 3 consecutive days — immediate action required.", day)
    e.daysBelow1 = 0
  }
}

// Warn when a manual override has been left active for too long.
function checkOverrideStuck(e: Engine, day: number) {
  if (e.overrideMode === "none" || e.overrideEnteredDay === null) return
  if (day - e.overrideEnteredDay >= ENGINE.OVERRIDE_STUCK_DAYS && !e.overrideStuckFired) {
    pushAlert(
      e,
      "yellow",
      `System in ${e.overrideMode} manual override for ${day - e.overrideEnteredDay} days without reverting.`,
      day,
    )
    e.overrideStuckFired = true
  }
}

// Main daily decision step. Mutates engine; fills logBuffer for the day.
export function runDecision(e: Engine, r: SensorReading, day: number) {
  e.logBuffer = []
  applyPendingChanges(e, day)
  checkSensorAlerts(e, r, day)
  checkOverrideStuck(e, day)

  const lpd = e.cfg.dischargeLph > 0 ? e.program.pulses * (e.program.sec / 3600) * e.cfg.dischargeLph : 0
  const programLine = `${e.program.pulses} pulses × ${e.program.sec}s  (~${lpd.toFixed(2)} L/day)`

  e.logBuffer.push("=".repeat(60))
  e.logBuffer.push(`DAY ${day}  |  Stage: ${e.stage.toUpperCase()}  |  Run mode: ${e.runMode}`)
  e.logBuffer.push(
    `Sensor daily averages:  T20=${r.t20.toFixed(2)} mb  |  T40=${r.t40.toFixed(2)} mb  |  VWC=${r.vwc.toFixed(2)}%`,
  )
  e.logBuffer.push(`Active program:  ${programLine}`)

  if (e.overrideMode === "full_manual") {
    e.logBuffer.push("Decision: FULL MANUAL override active — auto logic paused, no algorithm decisions made.")
    return
  }

  const t = r.t20

  if (e.stage === "cal1") {
    e.logBuffer.push(
      `Counters:  days T20 < 10mb: ${e.daysBelow10}/3 (need 3 to advance)  |  cal1 no-drop counter: ${e.cal1NoDropCounter}/5`,
    )
    if (t < ENGINE.CAL1_TRIGGER) {
      e.daysBelow10++
      e.logBuffer.push(`T20 ${t.toFixed(2)} mb < 10mb threshold → consecutive low days now ${e.daysBelow10}/3`)
    } else {
      e.daysBelow10 = 0
      e.logBuffer.push(`T20 ${t.toFixed(2)} mb ≥ 10mb — reset consecutive low counter`)
    }
    if (t >= ENGINE.CAL1_ALERT_MB) {
      e.cal1NoDropCounter++
      if (e.cal1NoDropCounter >= ENGINE.CAL1_ALERT_DAYS) {
        pushAlert(e, "red", "Cal 1: tensiometer hasn't dropped below 40mb after 5 days.", day)
        e.cal1NoDropCounter = 0
      }
    } else {
      e.cal1NoDropCounter = 0
    }
    if (e.daysBelow10 >= ENGINE.CAL1_CONSEC) {
      setStage(e, "cal2", day)
      setProgram(e, ENGINE.CAL2_PULSES, e.cfg.extPulse ? 60 : ENGINE.CAL2_SEC)
      e.logBuffer.push("✓ TRANSITION  CAL1 → CAL2")
      e.logBuffer.push("  Reason: T20 below 10mb for 3 consecutive days — soil sufficiently drenched")
      e.logBuffer.push(`  New program: ${ENGINE.CAL2_PULSES} pulses × ${e.cfg.extPulse ? 60 : ENGINE.CAL2_SEC}s (reduction phase)`)
    } else {
      e.logBuffer.push(`Decision: Continue CAL1 — need ${3 - e.daysBelow10} more consecutive days below 10mb`)
    }
  } else if (e.stage === "cal2") {
    const dayInStage = day - e.stageEnteredDay
    e.logBuffer.push(
      `Counters:  days T20 > 40mb: ${e.daysAbove40}/3  |  days T20 < 10mb: ${e.daysBelow10}/3  |  day in stage: ${dayInStage}/${e.cfg.cal2MaxDays}`,
    )
    if (t > ENGINE.CAL2_RISE) {
      e.daysAbove40++
      e.logBuffer.push(`T20 ${t.toFixed(2)} mb > 40mb → consecutive high days now ${e.daysAbove40}/3`)
    } else {
      e.daysAbove40 = 0
    }
    if (t < ENGINE.CAL1_TRIGGER) {
      e.daysBelow10++
      e.logBuffer.push(`T20 ${t.toFixed(2)} mb < 10mb → consecutive low days now ${e.daysBelow10}/3`)
    } else {
      e.daysBelow10 = 0
    }
    if (e.daysBelow10 >= ENGINE.CAL2_CONSEC && !e.cal2Below10Fired) {
      pushAlert(e, "red", "Cal 2: tensiometer daily avg dropped below 10mb again.", day)
      e.cal2Below10Fired = true
      e.daysBelow10 = 0
    }
    if (dayInStage >= e.cfg.cal2MaxDays && e.daysAbove40 < ENGINE.CAL2_CONSEC && !e.cal2NoRiseFired) {
      pushAlert(e, "red", `Cal 2: didn't rise above 40mb within ${e.cfg.cal2MaxDays} days.`, day)
      e.cal2NoRiseFired = true
    }
    if (e.daysAbove40 >= ENGINE.CAL2_CONSEC) {
      setStage(e, "cal3", day)
      e.windowStart = day
      e.vwcAtWindowStart = r.vwc
      e.logBuffer.push("✓ TRANSITION  CAL2 → CAL3")
      e.logBuffer.push("  Reason: T20 above 40mb for 3 consecutive days — soil sufficiently dried")
      e.logBuffer.push(`  Window start: Day ${day}  |  VWC at window start: ${r.vwc.toFixed(2)}%`)
    } else {
      e.logBuffer.push("Decision: Continue CAL2 — waiting for T20 to rise above 40mb for 3 consecutive days")
    }
  } else if (e.stage === "cal3") {
    const windowDay = day - e.windowStart
    e.logBuffer.push(
      `Counters:  days T20 < 10mb: ${e.daysBelow10}  |  days T20 > 40mb: ${e.daysAbove40}  |  window day: ${windowDay}/14`,
    )
    if (e.vwcAtWindowStart !== null)
      e.logBuffer.push(
        `VWC at window start: ${e.vwcAtWindowStart.toFixed(2)}%  |  current VWC: ${r.vwc.toFixed(2)}%  |  rise: ${(r.vwc - e.vwcAtWindowStart).toFixed(2)}%`,
      )

    if (t < ENGINE.CAL3_LOW) {
      e.daysBelow10++
      e.daysAbove40 = 0
    } else if (t > ENGINE.CAL3_HIGH) {
      e.daysAbove40++
      e.daysBelow10 = 0
    } else {
      e.daysBelow10 = 0
      e.daysAbove40 = 0
    }

    if (e.daysBelow10 >= 3) {
      if (!e.cal3Below10Fired) {
        pushAlert(e, "yellow", "Cal 3: T20 daily avg below 10mb for 3 days.", day)
        e.cal3Below10Fired = true
      }
      e.daysBelow10 = 0
    } else if (t >= 10) {
      e.cal3Below10Fired = false
    }
    if (e.daysAbove40 >= 3) {
      if (!e.cal3Above40Fired) {
        pushAlert(e, "yellow", "Cal 3: T20 daily avg above 40mb for 3 days.", day)
        e.cal3Above40Fired = true
      }
      e.daysAbove40 = 0
    } else if (t <= 40) {
      e.cal3Above40Fired = false
    }

    if (
      windowDay >= 7 &&
      e.vwcAtWindowStart !== null &&
      r.vwc < e.vwcAtWindowStart + 10 &&
      !e.vwcNotRisingFired
    ) {
      pushAlert(
        e,
        "red",
        `VWC hasn't risen 10% in a week (${e.vwcAtWindowStart.toFixed(0)}% → ${r.vwc.toFixed(0)}%).`,
        day,
      )
      e.vwcNotRisingFired = true
    }

    if (windowDay >= 14) {
      e.logBuffer.push("--- 14-day window end ---")
      if (t >= ENGINE.CAL3_STABLE_LOW && t <= ENGINE.CAL3_STABLE_HIGH) {
        e.logBuffer.push(`T20 ${t.toFixed(2)} mb stable in 20–40mb range`)
        e.logBuffer.push("✓ TRANSITION  CAL3 → OPTIMIZE")
        e.logBuffer.push(`  New program: ${e.program.pulses} pulses × ${ENGINE.OPT_SEC}s (optimization phase begins)`)
        setStage(e, "optimize", day)
        setProgram(e, e.program.pulses, ENGINE.OPT_SEC)
        e.windowStart = day
        e.vwcAtWindowStart = r.vwc
      } else {
        const before = e.program.pulses
        if (t < ENGINE.CAL3_LOW) {
          setProgram(e, e.program.pulses - ENGINE.CAL3_ADJUST, e.program.sec)
          e.logBuffer.push(`T20 ${t.toFixed(2)} mb < 20mb (too wet) → reduce pulses ${before} → ${e.program.pulses}`)
        } else {
          setProgram(e, e.program.pulses + ENGINE.CAL3_ADJUST, e.program.sec)
          e.logBuffer.push(`T20 ${t.toFixed(2)} mb > 40mb (too dry) → increase pulses ${before} → ${e.program.pulses}`)
        }
        e.logBuffer.push(`Decision: Continue CAL3 — new window starts Day ${day}`)
        e.windowStart = day
        e.vwcAtWindowStart = r.vwc
        e.daysBelow10 = 0
        e.daysAbove40 = 0
        e.vwcNotRisingFired = false
      }
    } else {
      e.logBuffer.push(`Decision: Continue CAL3 — ${14 - windowDay} days remaining in window`)
    }
  } else if (e.stage === "optimize") {
    const windowDay = day - e.windowStart
    e.logBuffer.push(`Window day: ${windowDay}/14`)
    if (windowDay >= 14) {
      e.logBuffer.push("--- 14-day window end ---")
      const [vwcLow] = VWC_RANGE[e.cfg.soilType]
      const vwcTooLow = r.vwc < vwcLow
      const tooDry = t > ENGINE.OPT_HIGH
      const tooWet = t < ENGINE.OPT_LOW
      const before = e.program.pulses
      let next = e.program.pulses
      if (tooWet) {
        next -= ENGINE.OPT_ADJUST
        e.logBuffer.push(`T20 ${t.toFixed(2)} mb < ${ENGINE.OPT_LOW}mb (too wet) → reduce pulses ${before} → ${clampPulses(next)}`)
      } else if (vwcTooLow || tooDry) {
        next += ENGINE.OPT_ADJUST
        const why = tooDry ? `T20 ${t.toFixed(2)} mb > ${ENGINE.OPT_HIGH}mb (too dry)` : `VWC ${r.vwc.toFixed(2)}% < optimal ${vwcLow}%`
        e.logBuffer.push(`${why} → increase pulses ${before} → ${clampPulses(next)}`)
      } else {
        e.logBuffer.push(`T20=${t.toFixed(2)} mb  VWC=${r.vwc.toFixed(2)}%  both in optimal range → no change (${before} pulses)`)
      }
      setProgram(e, next, ENGINE.OPT_SEC)
      e.windowStart = day
      e.vwcAtWindowStart = r.vwc
    } else {
      e.logBuffer.push(`Decision: Continue OPTIMIZE — ${14 - windowDay} days remaining in window`)
    }
  }
}

// Effective program actually delivered (frozen => zero pulses).
export function effectiveProgram(e: Engine): Program {
  return e.frozen ? { pulses: 0, sec: e.program.sec } : e.program
}

export function describeProgram(p: Program): string {
  if (p.pulses <= 0) return "0 pulses · tap off"
  const interval = (1440 / p.pulses).toFixed(1)
  return `${p.pulses} pulses · ${p.sec}s · ${interval}m interval`
}

// Download the full narrative decision log.
export function exportLog(log: string[], soilType: string, fileName: string) {
  const source = fileName ? `from file: ${fileName}` : "simulated"
  const header =
    [
      "=".repeat(60),
      "SensAItion Algorithm Decision Log",
      `Soil type: ${soilType}  |  Data source: ${source}`,
      `Generated: ${new Date().toISOString().slice(0, 19).replace("T", " ")} UTC`,
      "=".repeat(60),
      "",
    ].join("\n")
  const body = log.join("\n") + "\n"
  const blob = new Blob([header + body], { type: "text/plain;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `sensation_decision_log_${new Date().toISOString().slice(0, 10)}.txt`
  a.style.display = "none"
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }, 1000)
}
