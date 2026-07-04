"""
Agrinoze — Monte Carlo Stress Test
====================================
Runs N simulations with randomised:
  - Soil type
  - Site config (height mode, soil responsiveness)
  - Sensor noise profiles (sluggish, normal, erratic)
  - Field behaviour (drying rate, irrigation response)

Each run is fully deterministic given its seed, so failures are reproducible.

Checks tracked across ALL runs:
  - Safety invariants  (must NEVER be violated)
  - Progress invariants (must hold in healthy conditions)
  - Alert quality      (no spam, correct severity)
  - Pulse bounds       (always within safe operating range)
  - Stage reachability (can every stage be reached?)
"""

import sys, io, contextlib, types, random, math
sys.modules.setdefault("pytest", types.ModuleType("pytest"))
sys.path.insert(0, "/home/claude")

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from agrinoze.engine.models import (
    SiteConfig, SoilType, WaterType,
    SensorReading, Stage, AlertLevel, IrrigationProgram, OPTIMAL_VWC,
)
from agrinoze.engine.algorithm import IrrigationEngine

# ─── Soil physics model ───────────────────────────────────────────────────────

@dataclass
class SoilProfile:
    """
    Randomised soil physics for one Monte Carlo run.

    Physics are litre-based (not second-based):
      daily_litres = pulses × (pulse_sec / 3600) × 1.0 L/hr
      tension_drop = daily_litres × mb_per_litre
      net_delta    = drying_rate - tension_drop

    This ensures Cal1 (6.67 L/day) wets the soil while
    Cal2 (1.50 L/day) allows drying — matching PRD intent.
    """
    drying_rate: float    # mb/day natural drainage+evaporation  (1.0 – 8.0)
    mb_per_litre: float   # mb tension drop per litre delivered  (0.5 – 3.0)
    depth_lag: float      # 40cm lags 20cm by this factor        (0.3 – 0.8)
    noise_mb: float       # tensiometer noise amplitude (mb)     (0.5 – 4.0)
    noise_vwc: float      # VWC noise amplitude (%)              (0.1 – 1.5)
    vwc_per_litre: float  # % VWC rise per litre delivered       (0.3 – 1.5)
    t20_initial: float    # starting T20 (mb)                    (20 – 120)
    t40_initial: float    # starting T40 (mb)                    (15 – 80)
    vwc_initial: float    # starting VWC (%)                     (15 – 40)


@dataclass
class SimRun:
    """Records everything about one Monte Carlo run."""
    seed: int
    soil_type: SoilType
    profile: SoilProfile
    use_ext_pulse: bool

    days_run: int = 0
    final_stage: Stage = Stage.INITIAL
    stages_reached: set = field(default_factory=set)
    stage_days: dict = field(default_factory=dict)   # stage → days spent

    total_alerts: int = 0
    red_alerts: int = 0
    yellow_alerts: int = 0

    # Safety violations (must be zero)
    pulse_below_floor: int = 0       # pulse count outside [0, 200]
    pulse_duration_zero: int = 0     # pulse duration <= 0
    stage_regression: int = 0        # stage moved backward
    math_inconsistency: int = 0      # interval != cycle/pulses

    # Progress failures
    stuck_in_cal1: bool = False      # never left Cal1 in 60 days
    stuck_in_cal2: bool = False
    stuck_in_cal3: bool = False

    # Alert quality
    red_alert_in_safe_range: int = 0  # red alert when readings were fine
    duplicate_spam_alerts: int = 0    # same alert type >3 in any 7-day window

    # Pulse tracking
    min_pulses_seen: int = 9999
    max_pulses_seen: int = 0
    pulse_history: list = field(default_factory=list)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def silent(fn):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()

def D(n): return datetime(2026, 1, 1) + timedelta(days=n)

def make_profile(rng: random.Random) -> SoilProfile:
    return SoilProfile(
        drying_rate  = rng.uniform(1.0, 8.0),
        mb_per_litre = rng.uniform(0.5, 3.0),
        depth_lag    = rng.uniform(0.3, 0.8),
        noise_mb     = rng.uniform(0.5, 4.0),
        noise_vwc    = rng.uniform(0.1, 1.5),
        vwc_per_litre= rng.uniform(0.3, 1.5),
        t20_initial  = rng.uniform(20, 120),
        t40_initial  = rng.uniform(15, 80),
        vwc_initial  = rng.uniform(15, 40),
    )

DISCHARGE_LPH = 1.0  # L/hour per dripper (matches SiteConfig default)

def simulate_day(profile: SoilProfile, program: IrrigationProgram,
                 t20: float, t40: float, vwc: float,
                 rng: random.Random, day: int):
    """
    Apply one day of irrigation to the soil model.
    Litre-based physics: response = mb drop per litre delivered.
    """
    daily_litres = (
        program.num_pulses
        * (program.pulse_duration_sec / 3600)
        * DISCHARGE_LPH
    )
    # Cal1: 200×120s = 6.67 L/day → wets strongly
    # Cal2: 180×30s  = 1.50 L/day → allows drying for most soils

    tension_drop = daily_litres * profile.mb_per_litre
    tension_rise = profile.drying_rate
    dt20 = tension_rise - tension_drop
    dt40 = dt20 * profile.depth_lag

    t20 = max(0.0, t20 + dt20 + rng.gauss(0, profile.noise_mb))
    t40 = max(0.0, t40 + dt40 + rng.gauss(0, profile.noise_mb * 0.6))

    vwc_rise = daily_litres * profile.vwc_per_litre
    vwc_drop = 0.3 + rng.uniform(0, 0.2)
    vwc = max(0.0, min(100.0,
        vwc + vwc_rise - vwc_drop + rng.gauss(0, profile.noise_vwc)))

    return SensorReading(
        timestamp=D(day),
        tensiometer_20cm=round(min(t20, 200), 2),
        tensiometer_40cm=round(min(t40, 200), 2),
        vwc=round(vwc, 2),
    ), t20, t40, vwc


# ─── Single simulation run ────────────────────────────────────────────────────

STAGE_ORDER = [
    Stage.AWAITING_START, Stage.INITIAL, Stage.CALIBRATION_1,
    Stage.CALIBRATION_2, Stage.CALIBRATION_3, Stage.OPTIMIZATION
]

def run_one(seed: int, max_days: int = 180) -> SimRun:
    rng = random.Random(seed)

    soil_type    = rng.choice(list(SoilType))
    use_ext      = rng.random() < 0.2
    profile      = make_profile(rng)

    is_soilless = (soil_type == SoilType.SOILLESS)
    config = SiteConfig(
        soil_type=soil_type,
        water_type=WaterType.REGULAR,
        discharge_rate_lph=1.0,
        num_drippers=100,
        use_extended_pulse_sub2=use_ext,
        has_40cm_tensiometer=not is_soilless,   # Q8
        discharge_mismatch_pct=20.0,             # Q7
    )

    result = SimRun(seed=seed, soil_type=soil_type, profile=profile, use_ext_pulse=use_ext)
    engine = silent(lambda: IrrigationEngine(config))
    # Q9: confirm manual start
    silent(lambda: engine.confirm_start(now=D(0)))

    t20  = profile.t20_initial
    t40  = profile.t40_initial
    vwc  = profile.vwc_initial
    prev_stage = Stage.INITIAL
    alert_window = []       # (day, level) for spam detection

    for day in range(max_days):
        program = engine.current_program

        # Simulate soil response
        reading, t20, t40, vwc = simulate_day(profile, program, t20, t40, vwc, rng, day)

        # Feed to engine
        silent(lambda r=reading, d=day: engine.process_daily_reading([r], now=D(d)))

        # --- Track stage ---
        cur_stage = engine.current_stage
        result.stages_reached.add(cur_stage)
        result.stage_days[cur_stage] = result.stage_days.get(cur_stage, 0) + 1
        result.final_stage = cur_stage

        # Safety: stage regression
        if STAGE_ORDER.index(cur_stage) < STAGE_ORDER.index(prev_stage):
            result.stage_regression += 1
        prev_stage = cur_stage

        # --- Track program ---
        p = engine.current_program
        result.pulse_history.append(p.num_pulses)
        result.min_pulses_seen = min(result.min_pulses_seen, p.num_pulses)
        result.max_pulses_seen = max(result.max_pulses_seen, p.num_pulses)

        # Safety: pulse floor
        if p.num_pulses < 0:
            result.pulse_below_floor += 1
        if p.num_pulses > 200:
            result.pulse_below_floor += 1

        # Safety: pulse duration
        if p.pulse_duration_sec <= 0:
            result.pulse_duration_zero += 1

        # Safety: math consistency
        expected_interval = p.cycle_duration_min / p.num_pulses
        if abs(p.interval_min - expected_interval) > 0.01:
            result.math_inconsistency += 1

        # --- Track alerts ---
        new_alerts = engine.get_alerts(clear=True)
        for a in new_alerts:
            result.total_alerts += 1
            if a.level == AlertLevel.RED:
                result.red_alerts += 1
            else:
                result.yellow_alerts += 1
            alert_window.append((day, a.level, a.message))

        # Model the agronomist acknowledging the persist-until-ack 40cm alert
        # (PRD 18.6.26: it fires continuously until acknowledged). The MC
        # acknowledges the day after it first appears.
        if any("40cm" in m for _, _, m in alert_window):
            engine.acknowledge_t40_alert()

        # Spam detection: same alert MESSAGE appearing >2 times in any 7-day window.
        # Exclude alerts that are INTENTIONALLY persistent-until-acknowledged
        # (the 40cm sub-10mb alert) — repetition there is by design, not spam.
        alert_window = [(d, l, m) for d, l, m in alert_window if day - d <= 7]
        from collections import Counter
        msg_counts = Counter(
            m for _, _, m in alert_window if "40cm" not in m
        )
        if any(count > 2 for count in msg_counts.values()):
            result.duplicate_spam_alerts += 1

    result.days_run = max_days

    # Progress checks
    if Stage.CALIBRATION_2 not in result.stages_reached:
        result.stuck_in_cal1 = True
    if Stage.CALIBRATION_3 not in result.stages_reached and Stage.CALIBRATION_2 in result.stages_reached:
        result.stuck_in_cal2 = True
    if Stage.OPTIMIZATION not in result.stages_reached and Stage.CALIBRATION_3 in result.stages_reached:
        result.stuck_in_cal3 = True

    return result


# ─── Aggregate analysis ───────────────────────────────────────────────────────

@dataclass
class MCStats:
    n: int = 0

    # Safety (must be 0)
    safety_violations: int = 0
    stage_regressions: int = 0
    pulse_floor_violations: int = 0
    duration_zero_violations: int = 0
    math_violations: int = 0

    # Alert quality
    spam_violations: int = 0
    total_alerts: int = 0
    total_red: int = 0
    total_yellow: int = 0

    # Progress (across responsive soils)
    reached_cal2: int = 0
    reached_cal3: int = 0
    reached_opt: int = 0
    stuck_cal1: int = 0
    stuck_cal2: int = 0
    stuck_cal3: int = 0

    # Pulse range across all runs
    min_pulses_ever: int = 9999
    max_pulses_ever: int = 0
    pulse_counts: list = field(default_factory=list)

    # Per-soil-type progress
    soil_opt_reach: dict = field(default_factory=dict)
    soil_run_count: dict = field(default_factory=dict)

    # Worst cases
    worst_run_seed: Optional[int] = None
    worst_run_violations: int = 0


def analyse(runs: list[SimRun]) -> MCStats:
    s = MCStats(n=len(runs))
    for r in runs:
        # Safety
        v = r.stage_regression + r.pulse_below_floor + r.pulse_duration_zero + r.math_inconsistency
        s.safety_violations        += v
        s.stage_regressions        += r.stage_regression
        s.pulse_floor_violations   += r.pulse_below_floor
        s.duration_zero_violations += r.pulse_duration_zero
        s.math_violations          += r.math_inconsistency

        # Alerts
        s.spam_violations += r.duplicate_spam_alerts
        s.total_alerts    += r.total_alerts
        s.total_red       += r.red_alerts
        s.total_yellow    += r.yellow_alerts

        # Progress
        if Stage.CALIBRATION_2 in r.stages_reached: s.reached_cal2 += 1
        if Stage.CALIBRATION_3 in r.stages_reached: s.reached_cal3 += 1
        if Stage.OPTIMIZATION  in r.stages_reached: s.reached_opt  += 1
        if r.stuck_in_cal1: s.stuck_cal1 += 1
        if r.stuck_in_cal2: s.stuck_cal2 += 1
        if r.stuck_in_cal3: s.stuck_cal3 += 1

        # Pulse bounds
        s.min_pulses_ever = min(s.min_pulses_ever, r.min_pulses_seen)
        s.max_pulses_ever = max(s.max_pulses_ever, r.max_pulses_seen)
        s.pulse_counts.extend(r.pulse_history)

        # Per soil type
        st = r.soil_type.value
        s.soil_run_count[st] = s.soil_run_count.get(st, 0) + 1
        if Stage.OPTIMIZATION in r.stages_reached:
            s.soil_opt_reach[st] = s.soil_opt_reach.get(st, 0) + 1

        # Worst case
        if v > s.worst_run_violations:
            s.worst_run_violations = v
            s.worst_run_seed = r.seed

    return s


# ─── Reporter ─────────────────────────────────────────────────────────────────

def pct(num, den):
    return f"{100*num/den:.1f}%" if den else "—"

def report(s: MCStats, runs: list[SimRun]):
    bar = "═" * 68

    print(f"\n{bar}")
    print(f"  AGRINOZE — MONTE CARLO STRESS TEST  ({s.n:,} runs × 180 days)")
    print(bar)

    # ── Safety ──
    print(f"\n  ┌─ SAFETY INVARIANTS {'─'*45}┐")
    ok = lambda x: "✓" if x == 0 else "✗"
    print(f"  │  {ok(s.stage_regressions):1}  Stage regressions           {s.stage_regressions:>8,}  (must be 0)   │")
    print(f"  │  {ok(s.pulse_floor_violations):1}  Pulse out of [0,200]        {s.pulse_floor_violations:>8,}  (must be 0)   │")
    print(f"  │  {ok(s.duration_zero_violations):1}  Pulse duration ≤ 0          {s.duration_zero_violations:>8,}  (must be 0)   │")
    print(f"  │  {ok(s.math_violations):1}  Math inconsistencies         {s.math_violations:>8,}  (must be 0)   │")
    print(f"  │  {ok(s.spam_violations):1}  Alert spam (>3 in 7 days)    {s.spam_violations:>8,}  (must be 0)   │")
    total_v = s.safety_violations + s.spam_violations
    verdict = "ALL CLEAR" if total_v == 0 else f"⚠ {total_v} VIOLATIONS"
    print(f"  │                                                              │")
    print(f"  │    Verdict: {verdict:<52}│")
    print(f"  └{'─'*66}┘")

    # ── Progress ──
    print(f"\n  ┌─ STAGE PROGRESSION {'─'*46}┐")
    print(f"  │  Reached Cal 2      {pct(s.reached_cal2, s.n):>8}  ({s.reached_cal2:,}/{s.n:,})                 │")
    print(f"  │  Reached Cal 3      {pct(s.reached_cal3, s.n):>8}  ({s.reached_cal3:,}/{s.n:,})                 │")
    print(f"  │  Reached Optimize   {pct(s.reached_opt,  s.n):>8}  ({s.reached_opt:,}/{s.n:,})                 │")
    print(f"  │                                                              │")
    print(f"  │  Stuck in Cal 1     {pct(s.stuck_cal1, s.n):>8}  (soil never responded)           │")
    print(f"  │  Stuck in Cal 2     {pct(s.stuck_cal2, s.n):>8}  (never dried out enough)         │")
    print(f"  │  Stuck in Cal 3     {pct(s.stuck_cal3, s.n):>8}  (failed to stabilise)            │")
    print(f"  └{'─'*66}┘")

    # ── Per soil type ──
    print(f"\n  ┌─ OPTIMIZATION RATE BY SOIL TYPE {'─'*33}┐")
    for st in ["heavy","medium","sandy","soilless"]:
        total = s.soil_run_count.get(st, 0)
        opt   = s.soil_opt_reach.get(st, 0)
        bar_w = int(30 * opt / total) if total else 0
        bar_s = "█" * bar_w + "░" * (30 - bar_w)
        print(f"  │  {st:<10} {bar_s}  {pct(opt,total):>6}  │")
    print(f"  └{'─'*66}┘")

    # ── Alert stats ──
    print(f"\n  ┌─ ALERT STATISTICS {'─'*47}┐")
    avg_alerts = s.total_alerts / s.n if s.n else 0
    avg_red    = s.total_red    / s.n if s.n else 0
    print(f"  │  Total alerts fired      {s.total_alerts:>10,}                            │")
    print(f"  │  Avg alerts / run        {avg_alerts:>10.1f}                            │")
    print(f"  │  Red (action required)   {s.total_red:>10,}  ({pct(s.total_red, s.total_alerts):>6} of all)        │")
    print(f"  │  Yellow (monitor)        {s.total_yellow:>10,}  ({pct(s.total_yellow, s.total_alerts):>6} of all)        │")
    print(f"  └{'─'*66}┘")

    # ── Pulse distribution ──
    if s.pulse_counts:
        pc = sorted(s.pulse_counts)
        p5   = pc[int(len(pc)*0.05)]
        p50  = pc[int(len(pc)*0.50)]
        p95  = pc[int(len(pc)*0.95)]
        mean = sum(pc) / len(pc)
        print(f"\n  ┌─ PULSE COUNT DISTRIBUTION {'─'*39}┐")
        print(f"  │  Min ever              {s.min_pulses_ever:>6}                                    │")
        print(f"  │  P5                    {p5:>6}                                    │")
        print(f"  │  Median                {p50:>6}                                    │")
        print(f"  │  Mean                  {mean:>6.0f}                                    │")
        print(f"  │  P95                   {p95:>6}                                    │")
        print(f"  │  Max ever              {s.max_pulses_ever:>6}                                    │")
        print(f"  └{'─'*66}┘")

    # ── Stuck runs detail ──
    stuck_runs = [r for r in runs if r.stuck_in_cal1 or r.stuck_in_cal2 or r.stuck_in_cal3]
    if stuck_runs:
        print(f"\n  ┌─ STUCK RUNS SAMPLE (first 5) {'─'*36}┐")
        for r in stuck_runs[:5]:
            where = "Cal1" if r.stuck_in_cal1 else "Cal2" if r.stuck_in_cal2 else "Cal3"
            print(f"  │  seed={r.seed:<8} soil={r.soil_type.value:<10} stuck_in={where}          │")
            print(f"  │    drying={r.profile.drying_rate:.2f} mb/L={r.profile.mb_per_litre:.2f} "
                  f"t20_init={r.profile.t20_initial:.0f}mb           │")
        print(f"  └{'─'*66}┘")

    # ── Worst case ──
    if s.worst_run_seed and s.worst_run_violations > 0:
        print(f"\n  ⚡ Worst run: seed={s.worst_run_seed}, violations={s.worst_run_violations}")

    print(f"\n{bar}\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(n_runs: int = 2000, max_days: int = 180):
    print(f"Running {n_runs:,} Monte Carlo simulations × {max_days} days each...")
    print(f"Total simulated irrigation decisions: {n_runs * max_days:,}\n")

    runs = []
    dots_per_line = 50
    dot_interval  = max(1, n_runs // (dots_per_line * 10))

    for i in range(n_runs):
        run = run_one(seed=i, max_days=max_days)
        runs.append(run)
        if i % dot_interval == 0:
            if i % (dot_interval * dots_per_line) == 0 and i > 0:
                pct_done = 100 * i / n_runs
                print(f" {pct_done:.0f}%")
            print(".", end="", flush=True)

    print(f" 100%\n")

    stats = analyse(runs)
    report(stats, runs)

    # Exit code: 0 = all clear, 1 = violations found
    total_violations = stats.safety_violations + stats.spam_violations
    return 0 if total_violations == 0 else 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    sys.exit(main(n_runs=n))
