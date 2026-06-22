# Manual Override Logic — SensAItion Simulator v2.1

## Overview

The manual override system allows agronomists to take temporary control of irrigation during any stage of the algorithm. It preserves full system state and enables clean exit back to the algorithm.

---

## Entry: Two Override Modes

### Semi-Auto Override
- **Algorithm Status**: Continues running
- **Decision Logic**: All stage transitions, thresholds, and adjustments proceed normally
- **Manual Control**: Agronomist sets a baseline program (pulses/duration)
- **Baseline Role**: Stored as reference only; does not constrain algorithm decisions
- **Use Case**: Monitor/observe while algorithm runs; mark a reference tuning point

### Full Manual Override
- **Algorithm Status**: Completely paused (line 329-331: early return from decision logic)
- **Decision Logic**: No stage transitions, no threshold evaluation, no counter updates
- **Manual Control**: Agronomist's program runs as-is every day
- **Counter Behavior**: `daysBelow10`, `daysAbove40`, etc. remain frozen at entry values
- **Use Case**: Direct control; test manual irrigation scenarios; override broken algorithm state

---

## Snapshot & State Preservation

On entry to any override mode:

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

**"Exit to auto"** — Restores pre-override snapshot

1. Pending mode set to "none" (exit override)
2. Pending program set to snapshot's program
3. Pending stage set to snapshot's stage
4. All snapshot counters/windows restored
5. Changes apply at next cycle boundary

**Result**: System returns to exact pre-override state. Time is effectively rewound.

### Counter Behavior on Exit

- **From Semi-Auto**: Counters (daysBelow10, daysAbove40) are restored from snapshot. Any updates during semi_auto are discarded.
- **From Full Manual**: Counters are restored from snapshot. They were frozen during manual, so restoration just returns to entry values.

**Design Rationale**: Counters freeze in full_manual because the algorithm isn't running. When exiting, the snapshot restore is clean and deterministic. No need to manually set counters.

---

## Stuck Override Alert

If `overrideMode !== "none"` for ≥ `OVERRIDE_STUCK_DAYS` (currently 7 days):
- Yellow alert fires once: *"System in [mode] manual override for X days without reverting."*
- Reminds agronomist override is still active

---

## Pending State System

Override changes don't apply immediately. Instead:

1. User clicks "Execute" or "Exit"
2. Change queued as `pending*` (pendingOverrideMode, pendingProgram, pendingStage, etc.)
3. At next **cycle boundary** (day change):
   - Pending values applied to engine state
   - Change takes effect for that day onward

**Why**: Irrigation decisions are daily. Applying mid-day is inconsistent.

---

## Removed: `resume_modified_auto`

Previously allowed exiting with manual program as new auto baseline. **Removed because**:
- Counter freeze in full_manual meant state was corrupted on exit
- If agronomist wants permanent tuning, that belongs in config, not override
- Single exit path ("rewind") is simpler and safer

---

## Key Design Decisions

| Aspect | Decision | Why |
|--------|----------|-----|
| Semi-Auto baseline | Reference only, doesn't constrain | Keeps algorithm fully autonomous; baseline is just a marker |
| Full Manual counters | Freeze during override | Algorithm paused, counters irrelevant; snapshot restore is clean |
| Exit path | Single "rewind to snapshot" | Safe, deterministic, no state ambiguity |
| Pending application | At cycle boundary | Respects daily cycle; no mid-cycle confusion |
| Override duration | Alert at 7+ days | Safety reminder, not forced exit |

---

## Summary for PRD

**Manual override is a testing/intervention tool:**
- Semi-Auto: Algorithm continues, agronomist observes/marks baseline
- Full Manual: Algorithm paused, agronomist controls directly
- Exit: Always rewind to pre-override state (snapshot restore)
- Counters: Freeze in full_manual, restore on exit
- Pending: Changes apply at cycle boundary

Safe, simple, reversible.
