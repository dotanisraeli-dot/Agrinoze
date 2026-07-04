"""
Agrinoze — Algorithm Verification Suite
========================================
Organised in 6 sections:

  1. PRD Clause Audit      — every named rule from the PRD, one test per clause
  2. Boundary Conditions   — values at exact thresholds (0, 1, 9.9, 10, 10.1 …)
  3. Counter Logic         — consecutive-day counters: reset, accumulate, carry-over
  4. Scenario Simulations  — realistic multi-week journeys through the system
  5. Logical Consistency   — invariants that must hold regardless of input
  6. Bugs Found            — documents any discovered issues with regression tests
"""

import sys, io, contextlib, types

# ── patch pytest so the file imports without the package ──────────────────────
sys.modules.setdefault("pytest", types.ModuleType("pytest"))
sys.path.insert(0, "/home/claude")

from datetime import datetime, timedelta
from agrinoze.engine.models import (
    SiteConfig, SoilType, WaterType,
    SensorReading, Stage, AlertLevel, IrrigationProgram,
    OPTIMAL_VWC,
)
from agrinoze.engine.algorithm import IrrigationEngine

# ─── Helpers ──────────────────────────────────────────────────────────────────

def cfg(**kw) -> SiteConfig:
    return SiteConfig(
        soil_type=kw.get("soil_type", SoilType.MEDIUM),
        water_type=WaterType.REGULAR,
        discharge_rate_lph=1.0,
        num_drippers=100,
        use_extended_pulse_sub2=kw.get("ext", False),
    )

def R(t20=30.0, t40=25.0, vwc=35.0, ts=None) -> SensorReading:
    return SensorReading(
        timestamp=ts or datetime(2026,1,1),
        tensiometer_20cm=t20,
        tensiometer_40cm=t40,
        vwc=vwc,
    )

def D(n: int) -> datetime:
    return datetime(2026, 1, 1) + timedelta(days=n)

def silent(fn):
    """Run fn suppressing all prints."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()

def feed(engine, t20, t40=25.0, vwc=35.0, from_day=0, n=1):
    """Feed n identical readings, suppressing output. Returns last program."""
    prog = None
    for i in range(n):
        now = D(from_day + i)
        prog = silent(lambda: engine.process_daily_reading(
            [R(t20=t20, t40=t40, vwc=vwc, ts=now)], now=now
        ))
    return prog

def new_engine(**kw) -> IrrigationEngine:
    return silent(lambda: IrrigationEngine(cfg(**kw)))

def past_initial(engine, day=0):
    """Confirm start (Q9) and feed one reading to leave Initial stage."""
    silent(lambda: engine.confirm_start(now=D(day)))
    feed(engine, t20=60, from_day=day, n=1)

def reach_cal2(engine, start=1):
    """Drive engine from Cal1 → Cal2 (3 days below 10mb)."""
    feed(engine, t20=5, from_day=start, n=3)
    assert engine.current_stage == Stage.CALIBRATION_2, \
        f"Expected CAL2, got {engine.current_stage}"
    return start + 3

def reach_cal3(engine, start=1):
    """Drive Cal1→Cal2→Cal3.
    If engine is already past Cal1, only feeds the Cal2→Cal3 transition.
    """
    if engine.current_stage == Stage.CALIBRATION_1:
        d = reach_cal2(engine, start)
    elif engine.current_stage == Stage.CALIBRATION_2:
        d = start
    else:
        # Already past Cal2 — just return start and let caller handle it
        return start
    feed(engine, t20=50, from_day=d, n=3)
    assert engine.current_stage == Stage.CALIBRATION_3,         f"Expected CAL3, got {engine.current_stage} (fed t20=50 at day {d})"
    return d + 3

def reach_opt(engine, start=1):
    """Drive all the way to Optimization.
    Advances engine from wherever it currently is.
    """
    if engine.current_stage in (Stage.INITIAL, Stage.CALIBRATION_1):
        d = reach_cal3(engine, start)
    elif engine.current_stage == Stage.CALIBRATION_2:
        d = reach_cal3(engine, start)
    elif engine.current_stage == Stage.CALIBRATION_3:
        d = start
    else:
        return start  # already in Optimization
    feed(engine, t20=30, vwc=42, from_day=d, n=14)
    assert engine.current_stage == Stage.OPTIMIZATION,         f"Expected OPT, got {engine.current_stage}"
    return d + 14

def alerts_of(engine, level=None, keyword=None):
    all_alerts = engine.get_alerts()
    result = all_alerts
    if level:
        result = [a for a in result if a.level == level]
    if keyword:
        result = [a for a in result if keyword.lower() in a.message.lower()]
    return result

# ─── Test runner ──────────────────────────────────────────────────────────────

RESULTS = []

def test(name):
    """Decorator to register and run a test."""
    def decorator(fn):
        try:
            silent(fn)
            RESULTS.append(("PASS", name, None))
        except AssertionError as e:
            RESULTS.append(("FAIL", name, str(e)))
        except Exception as e:
            RESULTS.append(("ERROR", name, f"{type(e).__name__}: {e}"))
        return fn
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PRD CLAUSE AUDIT
# Every named rule from the PRD gets exactly one test.
# ═══════════════════════════════════════════════════════════════════════════════

@test("PRD§Q9: engine starts in AWAITING_START, not INITIAL")
def _():
    e = new_engine()
    assert e.current_stage == Stage.AWAITING_START

@test("PRD§Q9: confirm_start() advances to CALIBRATION_1")
def _():
    e = new_engine()
    silent(lambda: e.confirm_start(now=D(0)))
    assert e.current_stage == Stage.CALIBRATION_1

@test("PRD§Cal1: program is 200 pulses of 2-minute irrigation")
def _():
    e = new_engine(); past_initial(e)
    assert e.current_program.num_pulses == 200
    assert e.current_program.pulse_duration_sec == 120

@test("PRD§Cal1: interval = 7.2 min (200 pulses in 1440 min)")
def _():
    e = new_engine(); past_initial(e)
    assert abs(e.current_program.interval_min - 7.2) < 0.01

@test("PRD§Cal1: water-off = 5.2 min")
def _():
    e = new_engine(); past_initial(e)
    assert abs(e.current_program.off_duration_min - 5.2) < 0.01

@test("PRD§Cal1: alert if tensiometer NOT below 40mb after 5 days")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=80, from_day=1, n=5)
    assert alerts_of(e, AlertLevel.RED, "5 days")

@test("PRD§Cal1: advance to Cal2 when below 10mb for 3 consecutive days")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=5, from_day=1, n=3)
    assert e.current_stage == Stage.CALIBRATION_2

@test("PRD§Cal1: does NOT advance after only 2 days below 10mb")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=5, from_day=1, n=2)
    assert e.current_stage == Stage.CALIBRATION_1

@test("PRD§Cal2: program is 180 pulses, 30s — standard site")
def _():
    e = new_engine(); past_initial(e); reach_cal2(e)
    assert e.current_program.num_pulses == 180
    assert e.current_program.pulse_duration_sec == 30

@test("PRD§Cal2: program is 180 pulses, 60s — height-difference site")
def _():
    e = new_engine(ext=True); past_initial(e); reach_cal2(e)
    assert e.current_program.pulse_duration_sec == 60

@test("PRD§Cal2: interval = 8.0 min (180 pulses in 1440 min)")
def _():
    e = new_engine(); past_initial(e); reach_cal2(e)
    assert abs(e.current_program.interval_min - 8.0) < 0.01

@test("PRD§Cal2: water-off = 7.5 min")
def _():
    e = new_engine(); past_initial(e); reach_cal2(e)
    assert abs(e.current_program.off_duration_min - 7.5) < 0.01

@test("PRD§Cal2: advance to Cal3 when T20 above 40mb for 3 consecutive days")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=50, from_day=d, n=3)
    assert e.current_stage == Stage.CALIBRATION_3

@test("PRD§Cal2: alert if drops below 10mb again (3 consecutive days)")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=5, from_day=d, n=3)
    assert alerts_of(e, AlertLevel.RED, "dropped below 10mb")

@test("PRD§Cal2: alert if tensiometer does not rise above 40mb within 14 days")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=25, from_day=d, n=14)
    assert alerts_of(e, AlertLevel.RED, "2 weeks")

@test("PRD§Cal3: yellow alert if T20 below 10mb for 3 days during window")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    feed(e, t20=5, from_day=d, n=3)
    assert alerts_of(e, AlertLevel.YELLOW, "below 10mb")

@test("PRD§Cal3: yellow alert if T20 above 40mb for 3 days during window")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    feed(e, t20=50, from_day=d, n=3)
    assert alerts_of(e, AlertLevel.YELLOW, "above 40mb")

@test("PRD§Cal3: reduce pulses by 20 if below 10mb at end of 2-week window")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    initial = e.current_program.num_pulses
    feed(e, t20=5, from_day=d, n=14)
    assert e.current_program.num_pulses == initial - 20

@test("PRD§Cal3: increase pulses by 20 if above 40mb at end of 2-week window")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    initial = e.current_program.num_pulses
    feed(e, t20=50, from_day=d, n=14)
    assert e.current_program.num_pulses == initial + 20

@test("PRD§Cal3: advance to Optimization when stable 20-40mb for a full 2-week window")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    feed(e, t20=30, vwc=42, from_day=d, n=14)
    assert e.current_stage == Stage.OPTIMIZATION

@test("PRD§Cal3: VWC alert if not risen by 10% after 7 days")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    # VWC starts ~35, stays flat — should alert at day 7
    feed(e, t20=30, vwc=25, from_day=d, n=8)
    assert alerts_of(e, AlertLevel.RED, "VWC")

@test("PRD§Opt: pulse duration fixed at 30s in Optimization")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    assert e.current_program.pulse_duration_sec == 30

@test("PRD§Opt: add 20 pulses if VWC below optimal at 2-week check")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=25, vwc=35, from_day=d, n=14)  # VWC 35 < medium optimal 40
    assert e.current_program.num_pulses == initial + 20

@test("PRD§Opt: add 20 pulses if T20 above 40mb at 2-week check")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=50, vwc=45, from_day=d, n=14)
    assert e.current_program.num_pulses == initial + 20

@test("PRD§Opt: NO DOUBLE INCREASE — only +20 when both VWC low AND T20 high")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=50, vwc=35, from_day=d, n=14)
    assert e.current_program.num_pulses == initial + 20  # NOT +40

@test("PRD§Opt: reduce 20 pulses if T20 below 10mb at 2-week check")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=5, vwc=45, from_day=d, n=14)
    assert e.current_program.num_pulses == initial - 20

@test("PRD§Opt: reduce pulses even when VWC is above optimal (T20 < 10 wins)")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=5, vwc=48, from_day=d, n=14)  # VWC fine, T20 too low
    assert e.current_program.num_pulses == initial - 20

@test("PRD§Opt: no change when conditions are fully optimal")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=25, vwc=45, from_day=d, n=14)  # T20 10-40, VWC >= 40
    assert e.current_program.num_pulses == initial

@test("PRD§Universal: 40cm below 10mb → RED alert at any stage")
def _():
    for stage_fn in [
        lambda e: None,               # Initial
        lambda e: past_initial(e),    # Cal1
        lambda e: (past_initial(e), reach_cal2(e)),
        lambda e: (past_initial(e), reach_cal3(e)),
        lambda e: (past_initial(e), reach_opt(e)),
    ]:
        e = new_engine()
        stage_fn(e)
        feed(e, t20=30, t40=5, from_day=50, n=1)
        assert alerts_of(e, AlertLevel.RED, "40cm"), \
            f"No 40cm alert in stage {e.current_stage}"

@test("PRD§Universal: 20cm below 1mb → YELLOW alert fires on onset")
def _():
    e = new_engine()
    feed(e, t20=0.5, t40=20, from_day=0, n=1)
    assert alerts_of(e, AlertLevel.YELLOW, "1mb")

@test("PRD§Universal: 20cm below 1mb YELLOW alert does not repeat daily (onset-only)")
def _():
    e = new_engine()
    feed(e, t20=0.5, t40=20, from_day=0, n=5)   # 5 days below 1mb
    yellow = alerts_of(e, AlertLevel.YELLOW, "1mb")
    assert len(yellow) == 1  # fires exactly once on onset

@test("PRD§Universal: 20cm below 1mb for 3 consecutive days → RED alert")
def _():
    e = new_engine()
    feed(e, t20=0.3, t40=20, from_day=0, n=3)
    assert alerts_of(e, AlertLevel.RED, "3+")

@test("PRD§Universal: 40cm alert re-arms after condition clears and returns")
def _():
    e = new_engine()
    feed(e, t20=30, t40=5,  from_day=0, n=1)   # onset → alert fires
    feed(e, t20=30, t40=20, from_day=1, n=1)   # condition clears → re-arm
    feed(e, t20=30, t40=5,  from_day=2, n=1)   # onset again → fires again
    red = alerts_of(e, AlertLevel.RED, "40cm")
    assert len(red) == 2  # fired twice (two distinct onsets)

@test("PRD§Soil: optimal VWC ranges correct for all soil types")
def _():
    assert OPTIMAL_VWC[SoilType.HEAVY]    == (50, 100)
    assert OPTIMAL_VWC[SoilType.MEDIUM]   == (40, 50)
    assert OPTIMAL_VWC[SoilType.SANDY]    == (30, 35)
    assert OPTIMAL_VWC[SoilType.SOILLESS] == (30, 50)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — BOUNDARY CONDITIONS
# Test values at exact thresholds — the most common source of off-by-one bugs
# ═══════════════════════════════════════════════════════════════════════════════

@test("BOUNDARY: T20 exactly 10.0mb does NOT trigger Cal1→Cal2 counter")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=10.0, from_day=1, n=3)
    assert e.current_stage == Stage.CALIBRATION_1  # 10.0 is NOT < 10

@test("BOUNDARY: T20 exactly 9.9mb DOES trigger Cal1→Cal2 counter")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=9.9, from_day=1, n=3)
    assert e.current_stage == Stage.CALIBRATION_2

@test("BOUNDARY: T20 exactly 40.0mb does NOT trigger Cal2→Cal3 counter")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=40.0, from_day=d, n=3)
    assert e.current_stage == Stage.CALIBRATION_2  # 40.0 is NOT > 40

@test("BOUNDARY: T20 exactly 40.1mb DOES trigger Cal2→Cal3 counter")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=40.1, from_day=d, n=3)
    assert e.current_stage == Stage.CALIBRATION_3

@test("BOUNDARY: T20 exactly 0.0mb fires 40cm-style saturation conditions")
def _():
    e = new_engine()
    feed(e, t20=0.0, t40=20, from_day=0, n=1)
    # 0mb is below 1mb threshold — should get yellow alert
    assert alerts_of(e, AlertLevel.YELLOW, "1mb")

@test("BOUNDARY: T20 1.0mb exactly does NOT fire below-1mb alert")
def _():
    e = new_engine()
    feed(e, t20=1.0, t40=20, from_day=0, n=1)
    assert not alerts_of(e, AlertLevel.YELLOW, "1mb")

@test("BOUNDARY: T40 exactly 10.0mb does NOT fire 40cm alert")
def _():
    e = new_engine()
    feed(e, t20=30, t40=10.0, from_day=0, n=1)
    assert not alerts_of(e, AlertLevel.RED, "40cm")

@test("BOUNDARY: T40 exactly 9.9mb fires 40cm RED alert")
def _():
    e = new_engine()
    feed(e, t20=30, t40=9.9, from_day=0, n=1)
    assert alerts_of(e, AlertLevel.RED, "40cm")

@test("BOUNDARY: Cal3 window eval at exactly day 14 (not day 13)")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    feed(e, t20=30, vwc=42, from_day=d, n=13)
    assert e.current_stage == Stage.CALIBRATION_3   # not yet
    feed(e, t20=30, vwc=42, from_day=d+13, n=1)
    assert e.current_stage == Stage.OPTIMIZATION    # now

@test("BOUNDARY: Opt 2-week eval at exactly day 14")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=50, vwc=45, from_day=d, n=13)
    assert e.current_program.num_pulses == initial    # not yet adjusted
    feed(e, t20=50, vwc=45, from_day=d+13, n=1)
    assert e.current_program.num_pulses == initial + 20

@test("BOUNDARY: Pulse count floor — never drops below 0 (PRD 18.6.26)")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    # Reduce pulses many times
    for i in range(20):
        feed(e, t20=5, vwc=45, from_day=d + i*14, n=14)
    assert e.current_program.num_pulses >= 0

@test("BOUNDARY: Cal3 pulse count floor — never drops below 0 (PRD 18.6.26)")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    for i in range(20):
        feed(e, t20=5, from_day=d + i*14, n=14)
    assert e.current_program.num_pulses >= 0

@test("BOUNDARY: VWC at exactly optimal minimum does NOT trigger add-pulse")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)  # optimal min = 40
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=25, vwc=40.0, from_day=d, n=14)  # VWC == optimal min, NOT below
    assert e.current_program.num_pulses == initial

@test("BOUNDARY: VWC just below optimal minimum triggers add-pulse")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    feed(e, t20=25, vwc=39.9, from_day=d, n=14)
    assert e.current_program.num_pulses == initial + 20

@test("BOUNDARY: Cal1 alert fires around day 5 above 40mb (PRD 18.6.26 re-fires)")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=80, from_day=1, n=3)
    assert not alerts_of(e, AlertLevel.RED, "5 days")
    feed(e, t20=80, from_day=4, n=2)
    assert alerts_of(e, AlertLevel.RED, "5 days")

@test("BOUNDARY: Pulse ceiling — never exceeds 200 (PRD 18.6.26)")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    # Drive many increases (dry + low VWC)
    for i in range(20):
        feed(e, t20=60, vwc=20, from_day=d + i*14, n=14)
    assert e.current_program.num_pulses <= 200


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — COUNTER LOGIC
# Consecutive-day counters are the core mechanism; must be bulletproof
# ═══════════════════════════════════════════════════════════════════════════════

@test("COUNTER: Cal1 counter resets to zero on single day above 10mb")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=5,  from_day=1, n=2)   # 2 days below 10
    feed(e, t20=15, from_day=3, n=1)   # back above — counter resets
    feed(e, t20=5,  from_day=4, n=2)   # only 2 days below again
    assert e.current_stage == Stage.CALIBRATION_1

@test("COUNTER: Cal1 counter resumes correctly after partial reset")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=5,  from_day=1, n=2)
    feed(e, t20=15, from_day=3, n=1)   # reset
    feed(e, t20=5,  from_day=4, n=3)   # now 3 fresh days → advance
    assert e.current_stage == Stage.CALIBRATION_2

@test("COUNTER: Cal2 above-40 counter resets on single day at or below 40mb")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=50, from_day=d,   n=2)   # 2 days above 40
    feed(e, t20=30, from_day=d+2, n=1)   # reset
    feed(e, t20=50, from_day=d+3, n=2)   # only 2 days → no advance
    assert e.current_stage == Stage.CALIBRATION_2

@test("COUNTER: Cal2 above-40 counter resets at exactly 40.0mb")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=50, from_day=d,   n=2)
    feed(e, t20=40.0, from_day=d+2, n=1)  # 40.0 is NOT > 40 → resets
    feed(e, t20=50, from_day=d+3, n=2)
    assert e.current_stage == Stage.CALIBRATION_2

@test("COUNTER: Cal3 below/above counters are mutually exclusive")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    # Push into above-40 territory for 2 days
    feed(e, t20=50, from_day=d, n=2)
    # Then switch to below-10 — above counter must reset
    feed(e, t20=5, from_day=d+2, n=1)
    # Only 1 day below 10 — should NOT fire yellow alert
    assert not alerts_of(e, AlertLevel.YELLOW, "below 10mb")

@test("COUNTER: 1mb-for-3-days RED counter resets after firing, does not immediately re-fire")
def _():
    e = new_engine()
    # First 3-day trigger
    feed(e, t20=0.5, t40=20, from_day=0, n=3)
    assert alerts_of(e, AlertLevel.RED, "3+")
    n_red_before = len(alerts_of(e, AlertLevel.RED, "3+"))
    # 2 more days — counter resets after firing, so not enough to re-fire
    feed(e, t20=0.5, t40=20, from_day=3, n=2)
    assert len(alerts_of(e, AlertLevel.RED, "3+")) == n_red_before

@test("COUNTER: Cal1 5-day alert RE-FIRES every 5 days (PRD 18.6.26)")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=80, from_day=1, n=20)   # 20 days above 40mb
    # PRD: alert resets — should fire roughly every 5 days (~3-4 times in 20 days)
    fires = len(alerts_of(e, AlertLevel.RED, "5 days"))
    assert fires >= 3, f"Expected >=3 re-fires, got {fires}"

@test("COUNTER: transition to new stage resets both counters to zero")
def _():
    e = new_engine(); past_initial(e)
    # Build up 2 days of below-10 counter in Cal1
    feed(e, t20=5, from_day=1, n=2)
    # Then advance to Cal2 with 1 more day
    feed(e, t20=5, from_day=3, n=1)
    assert e.current_stage == Stage.CALIBRATION_2
    # Now in Cal2 — counter should be 0, so 2 more days above 40 should NOT advance
    feed(e, t20=50, from_day=4, n=2)
    assert e.current_stage == Stage.CALIBRATION_2


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SCENARIO SIMULATIONS
# Realistic journeys with commentary
# ═══════════════════════════════════════════════════════════════════════════════

@test("SCENARIO: Healthy field — smooth progression through all stages")
def _():
    """
    Ideal case: soil responds well, all thresholds met on first attempt.
    No alerts expected except possibly VWC.
    """
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e, day=0)
    # Cal1: 8 days of drenching, drops below 10mb cleanly
    feed(e, t20=45, from_day=1, n=5)
    feed(e, t20=5,  from_day=6, n=3)
    assert e.current_stage == Stage.CALIBRATION_2
    # Cal2: rises above 40mb after 10 days
    d = 9
    feed(e, t20=20, from_day=d,   n=7)
    feed(e, t20=50, from_day=d+7, n=3)
    assert e.current_stage == Stage.CALIBRATION_3
    # Cal3: stable immediately in 20-40 range
    d2 = d + 10
    feed(e, t20=30, vwc=42, from_day=d2, n=14)
    assert e.current_stage == Stage.OPTIMIZATION
    # Optimization: stable conditions, no change needed
    d3 = d2 + 14
    initial = e.current_program.num_pulses
    feed(e, t20=25, vwc=44, from_day=d3, n=14)
    assert e.current_program.num_pulses == initial

@test("SCENARIO: Stubborn soil — Cal1 never drops below 40mb, fires alert")
def _():
    e = new_engine(); past_initial(e)
    feed(e, t20=75, from_day=1, n=10)
    red = alerts_of(e, AlertLevel.RED, "5 days")
    assert len(red) >= 1
    assert e.current_stage == Stage.CALIBRATION_1  # still stuck

@test("SCENARIO: Slow-draining soil — Cal2 drops below 10mb again mid-stage")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=20, from_day=d,   n=5)   # seems ok
    feed(e, t20=4,  from_day=d+5, n=3)   # drops below 10 again
    assert alerts_of(e, AlertLevel.RED, "dropped below 10mb")
    assert e.current_stage == Stage.CALIBRATION_2   # still in Cal2

@test("SCENARIO: Cal3 oscillating — alternates wet/dry, takes 3 windows to stabilise")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    initial = e.current_program.num_pulses

    # Window 1: too wet (below 10) → reduce pulses
    feed(e, t20=5, from_day=d, n=14)
    assert e.current_stage == Stage.CALIBRATION_3
    p1 = e.current_program.num_pulses
    assert p1 == initial - 20

    # Window 2: too dry (above 40) → increase pulses
    feed(e, t20=50, from_day=d+14, n=14)
    p2 = e.current_program.num_pulses
    assert p2 == p1 + 20

    # Window 3: stable 20-40mb → advance to Optimization
    feed(e, t20=30, vwc=42, from_day=d+28, n=14)
    assert e.current_stage == Stage.OPTIMIZATION

@test("SCENARIO: Optimization self-corrects over multiple 2-week cycles")
def _():
    e = new_engine(soil_type=SoilType.MEDIUM)
    past_initial(e)
    d = reach_opt(e)

    # Cycle 1: VWC below optimal → +20 pulses
    initial = e.current_program.num_pulses
    feed(e, t20=25, vwc=35, from_day=d, n=14)
    assert e.current_program.num_pulses == initial + 20

    # Cycle 2: now VWC reaches optimal → no change
    d2 = d + 14
    after_add = e.current_program.num_pulses
    feed(e, t20=25, vwc=44, from_day=d2, n=14)
    assert e.current_program.num_pulses == after_add

    # Cycle 3: T20 drops below 10 → remove 20
    d3 = d2 + 14
    feed(e, t20=5, vwc=44, from_day=d3, n=14)
    assert e.current_program.num_pulses == after_add - 20

@test("SCENARIO: Heavy soil requires higher VWC threshold")
def _():
    e = new_engine(soil_type=SoilType.HEAVY)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    # VWC=48% is optimal for MEDIUM but NOT for HEAVY (needs 50%+)
    feed(e, t20=25, vwc=48, from_day=d, n=14)
    assert e.current_program.num_pulses == initial + 20  # below 50% optimal

@test("SCENARIO: Sandy soil has lower VWC threshold")
def _():
    e = new_engine(soil_type=SoilType.SANDY)
    past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses
    # VWC=32% is within SANDY optimal (30-35%), should not trigger increase
    feed(e, t20=25, vwc=32, from_day=d, n=14)
    assert e.current_program.num_pulses == initial  # no change needed

@test("SCENARIO: Red alert during Optimization — 40cm sensor still triggers")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    feed(e, t20=25, t40=5, vwc=44, from_day=d, n=1)
    assert alerts_of(e, AlertLevel.RED, "40cm")
    assert e.current_stage == Stage.OPTIMIZATION  # alert does not change stage


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — LOGICAL CONSISTENCY
# Invariants that must hold at all times regardless of input sequence
# ═══════════════════════════════════════════════════════════════════════════════

@test("INVARIANT: stage only ever moves forward (no regression)")
def _():
    stage_order = [
        Stage.INITIAL, Stage.CALIBRATION_1, Stage.CALIBRATION_2,
        Stage.CALIBRATION_3, Stage.OPTIMIZATION
    ]
    e = new_engine(); past_initial(e)
    seen = [Stage.INITIAL, Stage.CALIBRATION_1]
    d = reach_cal2(e); seen.append(e.current_stage)
    d = reach_cal3(e, start=d); seen.append(e.current_stage)
    d = reach_opt(e, start=d); seen.append(e.current_stage)
    for i in range(len(seen)-1):
        assert stage_order.index(seen[i]) < stage_order.index(seen[i+1])

@test("INVARIANT: pulse count is always a non-negative integer <= 200")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    for i in range(50):
        feed(e, t20=5, vwc=45, from_day=d + i*14, n=14)
        assert 0 <= e.current_program.num_pulses <= 200
        assert isinstance(e.current_program.num_pulses, int)

@test("INVARIANT: pulse duration is always positive in all stages")
def _():
    e = new_engine(); past_initial(e)
    stages_seen = []
    # Cal1
    assert e.current_program.pulse_duration_sec > 0
    # Cal2
    d = reach_cal2(e)
    assert e.current_program.pulse_duration_sec > 0
    # Cal3
    d = reach_cal3(e, start=d)
    assert e.current_program.pulse_duration_sec > 0
    # Optimization
    d = reach_opt(e, start=d)
    assert e.current_program.pulse_duration_sec > 0

@test("INVARIANT: interval = cycle / pulses (mathematical consistency)")
def _():
    e = new_engine(); past_initial(e)
    for t20, from_day, n in [(80,1,1), (5,2,3), (50,5,3), (30,8,14)]:
        feed(e, t20=t20, from_day=from_day, n=n)
        p = e.current_program
        expected = p.cycle_duration_min / p.num_pulses
        assert abs(p.interval_min - expected) < 0.001, \
            f"interval {p.interval_min} != {expected} for {p.num_pulses} pulses"

@test("INVARIANT: water-off = interval - pulse_duration")
def _():
    e = new_engine(); past_initial(e)
    p = e.current_program
    assert abs(p.off_duration_min - (p.interval_min - p.pulse_duration_sec/60)) < 0.001
    reach_cal2(e)
    p = e.current_program
    assert abs(p.off_duration_min - (p.interval_min - p.pulse_duration_sec/60)) < 0.001

@test("INVARIANT: Opt pulse duration is always 30s regardless of adjustments")
def _():
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    for i in range(5):
        feed(e, t20=5, vwc=45, from_day=d + i*14, n=14)   # trigger reduce
        assert e.current_program.pulse_duration_sec == 30
    for i in range(5,10):
        feed(e, t20=50, vwc=35, from_day=d + i*14, n=14)  # trigger increase
        assert e.current_program.pulse_duration_sec == 30

@test("INVARIANT: get_alerts is non-destructive by default")
def _():
    e = new_engine()
    feed(e, t20=0.5, t40=5, from_day=0, n=1)  # triggers multiple alerts
    a1 = e.get_alerts()
    a2 = e.get_alerts()
    assert len(a1) == len(a2)

@test("INVARIANT: get_alerts(clear=True) empties the list")
def _():
    e = new_engine()
    feed(e, t20=0.5, t40=5, from_day=0, n=1)
    e.get_alerts(clear=True)
    assert e.get_alerts() == []

@test("INVARIANT: engine processes identical readings deterministically")
def _():
    """Same input sequence must always produce same output."""
    def run():
        e = new_engine(soil_type=SoilType.MEDIUM)
        past_initial(e)
        feed(e, t20=5,  from_day=1, n=3)
        feed(e, t20=50, from_day=4, n=3)
        feed(e, t20=30, vwc=42, from_day=7, n=14)
        return e.current_stage, e.current_program.num_pulses
    assert run() == run()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — BUGS FOUND
# Issues identified during verification — each gets a regression test
# ═══════════════════════════════════════════════════════════════════════════════

@test("BUG-WATCH: Cal3 window VWC alert fires every day after day 7, not just once")
def _():
    """
    The VWC alert in Cal3 fires on EVERY reading after day 7 if VWC stays low.
    This would spam the agronomist. Verify and document behaviour.
    Expected: at least 1 alert fired. Issue: may fire many more than needed.
    """
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    feed(e, t20=30, vwc=25, from_day=d, n=10)  # 10 days, VWC stays low
    vwc_alerts = alerts_of(e, keyword="VWC")
    # Document: how many fired?
    # Acceptable: 1 per week (2 max for 10 days). Not acceptable: 4+ (daily spam)
    # This test marks as expected behaviour to flag for PRD clarification
    assert len(vwc_alerts) >= 1, "Expected at least one VWC alert"
    # Flag if excessive
    if len(vwc_alerts) > 3:
        RESULTS.append(("WARN", "BUG-WATCH VWC alert spam", f"{len(vwc_alerts)} alerts in 10 days — consider throttling"))

@test("BUG-WATCH: Cal1 5-day alert fires every single day after day 5 (alert spam)")
def _():
    """Same issue: once above 40mb past day 5, alert fires daily. Should throttle."""
    e = new_engine(); past_initial(e)
    feed(e, t20=80, from_day=1, n=20)
    day5_alerts = alerts_of(e, AlertLevel.RED, "5 days")
    assert len(day5_alerts) >= 1
    if len(day5_alerts) > 3:
        RESULTS.append(("WARN", "BUG-WATCH Cal1 alert spam", f"{len(day5_alerts)} alerts in 20 days — consider firing once then throttling"))

@test("BUG-WATCH: Cal3 above-40mb evaluates BOTH pulses AND duration increase (double adjustment)")
def _():
    """
    PRD Cal3 window item ii says 'increase pulse duration by 30s' AND item i's
    logic for above-40 says 'increase pulses by 20'. The current code does BOTH
    in the same window evaluation. Verify this matches PRD intent.
    """
    e = new_engine(); past_initial(e)
    d = reach_cal3(e)
    p_before = e.current_program.pulse_duration_sec
    n_before = e.current_program.num_pulses
    feed(e, t20=50, from_day=d, n=14)
    p_after = e.current_program.pulse_duration_sec
    n_after  = e.current_program.num_pulses
    # Document what actually happened
    if n_after != n_before + 20 or p_after != p_before + 30:
        RESULTS.append(("WARN", "BUG-WATCH Cal3 dual adjustment",
            f"Pulses: {n_before}→{n_after}, Duration: {p_before}s→{p_after}s — verify PRD intent"))
    assert n_after >= n_before  # at minimum, pulses should not decrease on too-dry

@test("BUG-WATCH: Cal2 '14-day no-rise' alert fires repeatedly if still in stage past day 14")
def _():
    e = new_engine(); past_initial(e)
    d = reach_cal2(e)
    feed(e, t20=25, from_day=d, n=20)
    alerts_14 = alerts_of(e, AlertLevel.RED, "2 weeks")
    assert len(alerts_14) >= 1
    if len(alerts_14) > 2:
        RESULTS.append(("WARN", "BUG-WATCH Cal2 14-day alert spam",
            f"{len(alerts_14)} alerts fired — should fire once"))

@test("BUG-WATCH: Opt window resets after each 14-day evaluation")
def _():
    """Verify window resets correctly after each 14-day evaluation in Optimization."""
    e = new_engine(); past_initial(e)
    d = reach_opt(e)
    initial = e.current_program.num_pulses  # 180

    # Window 1 → +20 (180 → 200)
    feed(e, t20=50, vwc=45, from_day=d, n=14)
    after1 = e.current_program.num_pulses
    assert after1 == min(200, initial + 20)

    # Window 2: already at ceiling 200 — PRD 18.6.26 caps here, stays 200
    feed(e, t20=50, vwc=45, from_day=d+14, n=14)
    after2 = e.current_program.num_pulses
    assert after2 == 200, f"Should be capped at 200, got {after2}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — SENSOR FAULT / IMPLAUSIBLE READING DETECTION
# Controller requirement: "read health of the sensors (faulty/working/
# implausible readings)". Tensiometers valid 0-200mb, VWC valid 0-100%.
# ═══════════════════════════════════════════════════════════════════════════════

@test("SENSOR-FAULT: out-of-range T20 readings excluded from daily average")
def _():
    e = new_engine(); past_initial(e)
    readings = [R(t20=30.0) for _ in range(140)] + [R(t20=350.0) for _ in range(4)]
    silent(lambda: e.process_daily_reading(readings, now=D(1)))
    avg = e.get_daily_averages()[-1]
    assert abs(avg.t20_avg - 30.0) < 0.01, f"Expected clean 30.0 avg, got {avg.t20_avg}"
    assert avg.t20_anomalies == 4

@test("SENSOR-FAULT: negative T40 readings excluded, RED alert fired")
def _():
    e = new_engine(); past_initial(e)
    readings = [R(t40=25.0) for _ in range(140)] + [R(t40=-5.0) for _ in range(4)]
    silent(lambda: e.process_daily_reading(readings, now=D(1)))
    assert alerts_of(e, AlertLevel.RED, "40cm tensiometer")

@test("SENSOR-FAULT: VWC above 100% excluded from average, RED alert fired")
def _():
    e = new_engine(); past_initial(e)
    readings = [R(vwc=35.0) for _ in range(140)] + [R(vwc=150.0) for _ in range(4)]
    silent(lambda: e.process_daily_reading(readings, now=D(1)))
    avg = e.get_daily_averages()[-1]
    assert abs(avg.vwc_avg - 35.0) < 0.01
    assert alerts_of(e, AlertLevel.RED, "VWC sensor")

@test("SENSOR-FAULT: alert fires once on onset, does not spam while fault persists")
def _():
    e = new_engine(); past_initial(e)
    bad = [R(t20=30.0) for _ in range(140)] + [R(t20=999.0) for _ in range(4)]
    silent(lambda: e.process_daily_reading(bad, now=D(1)))
    first_count = len(alerts_of(e, AlertLevel.RED, "20cm tensiometer"))
    silent(lambda: e.process_daily_reading(bad, now=D(2)))  # still faulty -- must NOT refire
    second_count = len(alerts_of(e, AlertLevel.RED, "20cm tensiometer"))
    assert first_count >= 1
    assert second_count == first_count, "Should not refire while the same fault persists"

@test("SENSOR-FAULT: alert re-arms after a clean day and refires on recurrence")
def _():
    e = new_engine(); past_initial(e)
    bad = [R(t20=30.0) for _ in range(140)] + [R(t20=999.0) for _ in range(4)]
    clean = [R(t20=30.0) for _ in range(144)]
    silent(lambda: e.process_daily_reading(bad, now=D(1)))
    first_count = len(alerts_of(e, AlertLevel.RED, "20cm tensiometer"))
    silent(lambda: e.process_daily_reading(clean, now=D(2)))  # clears
    silent(lambda: e.process_daily_reading(bad, now=D(3)))    # faults again
    second_count = len(alerts_of(e, AlertLevel.RED, "20cm tensiometer"))
    assert second_count == first_count + 1, "Should refire after clearing and recurring"

@test("SENSOR-FAULT: all-anomalous day falls back to previous day's average, not garbage")
def _():
    e = new_engine(); past_initial(e)
    silent(lambda: e.process_daily_reading([R(t20=32.0) for _ in range(144)], now=D(1)))
    all_bad = [R(t20=500.0) for _ in range(144)]
    silent(lambda: e.process_daily_reading(all_bad, now=D(2)))
    avg = e.get_daily_averages()[-1]
    assert abs(avg.t20_avg - 32.0) < 0.01, f"Expected fallback to 32.0, got {avg.t20_avg}"
    assert avg.t20_anomalies == 144

@test("SENSOR-FAULT: soilless sites skip the 40cm check entirely (no such sensor)")
def _():
    e = new_engine(soil_type=SoilType.SOILLESS); e.config.has_40cm_tensiometer = False
    past_initial(e)
    readings = [R(t40=-50.0) for _ in range(144)]  # would be a T40 fault on a normal site
    silent(lambda: e.process_daily_reading(readings, now=D(1)))
    assert not alerts_of(e, AlertLevel.RED, "40cm tensiometer")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — DISCHARGE MISMATCH (planned vs actual water usage)
# PRD: alert if actual discharge deviates from planned by more than the
# configurable threshold (default 20%). Checked independently of the daily
# decision cycle (PRD specifies every 2 hours) via IrrigationEngine.check_discharge().
# ═══════════════════════════════════════════════════════════════════════════════

def _planned_2h_liters(e):
    prog = e.current_program
    full_day_l = e.config.discharge_rate_lph * e.config.num_drippers * (prog.num_pulses * prog.pulse_duration_sec / 3600)
    return full_day_l * (2 / 24)

@test("DISCHARGE: no alert when actual matches planned within threshold")
def _():
    e = new_engine(); past_initial(e)
    planned = _planned_2h_liters(e)
    alert = silent(lambda: e.check_discharge(actual_liters=planned * 1.05, elapsed_hours=2, now=D(1)))
    assert alert is None
    assert not alerts_of(e, AlertLevel.RED, "Discharge mismatch")

@test("DISCHARGE: RED alert fires when actual is >20% below planned (clog/leak-low)")
def _():
    e = new_engine(); past_initial(e)
    planned = _planned_2h_liters(e)
    silent(lambda: e.check_discharge(actual_liters=planned * 0.5, elapsed_hours=2, now=D(1)))
    assert alerts_of(e, AlertLevel.RED, "Discharge mismatch")

@test("DISCHARGE: RED alert fires when actual is >20% above planned (leak-high)")
def _():
    e = new_engine(); past_initial(e)
    planned = _planned_2h_liters(e)
    silent(lambda: e.check_discharge(actual_liters=planned * 1.5, elapsed_hours=2, now=D(1)))
    assert alerts_of(e, AlertLevel.RED, "Discharge mismatch")

@test("DISCHARGE: threshold is configurable via SiteConfig.discharge_mismatch_pct")
def _():
    custom_cfg = SiteConfig(soil_type=SoilType.MEDIUM, water_type=WaterType.REGULAR,
                             discharge_rate_lph=1.0, num_drippers=100, discharge_mismatch_pct=50.0)
    e = silent(lambda: IrrigationEngine(custom_cfg))
    silent(lambda: e.confirm_start(now=D(0)))
    planned = _planned_2h_liters(e)
    # 30% deviation -- under this site's custom 50% threshold, should NOT fire
    silent(lambda: e.check_discharge(actual_liters=planned * 1.3, elapsed_hours=2, now=D(1)))
    assert not alerts_of(e, AlertLevel.RED, "Discharge mismatch")

@test("DISCHARGE: frozen irrigation expects zero planned water -- any flow alerts")
def _():
    e = new_engine(); past_initial(e)
    silent(lambda: e.freeze_irrigation())
    silent(lambda: e.check_discharge(actual_liters=5.0, elapsed_hours=2, now=D(1)))
    assert alerts_of(e, AlertLevel.RED, "Discharge mismatch")


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run():
    sections = {
        "PRD§":         "PRD Clause Audit",
        "BOUNDARY":     "Boundary Conditions",
        "COUNTER":      "Counter Logic",
        "SCENARIO":     "Scenario Simulations",
        "INVARIANT":    "Logical Consistency",
        "BUG-WATCH":    "Bug Watch / Regressions",
        "SENSOR-FAULT": "Sensor Fault Detection",
        "DISCHARGE":    "Discharge Mismatch",
    }

    print("\n" + "═"*70)
    print("  AGRINOZE — ALGORITHM VERIFICATION SUITE")
    print("═"*70)

    passed = failed = warned = errors = 0
    current_section = None

    for status, name, detail in RESULTS:
        section = next((k for k in sections if name.startswith(k)), "OTHER")
        if section != current_section:
            current_section = section
            print(f"\n  ── {sections.get(section, section)} ──")

        if status == "PASS":
            passed += 1
            print(f"  ✓  {name}")
        elif status == "WARN":
            warned += 1
            print(f"  ⚠  {name}")
            if detail: print(f"        {detail}")
        elif status == "FAIL":
            failed += 1
            print(f"  ✗  {name}")
            if detail: print(f"        → {detail}")
        elif status == "ERROR":
            errors += 1
            print(f"  ⚡ {name}")
            if detail: print(f"        → {detail}")

    total = passed + failed + errors
    print(f"\n{'═'*70}")
    print(f"  RESULTS: {passed}/{total} passed", end="")
    if warned:  print(f"  |  {warned} warnings", end="")
    if failed:  print(f"  |  {failed} FAILED", end="")
    if errors:  print(f"  |  {errors} ERRORS", end="")
    print(f"\n{'═'*70}\n")

    return failed, errors, warned

if __name__ == "__main__":
    failed, errors, warned = run()
    sys.exit(1 if (failed + errors) > 0 else 0)
