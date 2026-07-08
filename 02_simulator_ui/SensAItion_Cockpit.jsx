// ─────────────────────────────────────────────────────────────────────────────
// SensAItion Cockpit — Agronomist Mission Control (fleet demo)
//
// The commercial vision: one master agronomist supervising the Sensation
// engine running autonomously on many farms/orchards around the globe.
// Each site below runs the SAME engine logic as SensAItion_Simulator.jsx
// (ported from the verified Python engine), fed by the demo soil model.
//
// Convention: 02_simulator_ui/ is the source of truth; src/ holds the mirror
// that Vite builds. Keep both copies identical.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis,
  Tooltip as RTooltip, Legend, ReferenceLine, CartesianGrid,
} from "recharts";

// ─── Palette (matches simulator) ─────────────────────────────────────────────
const C = {
  bg:       "#F4F7F5",
  surface:  "#FFFFFF",
  raised:   "#EDF2EF",
  border:   "#D4E2DA",
  borderLit:"#B0CABB",
  chalk:    "#1A2B22",
  sub:      "#4A6B57",
  dim:      "#8FAF9C",
  green:    "#1E8A4C",
  greenDim: "#C6E8D4",
  blue:     "#1A72B8",
  amber:    "#B86A00",
  red:      "#C0352F",
  purple:   "#6B42C8",
  frost:    "#1A9AB0",
};

const STAGE_LABEL = { awaiting: "Awaiting", cal1: "Cal 1", cal2: "Cal 2", cal3: "Cal 3", optimize: "Optimize" };
const STAGE_COLOR = { awaiting: C.dim, cal1: C.blue, cal2: C.purple, cal3: C.amber, optimize: C.green };

// ─── Engine constants (mirror Python / simulator) ────────────────────────────
const E = {
  CAL1_PULSES: 200, CAL1_SEC: 120, CAL1_TRIGGER: 10, CAL1_ALERT_MB: 40, CAL1_ALERT_DAYS: 5, CAL1_CONSEC: 3,
  CAL2_PULSES: 180, CAL2_SEC: 30, CAL2_RISE: 40, CAL2_CONSEC: 3, CAL2_MAX_DAYS: 14,
  CAL3_LOW: 10, CAL3_HIGH: 40, CAL3_STABLE_LOW: 20, CAL3_STABLE_HIGH: 40, CAL3_ADJUST: 20,
  OPT_SEC: 30, OPT_ADJUST: 20, OPT_HIGH: 40, OPT_LOW: 10,
  PULSE_CEIL: 200, PULSE_FLOOR: 0,
  OVERRIDE_STUCK_DAYS: 3,
  WATER_DISCHARGE_LPH: 1.0, WATER_NUM_DRIPPERS: 21600, WATER_FIELD_HA: 10,
  WATER_MISMATCH_THRESHOLD: 0.2, WATER_PUMP_FAILURE_PROB: 0.004,
};

const OPTIMAL_VWC = { heavy: [50, 100], medium: [40, 50], sandy: [30, 35], soilless: [30, 50] };
const READINGS_PER_DAY = 144;
const SENSOR_NOISE_MB  = 1.5;
const SENSOR_NOISE_VWC = 0.3;

// ─── Soil physics simulator (identical to simulator) ─────────────────────────
function makeSoil(soilType) {
  const P = {
    heavy:    { A: 88, b: 1.55, k: 0.30, vwcDry: 14, vwcWet: 60, tFloor: 3, t0: 72, vwc0: 24 },
    medium:   { A: 82, b: 1.59, k: 0.33, vwcDry: 16, vwcWet: 54, tFloor: 2, t0: 66, vwc0: 26 },
    sandy:    { A: 84, b: 1.60, k: 0.40, vwcDry: 11, vwcWet: 38, tFloor: 2, t0: 58, vwc0: 20 },
    soilless: { A: 80, b: 1.55, k: 0.42, vwcDry: 22, vwcWet: 52, tFloor: 1, t0: 22, vwc0: 30 },
  }[soilType];
  return { ...P, soilType, curT: P.t0, curVwc: P.vwc0 };
}
function eqTension(litres, A, b, tFloor) {
  return Math.max(tFloor, Math.min(88, A * Math.pow(Math.max(litres, 0.05), -b)));
}
function eqVwcFromTension(teq, vwcDry, vwcWet) {
  const frac = Math.max(0, Math.min(1, 1 - teq / 80));
  return vwcDry + (vwcWet - vwcDry) * frac;
}
const ET_CONFIG = { low: { kDryScale: 0.5 }, medium: { kDryScale: 1.0 }, high: { kDryScale: 1.5 } };

function stepSoil(soil, program, dischargeLph, frozen, etLevel = "medium") {
  const litres = frozen ? 0 : program.pulses * (program.sec / 3600) * dischargeLph;
  const teq = eqTension(litres, soil.A, soil.b, soil.tFloor);
  const veq = eqVwcFromTension(teq, soil.vwcDry, soil.vwcWet);
  const noise = () => (Math.random() - 0.5) * 1.0;
  const { kDryScale } = ET_CONFIG[etLevel] || ET_CONFIG.medium;
  const gap = teq - soil.curT;
  const effectiveK = gap > 0 ? soil.k * kDryScale : soil.k;
  const curT = Math.max(0, soil.curT + gap * effectiveK + noise());
  const curVwc = Math.max(0, Math.min(100, soil.curVwc + (veq - soil.curVwc) * soil.k * 0.7));
  return { ...soil, curT, curVwc };
}
function soilReadings(soil) {
  return { t20: soil.curT, t40: soil.soilType === "soilless" ? 0 : soil.curT * 0.82, vwc: soil.curVwc };
}
function generateDailyReadings(baseT20, baseT40, baseVwc) {
  const randn = () => {
    const u = 1 - Math.random(), v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
  const readings = [];
  for (let i = 0; i < READINGS_PER_DAY; i++) {
    readings.push({
      t20: Math.max(0, baseT20 + randn() * SENSOR_NOISE_MB),
      t40: Math.max(0, baseT40 + randn() * SENSOR_NOISE_MB),
      vwc: Math.max(0, Math.min(100, baseVwc + randn() * SENSOR_NOISE_VWC)),
    });
  }
  return readings;
}
function computeDailyAvg(readings) {
  const n = readings.length;
  const avg = { t20: 0, t40: 0, vwc: 0, n };
  for (const r of readings) { avg.t20 += r.t20; avg.t40 += r.t40; avg.vwc += r.vwc; }
  avg.t20 = +(avg.t20 / n).toFixed(2);
  avg.t40 = +(avg.t40 / n).toFixed(2);
  avg.vwc = +(avg.vwc / n).toFixed(2);
  return avg;
}

// ─── Engine (identical logic to simulator; log lines trimmed) ─────────────────
function makeEngine(cfg) {
  return {
    cfg,
    stage: "awaiting",
    program: { pulses: 200, sec: 120 },
    stageEnteredDay: 0,
    daysBelow10: 0, daysAbove40: 0, daysBelow1: 0,
    windowStart: 0, vwcAtWindowStart: null,
    overrideMode: "none",
    runMode: "auto",
    snapshot: null,
    overrideEnteredDay: null, overrideStuckFired: false,
    pendingProgram: null, pendingStage: null, pendingOverrideMode: null,
    lastCycleDay: null,
    frozen: false,
    cal1NoDropCounter: 0,
    t40Acked: false,
    cal1AlertFired: false, cal2NoRiseFired: false, vwcNotRisingFired: false,
    cal2Below10Fired: false, cal3Below10Fired: false, cal3Above40Fired: false,
    t40Active: false, t20Below1Active: false, t20Below1Cooldown: 0,
    waterUsageHistory: [],
    waterMismatchFired: false, pumpFailureDay: null, clogDay: null,
    alerts: [],
  };
}
function clamp(p) { return Math.max(E.PULSE_FLOOR, Math.min(E.PULSE_CEIL, p)); }
function pushAlert(eng, level, msg, day) {
  eng.alerts.push({ level, msg, day, id: Math.random(), acked: false });
}
function setProgram(eng, pulses, sec) { eng.program = { pulses: clamp(pulses), sec }; }
function transition(eng, stage, day) {
  eng.stage = stage;
  eng.stageEnteredDay = day;
  eng.daysBelow10 = 0; eng.daysAbove40 = 0;
  eng.cal1AlertFired = false; eng.cal2NoRiseFired = false; eng.vwcNotRisingFired = false;
  eng.cal2Below10Fired = false; eng.cal3Below10Fired = false; eng.cal3Above40Fired = false;
}
function confirmStart(eng, day) {
  if (eng.stage === "awaiting") {
    transition(eng, "cal1", day);
    setProgram(eng, E.CAL1_PULSES, E.CAL1_SEC);
  }
}
function applyPendingIfNewCycle(eng, day) {
  if (eng.lastCycleDay === null) { eng.lastCycleDay = day; return; }
  if (day === eng.lastCycleDay) return;
  eng.lastCycleDay = day;
  if (eng.pendingOverrideMode !== null) {
    eng.overrideMode = eng.pendingOverrideMode;
    eng.runMode = { none: "auto", full_manual: "full_manual" }[eng.pendingOverrideMode] ?? "auto";
    eng.pendingOverrideMode = null;
  }
  if (eng.pendingProgram !== null) { eng.program = eng.pendingProgram; eng.pendingProgram = null; }
  if (eng.pendingStage !== null) { eng.stage = eng.pendingStage; eng.pendingStage = null; }
}
function enterOverride(eng, pulses, sec, day) {
  pulses = clamp(pulses);
  eng.snapshot = {
    stage: eng.stage, pulses: eng.program.pulses, sec: eng.program.sec,
    stageEnteredDay: eng.stageEnteredDay, windowStart: eng.windowStart,
    vwcAtWindowStart: eng.vwcAtWindowStart, daysBelow10: eng.daysBelow10, daysAbove40: eng.daysAbove40,
  };
  eng.pendingProgram = { pulses, sec };
  eng.pendingOverrideMode = "full_manual";
  eng.overrideEnteredDay = day;
  eng.overrideStuckFired = false;
}
function exitOverride(eng) {
  const s = eng.snapshot; if (!s) return;
  eng.pendingProgram = { pulses: s.pulses, sec: s.sec };
  eng.pendingStage = s.stage;
  eng.pendingOverrideMode = "none";
  eng.stageEnteredDay = s.stageEnteredDay;
  eng.windowStart = s.windowStart;
  eng.vwcAtWindowStart = s.vwcAtWindowStart;
  eng.daysBelow10 = s.daysBelow10; eng.daysAbove40 = s.daysAbove40;
  eng.snapshot = null;
  eng.overrideEnteredDay = null;
}
function freeze(eng) { eng.frozen = true; eng.runMode = "frozen"; }
function unfreeze(eng) {
  eng.frozen = false;
  eng.runMode = eng.overrideMode === "full_manual" ? "full_manual" : "auto";
}
function checkUniversalAlerts(eng, r, day) {
  if (eng.cfg.has40cm) {
    if (r.t40 < 10) {
      if (!eng.t40Acked) pushAlert(eng, "red", `40cm tensiometer daily avg below 10mb (${r.t40.toFixed(1)}mb) — over-saturation risk at depth. Acknowledge to silence.`, day);
      eng.t40Active = true;
    } else { eng.t40Active = false; eng.t40Acked = false; }
  } else {
    if (r.t20 < 10 && !eng.t40Active) { pushAlert(eng, "red", `Soilless: 20cm daily avg below 10mb (${r.t20.toFixed(1)}mb) — over-saturation risk.`, day); eng.t40Active = true; }
    else if (r.t20 >= 10) eng.t40Active = false;
  }
  if (eng.t20Below1Cooldown > 0) eng.t20Below1Cooldown--;
  if (r.t20 < 1) {
    if (!eng.t20Below1Active && eng.t20Below1Cooldown === 0) {
      pushAlert(eng, "yellow", `20cm tensiometer daily avg below 1mb (${r.t20.toFixed(1)}mb).`, day);
      eng.t20Below1Active = true; eng.t20Below1Cooldown = 14;
    }
  } else if (r.t20 > 3) eng.t20Below1Active = false;
  if (r.t20 < 1) eng.daysBelow1++; else eng.daysBelow1 = 0;
  if (eng.daysBelow1 >= 3) { pushAlert(eng, "red", "20cm daily avg below 1mb for 3 consecutive days — immediate action required.", day); eng.daysBelow1 = 0; }
}
function checkOverrideStuck(eng, day) {
  if (eng.overrideMode === "none" || eng.overrideEnteredDay === null) return;
  if (day - eng.overrideEnteredDay >= E.OVERRIDE_STUCK_DAYS && !eng.overrideStuckFired) {
    pushAlert(eng, "yellow", `System in Full Manual override for ${day - eng.overrideEnteredDay} days — consider reverting to Auto via "Resume last auto".`, day);
    eng.overrideStuckFired = true;
  }
}
function calculateWaterUsage(eng, day) {
  const perDripperLph = eng.cfg.dischargeLph || E.WATER_DISCHARGE_LPH;
  const numDrippers = eng.cfg.drippers || E.WATER_NUM_DRIPPERS;
  const plannedLiters = (perDripperLph / 3600) * eng.program.pulses * eng.program.sec * numDrippers;
  let actualLiters = 0;
  if (eng.frozen) {
    actualLiters = 0;
  } else {
    if (eng.pumpFailureDay === null && eng.clogDay === null && !eng.pumpEfficiency) eng.pumpEfficiency = 0.98;
    if (eng.pumpFailureDay === null && eng.clogDay === null) {
      if (Math.random() < E.WATER_PUMP_FAILURE_PROB) {
        if (Math.random() < 0.5) {
          eng.pumpFailureDay = day;
          pushAlert(eng, "red", "Pump failure detected — water delivery suspended.", day);
        } else {
          eng.clogDay = day;
          pushAlert(eng, "red", "System clog detected — water delivery severely reduced.", day);
        }
      }
    }
    let systemEfficiency = 1.0;
    if (eng.pumpFailureDay !== null) systemEfficiency = 0;
    else if (eng.clogDay !== null) {
      const clogDays = day - eng.clogDay;
      systemEfficiency = Math.max(0.2, 0.8 - clogDays * 0.05);
    } else {
      if (!eng.pumpEfficiency) eng.pumpEfficiency = 0.98;
      eng.pumpEfficiency = Math.max(0.90, eng.pumpEfficiency - Math.random() * 0.001);
      const sensorError = (Math.random() - 0.5) * 2 * 0.05;
      systemEfficiency = eng.pumpEfficiency + sensorError;
    }
    actualLiters = plannedLiters * systemEfficiency;
  }
  const deviation = plannedLiters > 0 ? Math.abs(actualLiters - plannedLiters) / plannedLiters : 0;
  const mismatch = deviation > E.WATER_MISMATCH_THRESHOLD;
  if (mismatch && !eng.waterMismatchFired) {
    const pct = (deviation * 100).toFixed(0);
    pushAlert(eng, "yellow", `Water usage mismatch: ${pct}% deviation from planned.`, day);
    eng.waterMismatchFired = true;
  } else if (!mismatch) {
    eng.waterMismatchFired = false;
  }
  eng.waterUsageHistory.push({ day, plannedLiters, actualLiters, deviation, mismatch });
}

// processDay: identical decisions to the simulator (log lines omitted)
function processDay(eng, r, day) {
  applyPendingIfNewCycle(eng, day);
  checkUniversalAlerts(eng, r, day);
  checkOverrideStuck(eng, day);
  calculateWaterUsage(eng, day);
  if (eng.overrideMode === "full_manual") return;
  const t20 = r.t20;

  if (eng.stage === "cal1") {
    if (t20 < E.CAL1_TRIGGER) eng.daysBelow10++; else eng.daysBelow10 = 0;
    if (t20 >= E.CAL1_ALERT_MB) {
      eng.cal1NoDropCounter++;
      if (eng.cal1NoDropCounter >= E.CAL1_ALERT_DAYS) {
        pushAlert(eng, "red", "Cal 1: tensiometer hasn't dropped below 40mb after 5 days.", day);
        eng.cal1NoDropCounter = 0;
      }
    } else eng.cal1NoDropCounter = 0;
    if (eng.daysBelow10 >= E.CAL1_CONSEC) {
      transition(eng, "cal2", day);
      setProgram(eng, E.CAL2_PULSES, eng.cfg.extPulse ? 60 : E.CAL2_SEC);
    }

  } else if (eng.stage === "cal2") {
    const winDay = day - eng.stageEnteredDay;
    if (t20 > E.CAL2_RISE) eng.daysAbove40++; else eng.daysAbove40 = 0;
    if (t20 < E.CAL1_TRIGGER) eng.daysBelow10++; else eng.daysBelow10 = 0;
    if (eng.daysBelow10 >= E.CAL2_CONSEC && !eng.cal2Below10Fired) {
      pushAlert(eng, "red", "Cal 2: tensiometer daily avg dropped below 10mb again.", day);
      eng.cal2Below10Fired = true; eng.daysBelow10 = 0;
    }
    if (winDay >= eng.cfg.cal2MaxDays && eng.daysAbove40 < E.CAL2_CONSEC && !eng.cal2NoRiseFired) {
      pushAlert(eng, "red", `Cal 2: didn't rise above 40mb within ${eng.cfg.cal2MaxDays} days.`, day);
      eng.cal2NoRiseFired = true;
    }
    if (eng.daysAbove40 >= E.CAL2_CONSEC) {
      transition(eng, "cal3", day);
      eng.windowStart = day; eng.vwcAtWindowStart = r.vwc;
    }

  } else if (eng.stage === "cal3") {
    const winDay = day - eng.windowStart;
    if (t20 < E.CAL3_LOW) { eng.daysBelow10++; eng.daysAbove40 = 0; }
    else if (t20 > E.CAL3_HIGH) { eng.daysAbove40++; eng.daysBelow10 = 0; }
    else { eng.daysBelow10 = 0; eng.daysAbove40 = 0; }
    if (eng.daysBelow10 >= 3) {
      if (!eng.cal3Below10Fired) { pushAlert(eng, "yellow", "Cal 3: T20 daily avg below 10mb for 3 days.", day); eng.cal3Below10Fired = true; }
      eng.daysBelow10 = 0;
    } else if (t20 >= 10) eng.cal3Below10Fired = false;
    if (eng.daysAbove40 >= 3) {
      if (!eng.cal3Above40Fired) { pushAlert(eng, "yellow", "Cal 3: T20 daily avg above 40mb for 3 days.", day); eng.cal3Above40Fired = true; }
      eng.daysAbove40 = 0;
    } else if (t20 <= 40) eng.cal3Above40Fired = false;
    if (winDay >= 7 && eng.vwcAtWindowStart !== null && r.vwc < eng.vwcAtWindowStart + 10 && !eng.vwcNotRisingFired) {
      pushAlert(eng, "red", `VWC hasn't risen 10% in a week (${eng.vwcAtWindowStart.toFixed(0)}% → ${r.vwc.toFixed(0)}%).`, day);
      eng.vwcNotRisingFired = true;
    }
    if (winDay >= 14) {
      if (t20 >= E.CAL3_STABLE_LOW && t20 <= E.CAL3_STABLE_HIGH) {
        transition(eng, "optimize", day);
        setProgram(eng, eng.program.pulses, E.OPT_SEC);
        eng.windowStart = day; eng.vwcAtWindowStart = r.vwc;
      } else {
        if (t20 < E.CAL3_LOW) setProgram(eng, eng.program.pulses - E.CAL3_ADJUST, eng.program.sec);
        else setProgram(eng, eng.program.pulses + E.CAL3_ADJUST, eng.program.sec);
        eng.windowStart = day; eng.vwcAtWindowStart = r.vwc;
        eng.daysBelow10 = 0; eng.daysAbove40 = 0; eng.vwcNotRisingFired = false;
      }
    }

  } else if (eng.stage === "optimize") {
    const winDay = day - eng.windowStart;
    if (winDay >= 14) {
      const [optMin] = OPTIMAL_VWC[eng.cfg.soilType];
      const vwcLow = r.vwc < optMin, t20High = t20 > E.OPT_HIGH, t20Low = t20 < E.OPT_LOW;
      let np = eng.program.pulses;
      if (t20Low) np -= E.OPT_ADJUST;
      else if (vwcLow || t20High) np += E.OPT_ADJUST;
      setProgram(eng, np, E.OPT_SEC);
      eng.windowStart = day; eng.vwcAtWindowStart = r.vwc;
    }
  }
}
function effectiveProgram(eng) {
  if (eng.frozen) return { pulses: 0, sec: eng.program.sec };
  return eng.program;
}

// ─── Fleet definition ─────────────────────────────────────────────────────────
// A demo fleet echoing Agrinoze's real footprint (Israel, India, US, EU, Africa).
const FLEET_DEF = [
  { id: "il-arava",   name: "Arava R&D Station",     country: "Israel",       flag: "🇮🇱", crop: "Bell peppers",      soilType: "sandy",    etLevel: "high",   startDaysAgo: 95, tz: "GMT+3" },
  { id: "il-jordan",  name: "Jordan Valley Dates",   country: "Israel",       flag: "🇮🇱", crop: "Medjool dates",     soilType: "heavy",    etLevel: "high",   startDaysAgo: 80, tz: "GMT+3" },
  { id: "in-fpo1",    name: "Karnataka FPO #1",      country: "India",        flag: "🇮🇳", crop: "Banana",            soilType: "medium",   etLevel: "high",   startDaysAgo: 55, tz: "GMT+5:30" },
  { id: "in-fpo2",    name: "Karnataka FPO #2",      country: "India",        flag: "🇮🇳", crop: "Table grapes",      soilType: "sandy",    etLevel: "medium", startDaysAgo: 40, tz: "GMT+5:30" },
  { id: "us-cv",      name: "Central Valley Pilot",  country: "USA",          flag: "🇺🇸", crop: "Almond orchard",    soilType: "medium",   etLevel: "medium", startDaysAgo: 28, tz: "GMT-8" },
  { id: "es-almeria", name: "Almería Greenhouse",    country: "Spain",        flag: "🇪🇸", crop: "Cucumber (soilless)", soilType: "soilless", etLevel: "low",  startDaysAgo: 18, tz: "GMT+1" },
  { id: "za-limpopo", name: "Limpopo Citrus",        country: "South Africa", flag: "🇿🇦", crop: "Citrus orchard",    soilType: "sandy",    etLevel: "medium", startDaysAgo: 7,  tz: "GMT+2" },
  { id: "it-emilia",  name: "Emilia-Romagna Trial",  country: "Italy",        flag: "🇮🇹", crop: "Processing tomato", soilType: "heavy",    etLevel: "low",    startDaysAgo: 0,  tz: "GMT+1" },
];

function makeSite(def) {
  const cfg = {
    soilType: def.soilType,
    has40cm: def.soilType !== "soilless",
    dischargeLph: E.WATER_DISCHARGE_LPH,
    drippers: E.WATER_NUM_DRIPPERS,
    cal2MaxDays: E.CAL2_MAX_DAYS,
    extPulse: false,
  };
  return {
    ...def,
    cfg,
    eng: makeEngine(cfg),
    soil: makeSoil(def.soilType),
    day: 0,
    history: [], // {day, t20, t40, vwc, pulses, sec, litres}
  };
}

function simulateSiteDay(site) {
  const prog = effectiveProgram(site.eng);
  site.soil = stepSoil(site.soil, prog, site.cfg.dischargeLph, site.eng.frozen, site.etLevel);
  const base = soilReadings(site.soil);
  const avg = computeDailyAvg(generateDailyReadings(base.t20, base.t40, base.vwc));
  processDay(site.eng, avg, site.day);
  const p = effectiveProgram(site.eng);
  const litres = p.pulses * (p.sec / 3600) * site.cfg.dischargeLph * site.cfg.drippers;
  site.history.push({ day: site.day, t20: avg.t20, t40: avg.t40, vwc: avg.vwc, pulses: p.pulses, sec: p.sec, litres });
  if (site.history.length > 400) site.history.shift();
  site.day += 1;
}

function initFleet() {
  return FLEET_DEF.map(def => {
    const site = makeSite(def);
    if (def.startDaysAgo > 0) {
      confirmStart(site.eng, 0);
      for (let d = 0; d < def.startDaysAgo; d++) simulateSiteDay(site);
      // Historical alerts would have been triaged long ago - keep only the last week open in the demo.
      for (const a of site.eng.alerts) if (a.day < site.day - 7) a.acked = true;
    }
    return site;
  });
}

// Conventional-protocol reference for the demo savings figure:
// evaporation-based protocols ≈ continuous drenching-level watering (Cal-1 program).
function conventionalLitres(site) {
  return E.CAL1_PULSES * (E.CAL1_SEC / 3600) * site.cfg.dischargeLph * site.cfg.drippers;
}

// ─── Small UI pieces ──────────────────────────────────────────────────────────
const card = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" };
const labelStyle = { fontSize: 11, fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: C.sub };

function Sparkline({ history, width = 150, height = 36 }) {
  const pts = history.slice(-30);
  if (pts.length < 2) return <div style={{ width, height }} />;
  const vals = pts.map(p => p.t20);
  const min = Math.min(...vals, 0), max = Math.max(...vals, 45);
  const x = i => (i / (pts.length - 1)) * (width - 2) + 1;
  const y = v => height - 2 - ((v - min) / (max - min || 1)) * (height - 4);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {/* target band 20–40mb */}
      <rect x={0} y={y(40)} width={width} height={Math.max(0, y(20) - y(40))} fill={C.greenDim} opacity={0.55} />
      <path d={path} fill="none" stroke={C.blue} strokeWidth={1.6} />
    </svg>
  );
}

function ModeBadge({ eng }) {
  const mode = eng.frozen ? "FROZEN" : eng.overrideMode === "full_manual" ? "MANUAL" : "AUTO";
  const color = eng.frozen ? C.frost : mode === "MANUAL" ? C.red : C.green;
  return (
    <span style={{
      fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", color: "#fff",
      background: color, borderRadius: 4, padding: "2px 7px",
    }}>{mode}</span>
  );
}

function StageBadge({ stage }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
      color: STAGE_COLOR[stage], border: `1px solid ${STAGE_COLOR[stage]}`,
      borderRadius: 4, padding: "1px 7px",
    }}>{STAGE_LABEL[stage]}</span>
  );
}

function fmtProgram(p) {
  if (p.pulses <= 0) return "0 pulses · tap off";
  const interval = (1440 / p.pulses).toFixed(1);
  return `${p.pulses} × ${p.sec}s · ${interval}m interval`;
}

// ─── Site card ────────────────────────────────────────────────────────────────
function SiteCard({ site, onOpen }) {
  const eng = site.eng;
  const openReds = eng.alerts.filter(a => a.level === "red" && !a.acked).length;
  const openYellows = eng.alerts.filter(a => a.level === "yellow" && !a.acked).length;
  const last = site.history[site.history.length - 1];
  const borderColor = openReds ? C.red : eng.overrideMode === "full_manual" ? C.amber : C.border;
  return (
    <div onClick={onOpen} style={{
      ...card, cursor: "pointer", border: `1.5px solid ${borderColor}`,
      boxShadow: openReds ? `0 0 0 3px ${C.red}22` : "none", padding: 12,
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontWeight: 800, color: C.chalk, fontSize: 14 }}>{site.flag} {site.name}</div>
          <div style={{ fontSize: 11.5, color: C.sub }}>{site.country} · {site.crop} · {site.soilType} · {site.tz}</div>
        </div>
        <ModeBadge eng={eng} />
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <StageBadge stage={eng.stage} />
        <span style={{ fontSize: 11, color: C.dim }}>day {site.day}</span>
        {openReds > 0 && <span style={{ fontSize: 11, fontWeight: 800, color: C.red }}>● {openReds} red</span>}
        {openYellows > 0 && <span style={{ fontSize: 11, fontWeight: 700, color: C.amber }}>● {openYellows} yellow</span>}
      </div>
      {eng.stage === "awaiting" ? (
        <div style={{ fontSize: 12, color: C.dim, fontStyle: "italic", padding: "6px 0" }}>
          Sensors live — awaiting agronomist confirmation to start.
        </div>
      ) : (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div style={{ fontSize: 11.5, color: C.sub, lineHeight: 1.7 }}>
            <div>T20 <b style={{ color: C.chalk }}>{last ? last.t20.toFixed(1) : "—"}</b> mb
              &nbsp; VWC <b style={{ color: C.chalk }}>{last ? last.vwc.toFixed(1) : "—"}</b>%</div>
            <div style={{ color: C.dim }}>{fmtProgram(effectiveProgram(eng))}</div>
          </div>
          <Sparkline history={site.history} />
        </div>
      )}
    </div>
  );
}

// ─── Detail drawer (drill-down + remote control) ──────────────────────────────
function SiteDetail({ site, onClose, onAction }) {
  const eng = site.eng;
  const [mp, setMp] = useState(eng.program.pulses);
  const [ms, setMs] = useState(eng.program.sec);
  const data = site.history.slice(-90);
  const open = eng.alerts.filter(a => !a.acked).slice().reverse();
  const btn = (bg, fg = "#fff") => ({
    background: bg, color: fg, border: "none", borderRadius: 6, padding: "7px 12px",
    fontWeight: 700, fontSize: 12, cursor: "pointer",
  });
  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "#0007", zIndex: 100,
      display: "flex", justifyContent: "flex-end",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: "min(680px, 95vw)", height: "100%", background: C.bg,
        borderLeft: `1px solid ${C.border}`, overflowY: "auto", padding: 18,
        display: "flex", flexDirection: "column", gap: 14,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 19, fontWeight: 800, color: C.chalk }}>{site.flag} {site.name}</div>
            <div style={{ fontSize: 12.5, color: C.sub }}>
              {site.country} · {site.crop} · {site.soilType} soil · ET {site.etLevel} · local {site.tz} · day {site.day}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <StageBadge stage={eng.stage} /> <ModeBadge eng={eng} />
            <button onClick={onClose} style={{ ...btn(C.raised, C.chalk), border: `1px solid ${C.border}` }}>✕</button>
          </div>
        </div>

        {/* chart */}
        <div style={{ ...card, padding: 10 }}>
          <div style={labelStyle}>Daily averages — last {data.length} days</div>
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: C.sub }} />
                <YAxis yAxisId="t" domain={[0, 80]} tick={{ fontSize: 10, fill: C.sub }} />
                <YAxis yAxisId="v" orientation="right" domain={[0, 60]} tick={{ fontSize: 10, fill: C.sub }} />
                <RTooltip contentStyle={{ fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine yAxisId="t" y={10} stroke={C.red} strokeDasharray="4 3" />
                <ReferenceLine yAxisId="t" y={40} stroke={C.amber} strokeDasharray="4 3" />
                <Line yAxisId="t" type="monotone" dataKey="t20" name="T20 (mb)" stroke={C.blue} dot={false} strokeWidth={2} />
                <Line yAxisId="v" type="monotone" dataKey="vwc" name="VWC (%)" stroke={C.green} dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* status + remote control */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={{ ...card, padding: 12 }}>
            <div style={labelStyle}>Status</div>
            <div style={{ fontSize: 12.5, color: C.sub, lineHeight: 2 }}>
              <div>Program: <b style={{ color: C.chalk }}>{fmtProgram(effectiveProgram(eng))}</b></div>
              <div>Days T20&lt;10mb: <b style={{ color: C.chalk }}>{eng.daysBelow10}</b> · T20&gt;40mb: <b style={{ color: C.chalk }}>{eng.daysAbove40}</b></div>
              <div>Pending change: <b style={{ color: C.chalk }}>{eng.pendingProgram ? `${eng.pendingProgram.pulses}×${eng.pendingProgram.sec}s at next midnight` : "none"}</b></div>
              <div>Water today: <b style={{ color: C.chalk }}>
                {((site.history[site.history.length - 1]?.litres ?? 0) / 1000).toFixed(1)} m³
              </b> (vs {(conventionalLitres(site) / 1000).toFixed(1)} m³ conventional)</div>
            </div>
          </div>
          <div style={{ ...card, padding: 12 }}>
            <div style={labelStyle}>Remote control (agronomist only)</div>
            {eng.stage === "awaiting" ? (
              <button style={{ ...btn(C.green), marginTop: 8 }} onClick={() => onAction(site.id, "start")}>▶ Confirm Start</button>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: C.sub }}>
                  <input type="number" value={mp} min={0} max={200} onChange={e => setMp(+e.target.value)}
                    style={{ width: 62, padding: 5, border: `1px solid ${C.border}`, borderRadius: 5 }} /> pulses ×
                  <input type="number" value={ms} min={10} max={600} onChange={e => setMs(+e.target.value)}
                    style={{ width: 62, padding: 5, border: `1px solid ${C.border}`, borderRadius: 5 }} /> sec
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <button style={btn(C.red)} onClick={() => onAction(site.id, "override", { pulses: mp, sec: ms })}>
                    Full Manual (next midnight)
                  </button>
                  {eng.overrideMode === "full_manual" || eng.pendingOverrideMode === "full_manual" ? (
                    <button style={btn(C.green)} onClick={() => onAction(site.id, "resume")}>Resume last auto</button>
                  ) : null}
                  {eng.frozen
                    ? <button style={btn(C.frost)} onClick={() => onAction(site.id, "unfreeze")}>Unfreeze</button>
                    : <button style={btn(C.frost)} onClick={() => onAction(site.id, "freeze")}>Irrigation Freeze</button>}
                </div>
                <div style={{ fontSize: 11, color: C.dim }}>
                  Snapshot-first override per PRD 29.6.26 — changes apply at cycle boundary, never mid-cycle.
                </div>
              </div>
            )}
          </div>
        </div>

        {/* site alerts */}
        <div style={{ ...card, padding: 12 }}>
          <div style={labelStyle}>Open alerts ({open.length})</div>
          {open.length === 0 && <div style={{ fontSize: 12.5, color: C.dim, marginTop: 6 }}>No open alerts.</div>}
          {open.slice(0, 12).map(a => (
            <div key={a.id} style={{
              display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center",
              padding: "7px 0", borderBottom: `1px solid ${C.border}`,
            }}>
              <div style={{ fontSize: 12.5, color: C.chalk }}>
                <b style={{ color: a.level === "red" ? C.red : C.amber }}>●</b> day {a.day} — {a.msg}
              </div>
              <button style={btn(C.raised, C.sub)} onClick={() => onAction(site.id, "ack", { alertId: a.id })}>Ack</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Main cockpit component ───────────────────────────────────────────────────
export default function SensAItionCockpit() {
  const [sites, setSites] = useState(() => initFleet());
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState(1);          // days per tick
  const [selected, setSelected] = useState(null); // site id
  const [, force] = useState(0);
  const sitesRef = useRef(sites);
  sitesRef.current = sites;

  useEffect(() => {
    if (!running) return;
    const iv = setInterval(() => {
      for (const site of sitesRef.current) {
        if (site.eng.stage === "awaiting" && site.day === 0) continue; // waits for Confirm Start
        for (let i = 0; i < speed; i++) simulateSiteDay(site);
      }
      setSites(s => [...s]);
    }, 1500);
    return () => clearInterval(iv);
  }, [running, speed]);

  const act = (siteId, action, payload = {}) => {
    const site = sitesRef.current.find(s => s.id === siteId);
    if (!site) return;
    const eng = site.eng, day = site.day;
    if (action === "start") confirmStart(eng, day);
    else if (action === "override") enterOverride(eng, payload.pulses, payload.sec, day);
    else if (action === "resume") exitOverride(eng);
    else if (action === "freeze") freeze(eng);
    else if (action === "unfreeze") unfreeze(eng);
    else if (action === "ack") {
      const a = eng.alerts.find(x => x.id === payload.alertId);
      if (a) {
        a.acked = true;
        if (a.msg.startsWith("40cm")) eng.t40Acked = true;
      }
    }
    setSites(s => [...s]); force(x => x + 1);
  };

  // ── fleet KPIs ──
  const kpi = useMemo(() => {
    const started = sites.filter(s => s.eng.stage !== "awaiting");
    const optimizing = sites.filter(s => s.eng.stage === "optimize").length;
    const reds = sites.reduce((n, s) => n + s.eng.alerts.filter(a => a.level === "red" && !a.acked).length, 0);
    const yellows = sites.reduce((n, s) => n + s.eng.alerts.filter(a => a.level === "yellow" && !a.acked).length, 0);
    const manual = sites.filter(s => s.eng.overrideMode === "full_manual" || s.eng.frozen).length;
    let actual = 0, conventional = 0;
    for (const s of started) {
      const last = s.history[s.history.length - 1];
      if (!last) continue;
      actual += last.litres;
      conventional += conventionalLitres(s);
    }
    const saved = conventional > 0 ? Math.max(0, 1 - actual / conventional) : 0;
    return { total: sites.length, started: started.length, optimizing, reds, yellows, manual, actual, saved };
  }, [sites]);

  // ── global alert queue (unacked, red first, newest first) ──
  const queue = useMemo(() => {
    const rows = [];
    for (const s of sites)
      for (const a of s.eng.alerts)
        if (!a.acked) rows.push({ site: s, a });
    rows.sort((x, y) =>
      (x.a.level === y.a.level ? y.a.day - x.a.day : x.a.level === "red" ? -1 : 1));
    return rows;
  }, [sites]);

  const selectedSite = sites.find(s => s.id === selected);
  const kpiBox = { ...card, padding: "10px 14px", flex: 1, minWidth: 110 };
  const kpiNum = { fontSize: 22, fontWeight: 800, color: C.chalk };

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: 16, fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 21, fontWeight: 900, color: C.chalk, letterSpacing: "0.01em" }}>
            SensAItion <span style={{ color: C.green }}>Cockpit</span>
          </div>
          <div style={{ fontSize: 12.5, color: C.sub }}>
            Agronomist mission control · Eitan Israeli · Agrinoze — one expert, {kpi.total} sites, 4 continents
            <span style={{ color: C.dim }}> · demo fleet on simulated soil physics</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={() => setRunning(r => !r)} style={{
            background: running ? C.raised : C.green, color: running ? C.chalk : "#fff",
            border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 14px", fontWeight: 800, fontSize: 12.5, cursor: "pointer",
          }}>{running ? "❚❚ Pause fleet" : "▶ Run fleet"}</button>
          {[1, 3, 7].map(v => (
            <button key={v} onClick={() => setSpeed(v)} style={{
              background: speed === v ? C.green : C.surface, color: speed === v ? "#fff" : C.sub,
              border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 10px", fontWeight: 700, fontSize: 12, cursor: "pointer",
            }}>{v}d/tick</button>
          ))}
        </div>
      </div>

      {/* KPI strip */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <div style={kpiBox}><div style={labelStyle}>Sites online</div><div style={kpiNum}>{kpi.started}/{kpi.total}</div></div>
        <div style={kpiBox}><div style={labelStyle}>In optimization</div><div style={{ ...kpiNum, color: C.green }}>{kpi.optimizing}</div></div>
        <div style={kpiBox}><div style={labelStyle}>Red alerts</div><div style={{ ...kpiNum, color: kpi.reds ? C.red : C.chalk }}>{kpi.reds}</div></div>
        <div style={kpiBox}><div style={labelStyle}>Yellow alerts</div><div style={{ ...kpiNum, color: kpi.yellows ? C.amber : C.chalk }}>{kpi.yellows}</div></div>
        <div style={kpiBox}><div style={labelStyle}>Manual / frozen</div><div style={kpiNum}>{kpi.manual}</div></div>
        <div style={kpiBox}>
          <div style={labelStyle}>Water vs conventional</div>
          <div style={{ ...kpiNum, color: C.blue }}>−{(kpi.saved * 100).toFixed(0)}%</div>
          <div style={{ fontSize: 10.5, color: C.dim }}>{(kpi.actual / 1000).toFixed(0)} m³/day fleet-wide (demo estimate)</div>
        </div>
      </div>

      {/* main grid */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2.2fr) minmax(260px, 1fr)", gap: 14, alignItems: "start" }}>
        {/* site cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(270px, 1fr))", gap: 10 }}>
          {sites.map(s => <SiteCard key={s.id} site={s} onOpen={() => setSelected(s.id)} />)}
        </div>

        {/* triage queue */}
        <div style={{ ...card, padding: 12, position: "sticky", top: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={labelStyle}>Alert triage — fleet</div>
            <span style={{ fontSize: 11, color: C.dim }}>{queue.length} open</span>
          </div>
          {queue.length === 0 && (
            <div style={{ fontSize: 12.5, color: C.dim, marginTop: 8 }}>
              All quiet. The engine is handling everything — that's the point.
            </div>
          )}
          <div style={{ maxHeight: "62vh", overflowY: "auto" }}>
            {queue.slice(0, 40).map(({ site, a }) => (
              <div key={a.id} onClick={() => setSelected(site.id)} style={{
                padding: "8px 6px", borderBottom: `1px solid ${C.border}`, cursor: "pointer",
                background: a.level === "red" ? `${C.red}0d` : "transparent", borderRadius: 4,
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: a.level === "red" ? C.red : C.amber }}>
                  {a.level.toUpperCase()} · {site.flag} {site.name} · day {a.day}
                </div>
                <div style={{ fontSize: 12, color: C.chalk, lineHeight: 1.45 }}>{a.msg}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {selectedSite && (
        <SiteDetail site={selectedSite} onClose={() => setSelected(null)} onAction={act} />
      )}

      <div style={{ marginTop: 16, fontSize: 11, color: C.dim, textAlign: "center" }}>
        Confidential — Agrinoze · Fleet demo: every site runs the verified SensAItion engine on the demonstration soil model.
        Single-site deep dive: switch to Simulator view.
      </div>
    </div>
  );
}
