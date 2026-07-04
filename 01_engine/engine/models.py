"""
Agrinoze Smart Irrigation System
Core data models and enums
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime, date
from typing import Optional, List


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SoilType(Enum):
    HEAVY   = "heavy"     # optimal VWC 50%+
    MEDIUM  = "medium"    # optimal VWC 40-50%
    SANDY   = "sandy"     # optimal VWC 30-35%
    SOILLESS = "soilless" # optimal VWC 30-50%


class WaterType(Enum):
    REGULAR   = "regular"
    DISTILLED = "distilled"


class Stage(Enum):
    AWAITING_START = "awaiting_start"   # waiting for manual agronomist start
    INITIAL        = "initial"
    CALIBRATION_1  = "calibration_1"
    CALIBRATION_2  = "calibration_2"
    CALIBRATION_3  = "calibration_3"
    OPTIMIZATION   = "optimization"


class AlertLevel(Enum):
    YELLOW = "yellow"   # Pay attention, no immediate action needed
    RED    = "red"      # Immediate action required


class OverrideMode(Enum):
    """Manual override modes (PRD 29.6.26).
    Full-manual-only in the current phase; Semi-Auto is deferred to
    Future Requirements per PRD 29.6.26 and is intentionally not modelled here.
    """
    NONE        = "none"         # system running fully automatic
    FULL_MANUAL = "full_manual"  # auto logic paused; simple continuous program


class ExitMode(Enum):
    """How to leave a manual override (PRD 29.6.26). Single exit path."""
    RESUME_LAST_AUTO = "resume_last_auto"  # restore pre-override snapshot


class RunMode(Enum):
    """Top-level run state, surfaced prominently in the UI."""
    AUTO        = "auto"
    FULL_MANUAL = "full_manual"
    FROZEN      = "frozen"      # irrigation freeze: tap closed, logic continues


# ---------------------------------------------------------------------------
# Optimal VWC ranges per soil type
# Returns (min%, max%) -- irrigation targets the minimum
# ---------------------------------------------------------------------------

OPTIMAL_VWC = {
    SoilType.HEAVY:    (50, 100),
    SoilType.MEDIUM:   (40, 50),
    SoilType.SANDY:    (30, 35),
    SoilType.SOILLESS: (30, 50),
}


# ---------------------------------------------------------------------------
# Pulse bounds (PRD 18.6.26): ceiling 200, floor 0
# ---------------------------------------------------------------------------

PULSE_CEILING = 200
PULSE_FLOOR   = 0


# ---------------------------------------------------------------------------
# Program snapshot -- captured at the moment of override "Execute",
# BEFORE the manual change is staged (PRD 18.6.26)
# ---------------------------------------------------------------------------

@dataclass
class ProgramSnapshot:
    stage: "Stage"
    num_pulses: int
    pulse_duration_sec: int
    # window state, so "resume last auto" can continue the algorithm cleanly
    stage_entered_at: Optional[datetime] = None
    two_week_window_start: Optional[datetime] = None
    vwc_at_window_start: Optional[float] = None
    days_below_10mb_20cm: int = 0
    days_above_40mb_20cm: int = 0


# ---------------------------------------------------------------------------
# Sensor reading snapshot
# ---------------------------------------------------------------------------

@dataclass
class SensorReading:
    timestamp: datetime
    tensiometer_20cm: float      # millibar, 0=saturated, 200=dry
    tensiometer_40cm: float      # millibar
    vwc: float                   # volumetric water content, 0-100%
    ec_bulk: Optional[float] = None
    ec_pore: Optional[float] = None
    soil_temp: Optional[float] = None
    ph: Optional[float] = None

    def is_tensiometer_20cm_valid(self) -> bool:
        return 0 <= self.tensiometer_20cm <= 200

    def is_tensiometer_40cm_valid(self) -> bool:
        return 0 <= self.tensiometer_40cm <= 200

    def is_vwc_valid(self) -> bool:
        return 0 <= self.vwc <= 100


# ---------------------------------------------------------------------------
# Daily sensor average (PRD 19.6.26)
# One record per day -- simple mean of the 144 ten-minute readings per sensor.
# Stored in SystemState.daily_averages for UI display ("every passing day").
# The algorithm uses these values exclusively for all decisions.
# ---------------------------------------------------------------------------

@dataclass
class DailySensorAverage:
    day: date                    # calendar date this average covers
    t20_avg: float               # mean T20 millibar across 144 readings
    t40_avg: float               # mean T40 millibar across 144 readings
    vwc_avg: float               # mean VWC % across 144 readings
    num_readings: int = 144      # actual count (may be <144 on first/partial day)
    # Sensor-fault tracking: readings outside the physically plausible range
    # (tensiometers 0-200mb, VWC 0-100%) are excluded from the average above.
    # Non-zero here means the engine should raise a sensor-fault alert.
    t20_anomalies: int = 0
    t40_anomalies: int = 0
    vwc_anomalies: int = 0
    # Optional averages for display-only sensors
    ec_bulk_avg: Optional[float] = None
    ec_pore_avg: Optional[float] = None
    soil_temp_avg: Optional[float] = None
    ph_avg: Optional[float] = None


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    timestamp: datetime
    level: AlertLevel
    message: str
    stage: Stage


# ---------------------------------------------------------------------------
# Irrigation program -- what the controller executes
# ---------------------------------------------------------------------------

@dataclass
class IrrigationProgram:
    num_pulses: int          # pulses per 24-hour cycle
    pulse_duration_sec: int  # seconds water is ON per pulse
    cycle_duration_min: int = 1440  # 24 hours in minutes

    @property
    def interval_min(self) -> float:
        """Total time (on+off) between pulse starts, in minutes."""
        if self.num_pulses <= 0:
            return 0.0   # no pulses -> no interval (tap effectively off)
        return self.cycle_duration_min / self.num_pulses

    @property
    def off_duration_min(self) -> float:
        """Minutes water is OFF between pulses."""
        if self.num_pulses <= 0:
            return float(self.cycle_duration_min)  # whole cycle is "off"
        return self.interval_min - (self.pulse_duration_sec / 60)

    @property
    def daily_water_on_sec(self) -> int:
        return self.num_pulses * self.pulse_duration_sec

    def describe(self) -> str:
        if self.num_pulses <= 0:
            return "0 pulses/day | tap off (no irrigation)"
        return (
            f"{self.num_pulses} pulses/day | "
            f"{self.pulse_duration_sec}s ON | "
            f"{self.off_duration_min:.1f} min OFF | "
            f"interval {self.interval_min:.1f} min"
        )


# ---------------------------------------------------------------------------
# Site configuration -- set once at deployment
# ---------------------------------------------------------------------------

@dataclass
class SiteConfig:
    soil_type: SoilType
    water_type: WaterType
    discharge_rate_lph: float        # litres per hour per dripper
    num_drippers: int
    # Some sites with height differences use 1-min pulses in sub-stage 2
    use_extended_pulse_sub2: bool = False
    cycle_duration_min: int = 1440   # default 24h
    # Configurable Cal2 timeout (default 14 days per PRD)
    cal2_max_days: int = 14
    # Configurable discharge mismatch threshold (default 20%)
    discharge_mismatch_pct: float = 20.0
    # Soilless sites have no 40cm tensiometer
    has_40cm_tensiometer: bool = True


# ---------------------------------------------------------------------------
# Full system state -- everything the algorithm needs to make decisions
# ---------------------------------------------------------------------------

@dataclass
class SystemState:
    stage: Stage = Stage.INITIAL
    program: IrrigationProgram = field(
        default_factory=lambda: IrrigationProgram(
            num_pulses=200, pulse_duration_sec=120
        )
    )
    alerts: list = field(default_factory=list)

    # Stage timing trackers
    stage_entered_at: Optional[datetime] = None

    # Consecutive-day counters (reset on condition change)
    days_below_10mb_20cm: int = 0
    days_above_40mb_20cm: int = 0
    days_below_1mb_20cm: int = 0

    # Calibration sub-stage 3 / optimization 2-week window
    two_week_window_start: Optional[datetime] = None
    vwc_at_window_start: Optional[float] = None

    # Last known raw reading (for display)
    last_reading: Optional[SensorReading] = None

    # Daily averages history (PRD 19.6.26) -- one entry per completed day,
    # used for all algorithm decisions and displayed in the UI.
    daily_averages: List["DailySensorAverage"] = field(default_factory=list)

    # Last computed daily average (convenience reference)
    last_daily_avg: Optional["DailySensorAverage"] = None

    # Awaiting manual agronomist start confirmation
    awaiting_manual_start: bool = True

    # ---- Manual override (PRD 29.6.26: full-manual-only in current phase) ----
    override_mode: "OverrideMode" = None          # set in __post_init__
    run_mode: "RunMode" = None                    # set in __post_init__
    override_snapshot: Optional["ProgramSnapshot"] = None  # pre-override auto values
    override_entered_at: Optional[datetime] = None         # for 3-day stuck alert
    alert_override_stuck_fired: bool = False

    # ---- Cycle-boundary application (PRD 18.6.26) ----
    # Changes never apply mid-cycle. A staged program waits for next midnight.
    pending_program: Optional[IrrigationProgram] = None
    pending_stage: Optional[Stage] = None
    pending_override_mode: Optional["OverrideMode"] = None
    last_cycle_date: Optional[object] = None      # date of last applied cycle

    # ---- Irrigation freeze (PRD 18.6.26) ----
    # Closes the tap (0 water) but timers, readings, stage logic keep running.
    frozen: bool = False

    # Alert throttle flags -- prevent the same condition firing daily
    alert_cal1_no_drop_fired: bool = False
    alert_cal2_no_rise_fired: bool = False
    alert_vwc_not_rising_fired: bool = False
    # Universal alert throttles -- fire once per condition onset, not every day
    alert_t40_below_10_active: bool = False   # True while condition persists
    alert_t20_below_1_active:  bool = False   # True while condition persists

    # Per-stage alert cooldown
    alert_cal2_dropped_below10_fired: bool = False
    alert_1mb_red_cooldown_days: int = 0
    alert_t20_below_1_cooldown: int = 0
    alert_cal3_below10_fired: bool = False
    alert_cal3_above40_fired: bool = False

    # Persist-until-acknowledged alerts (PRD 18.6.26)
    alert_t40_below_10_acknowledged: bool = False
    alert_cal1_no_drop_day_counter: int = 0

    # ---- Sensor-fault / implausible-reading alerts (onset-based, like the
    # universal sensor alerts above -- fire once, re-arm after a clean day) ----
    alert_t20_fault_active: bool = False
    alert_t40_fault_active: bool = False
    alert_vwc_fault_active: bool = False

    # ---- Discharge mismatch (planned vs actual water usage) ----
    # Populated by IrrigationEngine.check_discharge(); independent of the
    # daily decision cycle since PRD checks this every 2 hours.
    last_planned_liters: Optional[float] = None
    last_actual_liters: Optional[float] = None
    last_discharge_pct_diff: Optional[float] = None

    def __post_init__(self):
        if self.override_mode is None:
            self.override_mode = OverrideMode.NONE
        if self.run_mode is None:
            self.run_mode = RunMode.AUTO


# ---------------------------------------------------------------------------
# Helper: compute a DailySensorAverage from a list of raw SensorReadings
# ---------------------------------------------------------------------------

def compute_daily_average(
    readings: List[SensorReading],
    day_date: date,
    fallback: Optional["DailySensorAverage"] = None,
) -> DailySensorAverage:
    """
    PRD 19.6.26: simple mean of all readings for the given day.
    Expected: 144 readings (one every 10 min). Works with any non-zero count.
    Each sensor (T20, T40, VWC) is averaged independently.

    Sensor-fault / implausible-reading handling (controller requirement --
    "read health of the sensors: faulty/working/implausible readings").
    Tensiometer readings outside 0-200mb, and VWC readings outside 0-100%,
    are physically implausible (malfunction suspected per PRD: "values above
    [200mb] are suspect as a malfunction"). Such readings are excluded from
    the average so a single glitchy sample can't skew the day's decision.
    If a sensor has ZERO valid readings for the entire day, the previous
    day's average is carried forward via `fallback` instead of feeding the
    algorithm garbage data. Anomaly counts are returned on the
    DailySensorAverage so the engine can raise a sensor-fault alert.
    """
    if not readings:
        raise ValueError("Cannot compute daily average from empty reading list")

    n = len(readings)

    t20_valid = [r.tensiometer_20cm for r in readings if r.is_tensiometer_20cm_valid()]
    t40_valid = [r.tensiometer_40cm for r in readings if r.is_tensiometer_40cm_valid()]
    vwc_valid = [r.vwc for r in readings if r.is_vwc_valid()]

    t20_anomalies = n - len(t20_valid)
    t40_anomalies = n - len(t40_valid)
    vwc_anomalies = n - len(vwc_valid)

    if t20_valid:
        t20 = sum(t20_valid) / len(t20_valid)
    elif fallback is not None:
        t20 = fallback.t20_avg
    else:
        t20 = sum(r.tensiometer_20cm for r in readings) / n

    if t40_valid:
        t40 = sum(t40_valid) / len(t40_valid)
    elif fallback is not None:
        t40 = fallback.t40_avg
    else:
        t40 = sum(r.tensiometer_40cm for r in readings) / n

    if vwc_valid:
        vwc = sum(vwc_valid) / len(vwc_valid)
    elif fallback is not None:
        vwc = fallback.vwc_avg
    else:
        vwc = sum(r.vwc for r in readings) / n

    ec_bulk_vals = [r.ec_bulk for r in readings if r.ec_bulk is not None]
    ec_pore_vals = [r.ec_pore for r in readings if r.ec_pore is not None]
    soil_temp_vals = [r.soil_temp for r in readings if r.soil_temp is not None]
    ph_vals = [r.ph for r in readings if r.ph is not None]

    return DailySensorAverage(
        day=day_date,
        t20_avg=round(t20, 2),
        t40_avg=round(t40, 2),
        vwc_avg=round(vwc, 2),
        num_readings=n,
        t20_anomalies=t20_anomalies,
        t40_anomalies=t40_anomalies,
        vwc_anomalies=vwc_anomalies,
        ec_bulk_avg=round(sum(ec_bulk_vals) / len(ec_bulk_vals), 3) if ec_bulk_vals else None,
        ec_pore_avg=round(sum(ec_pore_vals) / len(ec_pore_vals), 3) if ec_pore_vals else None,
        soil_temp_avg=round(sum(soil_temp_vals) / len(soil_temp_vals), 1) if soil_temp_vals else None,
        ph_avg=round(sum(ph_vals) / len(ph_vals), 2) if ph_vals else None,
    )
