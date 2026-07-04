# Manual Override Logic — SensAItion Simulator (PRD 29.6.26)

## Overview

The manual override system lets the agronomist take temporary, full control of irrigation during any stage of the algorithm. It preserves full system state and enables a clean, deterministic exit back to the algorithm.

**Update (PRD 29.6.26):** the system now offers a single override mode — Full Manual. Semi-Auto (auto logic continues from a manual baseline) and the "Resume Modified Auto" exit were both moved to Future Requirements and are intentionally not implemented in the current phase. This doc supersedes the v2.1 description, which documented two entry modes and two exit modes that no longer exist in code.

---

## Entry: Full Manual Override (only mode)

- **Algorithm Status**: Completely paused (auto stage transitions, thresholds, and counter updates all stop)
- **Manual Control**: Agronomist's continuous program (pulses/duration) runs as-is every day
- **Counter Behaviour**: `daysBelow10`, `daysAbove40`, etc. remain frozen at entry values
- **Use Case**: Direct control; test manual irrigation scenarios; override broken algorithm state; a "mini experiment" before returning to Auto

---

## Snapshot & State Preservation

On entry to override:

```
snapshot = {
  stage,
  program: { pulses, sec },
  stageEnteredDay,
  windowStart,
  vwcAtWindowStart,
  daysBelow10,
  daysAbove40
}
```

The snapshot captures the **exact state at override entry**. All other state (alerts, flags, frozen status) continues as-is.

---

## Exit Logic: Single Path

**"Resume last auto"** — Restores pre-override snapshot

1. Pending mode set to "none" (exit override)
2. Pending program set to snapshot's program
3. Pending stage set to snapshot's stage
4. All snapshot counters/windows restored
5. Changes apply at next cycle boundary

**Result**: System returns to exact pre-override state. Time is effectively rewound.

### Counter Behaviour on Exit

Counters freeze during Full Manual override (algorithm isn't running). On exit, the snapshot restore returns them to their entry values — no manual reconciliation needed.

---

## Stuck Override Alert

If `overrideMode !== "none"` for ≥ `OVERRIDE_STUCK_DAYS` (3 days per PRD 29.6.26 — "more than 3 consecutive days"):
- Yellow alert fires once: *"System in Full Manual override for X days — consider reverting to Auto via 'Resume last auto'."*
- Reminds the agronomist the override is still active

---

## Pending State System

Override changes don't apply immediately. Instead:

1. User clicks "Execute" or "Resume last auto"
2. Change queued as `pending*` (pendingOverrideMode, pendingProgram, pendingStage, etc.)
3. At next **cycle boundary** (day change):
   - Pending values applied to engine state
   - Change takes effect for that day onward

**Why**: Irrigation decisions are daily. Applying mid-day is inconsistent.

---

## Removed since v2.1: `semi_auto` and `resume_modified_auto`

PRD 29.6.26 moved both to Future Requirements:
- **Semi-Auto** (auto logic continues from a manual baseline, program not paused) — deferred; may return as "advanced manual mode" in a later phase.
- **Resume Modified Auto** (keep manual values as the new auto baseline on exit) — removed along with Semi-Auto, since it only made sense as a companion to it.

Both the JS simulator (`src/SensAItion_Simulator.jsx`, `02_simulator_ui/SensAItion_Simulator.jsx`) and the Python reference engine (`01_engine/engine/models.py`, `algorithm.py`) have been updated to match: `OverrideMode` and `ExitMode` no longer have `SEMI_AUTO` / `RESUME_MODIFIED_AUTO` members, and `enter_manual_override()` / `exit_manual_override()` no longer take a mode parameter.

---

## Key Design Decisions

| Aspect | Decision | Why |
|--------|----------|-----|
| Override mode | Full Manual only (current phase) | PRD 29.6.26 simplification; Semi-Auto deferred to Future Requirements |
| Full Manual counters | Freeze during override | Algorithm paused, counters irrelevant; snapshot restore is clean |
| Exit path | Single "resume last auto" (rewind to snapshot) | Safe, deterministic, no state ambiguity |
| Pending application | At cycle boundary | Respects daily cycle; no mid-cycle confusion |
| Override duration | Alert at 3+ days | Matches PRD 29.6.26 wording exactly |

---

## Summary for PRD

**Manual override is a testing/intervention tool:**
- Full Manual: Algorithm paused, agronomist controls directly
- Exit: Always rewind to pre-override state (snapshot restore)
- Counters: Freeze during override, restore on exit
- Pending: Changes apply at cycle boundary
- Stuck alert: fires once at 3+ consecutive days in override

Safe, simple, reversible.
