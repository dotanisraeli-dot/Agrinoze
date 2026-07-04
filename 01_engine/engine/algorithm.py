"""
Agrinoze - Irrigation Algorithm Engine
Implements the full stage machine from the PRD:
  Initial -> Calibration 1 -> Calibration 2 -> Calibration 3 -> Optimization
"""

from datetime import datetime, timedelta
from typing import List, Optional

from .models import (
    Stage, SystemState, SiteConfig, SensorReading,
    IrrigationProgram, OPTIMAL_VWC,
    OverrideMode, ExitMode, RunMode, ProgramSnapshot,
    PULSE_CEILING, PULSE_FLOOR,
    DailySensorAverage, compute_daily_average,
)
from .alerts import (
    check_universal_sensor_alerts,
    check_universal_sensor_alerts_soilless,
    check_20cm_below_1mb_for_3_days,
    alert_tensiometer_no_drop_after_5_days,
    alert_cal2_no_rise_within_2_weeks,
    alert_cal2_dropped_below_10mb,
    alert_cal3_below_10mb,
    alert_cal3_above_40mb,
    alert_vwc_not_rising,
    alert_cal3_no_stabilisation,
    alert_override_stuck_3_days,
    alert_sensor_fault,
    alert_discharge_mismatch,
)

# ---------------------------------------------------------------------------
# Constants from PRD
# ---------------------------------------------------------------------------

CAL1_PULSES            = 200
CAL1_PULSE_SEC         = 120    # 2 minutes
CAL1_TRIGGER_MB        = 10     # drop below this for 3 days -> advance
CAL1_ALERT_MB          = 40     # must drop below within 5 days
CAL1_ALERT_DAYS        = 5
CAL1_CONSECUTIVE_DAYS  = 3

CAL2_PULSES            = 180
CAL2_PULSE_SEC_STD     = 30     # standard sites
CAL2_PULSE_SEC_EXT     = 60     # sites with height difference
CAL2_RISE_MB           = 40     # tensiometer must rise above this
CAL2_CONSECUTIVE_DAYS  = 3
CAL2_MAX_DAYS          = 14

CAL3_LOW_MB            = 10
CAL3_HIGH_MB           = 40
CAL3_STABLE_LOW        = 20
CAL3_STABLE_HIGH       = 40
CAL3_STABLE_WEEKS      = 2
CAL3_PULSE_ADJUST      = 20
CAL3_DURATION_ADJUST_SEC = 30

OPT_PULSE_SEC          = 30
SOILLESS_T20_LOW       = 10
SOILLESS_T20_HIGH      = 20
OPT_PULSE_ADJUST       = 20
OPT_HIGH_MB            = 40
OPT_LOW_MB             = 10

TWO_WEEKS              = timedelta(days=14)
ONE_WEEK               = timedelta(days=7)

OVERRIDE_STUCK_DAYS    = 3


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class IrrigationEngine:
    """
    Call process_daily_reading() once per day with the day's sensor readings.
    The engine computes a per-sensor daily average (PRD 19.6.26) and uses
    those averages for all decisions and stage transitions.
    """

    def __init__(self, config: SiteConfig):
        self.config = config
        self.state  = SystemState()
        self.state.stage            = Stage.AWAITING_START
        self.state.stage_entered_at = datetime.now()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_daily_reading(
        self,
        readings: List[SensorReading],
        now: Optional[datetime] = None,
    ) -> IrrigationProgram:
        """
        Main entry point. Call once per day with all raw sensor readings.

        PRD 19.6.26: sensors are sampled every 10 minutes -> 144 readings/day.
        The engine computes a simple per-sensor daily average (T20, T40, VWC)
        and uses those averages for ALL algorithm decisions and stage transitions.
        Raw readings are stored as last_reading; the daily average is appended to
        state.daily_averages for UI display ("every passing day").

        Order of operations:
          1. Compute daily averages from the 144 raw readings (excluding any
             implausible/faulty samples -- see _check_sensor_faults)
          2. Apply any pending program staged for this cycle (midnight boundary)
          3. Run universal alerts (fire in every mode, always use daily avg)
          4. Manual-override bookkeeping (stuck-in-manual alert)
          5. Dispatch stage handler (FULL_MANUAL pauses auto logic)
        """
        now = now or datetime.now()

        # 1. Compute daily average -- this is what the algorithm uses.
        #    Implausible readings (tensiometer outside 0-200mb, VWC outside
        #    0-100%) are excluded; if a whole sensor is bad for the day, fall
        #    back to yesterday's average rather than deciding on garbage.
        day_avg = compute_daily_average(readings, now.date(), fallback=self.state.last_daily_avg)
        self.state.daily_averages.append(day_avg)
        self.state.last_daily_avg = day_avg
        self.state.last_reading = readings[-1]  # most recent raw reading for display

        # Build a SensorReading from daily averages for alert/stage handlers
        avg_reading = SensorReading(
            timestamp=now,
            tensiometer_20cm=day_avg.t20_avg,
            tensiometer_40cm=day_avg.t40_avg,
            vwc=day_avg.vwc_avg,
            ec_bulk=day_avg.ec_bulk_avg,
            ec_pore=day_avg.ec_pore_avg,
            soil_temp=day_avg.soil_temp_avg,
            ph=day_avg.ph_avg,
        )

        print(
            f"[DAY AVG] {now.date()} | "
            f"T20={day_avg.t20_avg:.2f}mb | "
            f"T40={day_avg.t40_avg:.2f}mb | "
            f"VWC={day_avg.vwc_avg:.2f}% | "
            f"n={day_avg.num_readings} readings"
        )

        # 2. Cycle boundary -- apply anything staged for today, once per date
        self._apply_pending_if_new_cycle(now)

        # 2b. Sensor-fault / implausible-reading detection (controller requirement)
        self._check_sensor_faults(day_avg)

        # 3. Universal alerts -- always checked, every mode
        if self.config.has_40cm_tensiometer:
            check_universal_sensor_alerts(self.state, avg_reading)
        else:
            check_universal_sensor_alerts_soilless(self.state, avg_reading)
        check_20cm_below_1mb_for_3_days(self.state, avg_reading)

        # 4. Manual-override stuck alert (PRD: >3 days in manual without revert)
        self._check_override_stuck(now)

        # 5. FULL_MANUAL pauses all auto logic
        if self.state.override_mode == OverrideMode.FULL_MANUAL:
            print(f"[FULL-MANUAL] Auto logic paused. Holding {self.state.program.describe()}")
            return self.state.program

        # AUTO runs the stage machine using daily averages
        handler = {
            Stage.AWAITING_START: self._handle_awaiting_start,
            Stage.INITIAL:        self._handle_initial,
            Stage.CALIBRATION_1:  self._handle_cal1,
            Stage.CALIBRATION_2:  self._handle_cal2,
            Stage.CALIBRATION_3:  self._handle_cal3,
            Stage.OPTIMIZATION:   self._handle_optimization,
        }[self.state.stage]

        handler(avg_reading, now)
        return self.state.program

    # ------------------------------------------------------------------
    # Cycle boundary (PRD 18.6.26): changes apply at midnight, never mid-cycle
    # ------------------------------------------------------------------

    def _apply_pending_if_new_cycle(self, now: datetime):
        today = now.date()
        if self.state.last_cycle_date is None:
            self.state.last_cycle_date = today
            return

        if today == self.state.last_cycle_date:
            return  # same cycle -- no changes allowed

        self.state.last_cycle_date = today

        if self.state.pending_override_mode is not None:
            self.state.override_mode = self.state.pending_override_mode
            self.state.run_mode = {
                OverrideMode.NONE:        RunMode.AUTO,
                OverrideMode.FULL_MANUAL: RunMode.FULL_MANUAL,
            }[self.state.pending_override_mode]
            self.state.pending_override_mode = None

        if self.state.pending_program is not None:
            self.state.program = self.state.pending_program
            self.state.pending_program = None
            print(f"[CYCLE] New cycle {today} -- applied staged program: "
                  f"{self.state.program.describe()}")

        if self.state.pending_stage is not None:
            self.state.stage = self.state.pending_stage
            self.state.pending_stage = None

    @property
    def current_stage(self) -> Stage:
        return self.state.stage

    @property
    def current_program(self) -> IrrigationProgram:
        return self.state.program

    def get_alerts(self, clear: bool = False):
        alerts = list(self.state.alerts)
        if clear:
            self.state.alerts.clear()
        return alerts

    def get_daily_averages(self) -> list:
        """
        PRD 19.6.26: return the full history of daily sensor averages,
        one DailySensorAverage per completed day. Intended for UI display.
        """
        return list(self.state.daily_averages)

    def acknowledge_t40_alert(self):
        self.state.alert_t40_below_10_acknowledged = True
        print("[ACK] 40cm sub-10mb alert acknowledged by administrator.")

    @property
    def run_mode(self):
        return self.state.run_mode

    @property
    def is_frozen(self) -> bool:
        return self.state.frozen

    @property
    def override_mode(self):
        return self.state.override_mode

    # ------------------------------------------------------------------
    # Stage: AWAITING_START
    # ------------------------------------------------------------------

    def _handle_awaiting_start(self, reading: SensorReading, now: datetime):
        print(f"[AWAITING_START] T20 daily avg={reading.tensiometer_20cm:.2f}mb -- waiting for manual start.")

    def confirm_start(self, now: Optional[datetime] = None):
        now = now or datetime.now()
        if self.state.stage == Stage.AWAITING_START:
            print("[MANUAL START] Agronomist confirmed -- beginning Calibration Sub-Stage 1.")
            self._transition_to(Stage.CALIBRATION_1, now)
            self._set_program(CAL1_PULSES, CAL1_PULSE_SEC)
        else:
            print(f"[MANUAL START] Ignored -- system already in stage {self.state.stage.value}")

    # ------------------------------------------------------------------
    # Manual override (PRD 18.6.26)
    # ------------------------------------------------------------------

    def enter_manual_override(
        self,
        num_pulses: int,
        pulse_duration_sec: int,
        now: Optional[datetime] = None,
    ):
        """
        PRD 29.6.26: only one override mode exists in the current phase --
        Full Manual (auto logic fully paused). Semi-Auto is deferred to
        Future Requirements and is intentionally not offered here.
        """
        now = now or datetime.now()
        num_pulses = max(PULSE_FLOOR, min(PULSE_CEILING, num_pulses))

        self.state.override_snapshot = ProgramSnapshot(
            stage=self.state.stage,
            num_pulses=self.state.program.num_pulses,
            pulse_duration_sec=self.state.program.pulse_duration_sec,
            stage_entered_at=self.state.stage_entered_at,
            two_week_window_start=self.state.two_week_window_start,
            vwc_at_window_start=self.state.vwc_at_window_start,
            days_below_10mb_20cm=self.state.days_below_10mb_20cm,
            days_above_40mb_20cm=self.state.days_above_40mb_20cm,
        )
        print(f"[OVERRIDE] Snapshot saved: {self.state.override_snapshot.stage.value}, "
              f"{self.state.override_snapshot.num_pulses} pulses, "
              f"{self.state.override_snapshot.pulse_duration_sec}s")

        manual_program = IrrigationProgram(
            num_pulses=num_pulses,
            pulse_duration_sec=pulse_duration_sec,
            cycle_duration_min=self.config.cycle_duration_min,
        )
        self.state.pending_program       = manual_program
        self.state.pending_override_mode = OverrideMode.FULL_MANUAL
        self.state.override_entered_at   = now
        self.state.alert_override_stuck_fired = False

        print(f"[OVERRIDE] full_manual staged for next cycle: "
              f"{manual_program.describe()}")

    def exit_manual_override(self, now: Optional[datetime] = None):
        """PRD 29.6.26: single exit path -- 'Resume last auto' (rewind to snapshot)."""
        now = now or datetime.now()
        if self.state.override_mode == OverrideMode.NONE and self.state.pending_override_mode is None:
            print("[OVERRIDE] No active override to exit.")
            return

        snap = self.state.override_snapshot
        if snap is None:
            print("[OVERRIDE] No snapshot -- cannot resume last auto.")
            return
        restored = IrrigationProgram(
            num_pulses=snap.num_pulses,
            pulse_duration_sec=snap.pulse_duration_sec,
            cycle_duration_min=self.config.cycle_duration_min,
        )
        self.state.pending_program       = restored
        self.state.pending_stage         = snap.stage
        self.state.pending_override_mode = OverrideMode.NONE
        self.state.stage_entered_at       = snap.stage_entered_at
        self.state.two_week_window_start  = snap.two_week_window_start
        self.state.vwc_at_window_start    = snap.vwc_at_window_start
        self.state.days_below_10mb_20cm   = snap.days_below_10mb_20cm
        self.state.days_above_40mb_20cm   = snap.days_above_40mb_20cm
        print(f"[OVERRIDE] Resume LAST auto staged -- restoring snapshot "
              f"{snap.num_pulses} pulses at {snap.stage.value}")

        self.state.override_snapshot   = None
        self.state.override_entered_at = None

    def _check_override_stuck(self, now: datetime):
        if self.state.override_mode == OverrideMode.NONE:
            return
        if self.state.override_entered_at is None:
            return
        days = (now - self.state.override_entered_at).days
        if days >= OVERRIDE_STUCK_DAYS and not self.state.alert_override_stuck_fired:
            alert_override_stuck_3_days(self.state, self.state.override_mode.value, days)
            self.state.alert_override_stuck_fired = True

    def _check_sensor_faults(self, day_avg: DailySensorAverage):
        """
        Controller requirement: read sensor health (faulty/working/implausible
        readings). Fires once on ONSET of a fault day, stays silent while the
        fault persists, and re-arms after a clean day (same pattern as the
        universal sensor alerts). Soilless sites have no 40cm tensiometer, so
        that check is skipped entirely for them.
        """
        if day_avg.t20_anomalies > 0:
            if not self.state.alert_t20_fault_active:
                alert_sensor_fault(self.state, "20cm tensiometer", day_avg.t20_anomalies, day_avg.num_readings)
                self.state.alert_t20_fault_active = True
        else:
            self.state.alert_t20_fault_active = False

        if self.config.has_40cm_tensiometer:
            if day_avg.t40_anomalies > 0:
                if not self.state.alert_t40_fault_active:
                    alert_sensor_fault(self.state, "40cm tensiometer", day_avg.t40_anomalies, day_avg.num_readings)
                    self.state.alert_t40_fault_active = True
            else:
                self.state.alert_t40_fault_active = False

        if day_avg.vwc_anomalies > 0:
            if not self.state.alert_vwc_fault_active:
                alert_sensor_fault(self.state, "VWC sensor", day_avg.vwc_anomalies, day_avg.num_readings)
                self.state.alert_vwc_fault_active = True
        else:
            self.state.alert_vwc_fault_active = False

    # ------------------------------------------------------------------
    # Irrigation Freeze (PRD 18.6.26)
    # ------------------------------------------------------------------

    def freeze_irrigation(self):
        self.state.frozen = True
        if self.state.run_mode != RunMode.FROZEN:
            self.state.run_mode = RunMode.FROZEN
        print("[FREEZE] Irrigation frozen -- tap closed, logic continues.")

    def unfreeze_irrigation(self):
        self.state.frozen = False
        self.state.run_mode = {
            OverrideMode.NONE:        RunMode.AUTO,
            OverrideMode.FULL_MANUAL: RunMode.FULL_MANUAL,
        }[self.state.override_mode]
        print("[FREEZE] Irrigation resumed.")

    def effective_water_program(self) -> IrrigationProgram:
        if self.state.frozen:
            return IrrigationProgram(
                num_pulses=0,
                pulse_duration_sec=self.state.program.pulse_duration_sec,
                cycle_duration_min=self.config.cycle_duration_min,
            )
        return self.state.program

    # ------------------------------------------------------------------
    # Discharge mismatch -- planned vs actual water usage (PRD)
    # ------------------------------------------------------------------

    def check_discharge(
        self,
        actual_liters: float,
        elapsed_hours: float = 2.0,
        now: Optional[datetime] = None,
    ):
        """
        PRD: compare planned vs actual water discharge and alert if the
        mismatch exceeds config.discharge_mismatch_pct (default 20%). PRD
        specifies this check runs every 2 hours -- independent of the once-
        a-day process_daily_reading() cycle -- so call this on whatever
        cadence the controller/adapter reports actual discharge.

        Planned volume is derived from the *effective* program (0 pulses if
        irrigation is frozen), scaled down from a full day to `elapsed_hours`.
        Returns the fired Alert, or None if within threshold.
        """
        now = now or datetime.now()
        prog = self.effective_water_program()

        full_day_on_seconds = prog.num_pulses * prog.pulse_duration_sec
        fraction_of_day = elapsed_hours / 24.0
        on_seconds = full_day_on_seconds * fraction_of_day

        planned_liters = self.config.discharge_rate_lph * self.config.num_drippers * (on_seconds / 3600.0)

        self.state.last_planned_liters = planned_liters
        self.state.last_actual_liters = actual_liters

        if planned_liters > 0:
            pct_diff = (actual_liters - planned_liters) / planned_liters * 100.0
        else:
            # Nothing planned (e.g. frozen) -- any real flow is a 100% mismatch
            pct_diff = 0.0 if actual_liters <= 0 else 100.0

        self.state.last_discharge_pct_diff = pct_diff

        threshold = self.config.discharge_mismatch_pct
        if abs(pct_diff) > threshold:
            return alert_discharge_mismatch(self.state, planned_liters, actual_liters, pct_diff, threshold)
        return None

    # ------------------------------------------------------------------
    # Stage: INITIAL
    # ------------------------------------------------------------------

    def _handle_initial(self, reading: SensorReading, now: datetime):
        print(f"[INITIAL] T20 daily avg={reading.tensiometer_20cm:.2f}mb -- system initialised, awaiting start.")
        self._transition_to(Stage.CALIBRATION_1, now)
        self._set_program(CAL1_PULSES, CAL1_PULSE_SEC)

    # ------------------------------------------------------------------
    # Stage: CALIBRATION 1 -- Drenching
    # ------------------------------------------------------------------

    def _handle_cal1(self, reading: SensorReading, now: datetime):
        t20 = reading.tensiometer_20cm
        days_in_stage = (now - self.state.stage_entered_at).days

        if t20 < CAL1_TRIGGER_MB:
            self.state.days_below_10mb_20cm += 1
        else:
            self.state.days_below_10mb_20cm = 0

        print(
            f"[CAL-1] Day {days_in_stage} | T20 daily avg: {t20:.2f}mb | "
            f"days<10mb: {self.state.days_below_10mb_20cm}"
        )

        if t20 >= CAL1_ALERT_MB:
            self.state.alert_cal1_no_drop_day_counter += 1
            if self.state.alert_cal1_no_drop_day_counter >= CAL1_ALERT_DAYS:
                alert_tensiometer_no_drop_after_5_days(self.state)
                self.state.alert_cal1_no_drop_day_counter = 0
        else:
            self.state.alert_cal1_no_drop_day_counter = 0

        if self.state.days_below_10mb_20cm >= CAL1_CONSECUTIVE_DAYS:
            print("[CAL-1] Advancing to Calibration Sub-Stage 2")
            self.state.days_below_10mb_20cm = 0
            self._transition_to(Stage.CALIBRATION_2, now)
            pulse_sec = (
                CAL2_PULSE_SEC_EXT
                if self.config.use_extended_pulse_sub2
                else CAL2_PULSE_SEC_STD
            )
            self._set_program(CAL2_PULSES, pulse_sec)

    # ------------------------------------------------------------------
    # Stage: CALIBRATION 2 -- Reduction
    # ------------------------------------------------------------------

    def _handle_cal2(self, reading: SensorReading, now: datetime):
        t20 = reading.tensiometer_20cm
        days_in_stage = (now - self.state.stage_entered_at).days

        if t20 > CAL2_RISE_MB:
            self.state.days_above_40mb_20cm += 1
        else:
            self.state.days_above_40mb_20cm = 0

        if t20 < CAL1_TRIGGER_MB:
            self.state.days_below_10mb_20cm += 1
        else:
            self.state.days_below_10mb_20cm = 0

        print(
            f"[CAL-2] Day {days_in_stage} | T20 daily avg: {t20:.2f}mb | "
            f"days>40mb: {self.state.days_above_40mb_20cm}"
        )

        if self.state.days_below_10mb_20cm >= CAL2_CONSECUTIVE_DAYS:
            if not self.state.alert_cal2_dropped_below10_fired:
                alert_cal2_dropped_below_10mb(self.state)
                self.state.alert_cal2_dropped_below10_fired = True
            self.state.days_below_10mb_20cm = 0

        if days_in_stage >= self.config.cal2_max_days and self.state.days_above_40mb_20cm < CAL2_CONSECUTIVE_DAYS:
            if not self.state.alert_cal2_no_rise_fired:
                alert_cal2_no_rise_within_2_weeks(self.state)
                self.state.alert_cal2_no_rise_fired = True

        if self.state.days_above_40mb_20cm >= CAL2_CONSECUTIVE_DAYS:
            print("[CAL-2] Advancing to Calibration Sub-Stage 3")
            self.state.days_above_40mb_20cm = 0
            self.state.days_below_10mb_20cm = 0
            self._transition_to(Stage.CALIBRATION_3, now)
            self.state.two_week_window_start = now
            self.state.vwc_at_window_start = reading.vwc

    # ------------------------------------------------------------------
    # Stage: CALIBRATION 3 -- Stabilisation loop
    # ------------------------------------------------------------------

    def _handle_cal3(self, reading: SensorReading, now: datetime):
        t20 = reading.tensiometer_20cm
        days_in_stage  = (now - self.state.stage_entered_at).days
        days_in_window = (now - self.state.two_week_window_start).days

        if t20 < CAL3_LOW_MB:
            self.state.days_below_10mb_20cm += 1
            self.state.days_above_40mb_20cm = 0
        elif t20 > CAL3_HIGH_MB:
            self.state.days_above_40mb_20cm += 1
            self.state.days_below_10mb_20cm = 0
        else:
            self.state.days_below_10mb_20cm = 0
            self.state.days_above_40mb_20cm = 0

        print(
            f"[CAL-3] Day {days_in_stage} | T20 daily avg: {t20:.2f}mb | "
            f"VWC daily avg: {reading.vwc:.2f}% | window day {days_in_window}"
        )

        if self.state.days_below_10mb_20cm >= 3:
            if not self.state.alert_cal3_below10_fired:
                alert_cal3_below_10mb(self.state)
                self.state.alert_cal3_below10_fired = True
            self.state.days_below_10mb_20cm = 0
        elif t20 >= 10:
            self.state.alert_cal3_below10_fired = False

        if self.state.days_above_40mb_20cm >= 3:
            if not self.state.alert_cal3_above40_fired:
                alert_cal3_above_40mb(self.state)
                self.state.alert_cal3_above40_fired = True
            self.state.days_above_40mb_20cm = 0
        elif t20 <= 40:
            self.state.alert_cal3_above40_fired = False

        if days_in_window >= 7 and self.state.vwc_at_window_start is not None:
            expected_vwc = self.state.vwc_at_window_start + 10
            if reading.vwc < expected_vwc and not self.state.alert_vwc_not_rising_fired:
                alert_vwc_not_rising(
                    self.state, self.state.vwc_at_window_start, reading.vwc
                )
                self.state.alert_vwc_not_rising_fired = True

        if days_in_window >= 14:
            self._evaluate_cal3_window(reading, now)

    def _evaluate_cal3_window(self, reading: SensorReading, now: datetime):
        t20 = reading.tensiometer_20cm
        p   = self.state.program

        if CAL3_STABLE_LOW <= t20 <= CAL3_STABLE_HIGH:
            print("[CAL-3] Stable 20-40mb achieved -- Advancing to Optimization")
            self._transition_to(Stage.OPTIMIZATION, now)
            self._set_program(p.num_pulses, OPT_PULSE_SEC)
            self.state.two_week_window_start = now
            self.state.vwc_at_window_start = reading.vwc
            return

        if t20 < CAL3_LOW_MB:
            new_pulses = p.num_pulses - CAL3_PULSE_ADJUST
            print(f"[CAL-3] Below 10mb -- reduce pulses {p.num_pulses}->{new_pulses}")
            self._set_program(new_pulses, p.pulse_duration_sec)
        elif t20 > CAL3_HIGH_MB:
            new_pulses = p.num_pulses + CAL3_PULSE_ADJUST
            print(f"[CAL-3] Above 40mb -- increase pulses {p.num_pulses}->{new_pulses}")
            self._set_program(new_pulses, p.pulse_duration_sec)

        self.state.two_week_window_start      = now
        self.state.vwc_at_window_start        = reading.vwc
        self.state.days_below_10mb_20cm       = 0
        self.state.days_above_40mb_20cm       = 0
        self.state.alert_vwc_not_rising_fired = False

    # ------------------------------------------------------------------
    # Stage: OPTIMIZATION -- Continuous
    # ------------------------------------------------------------------

    def _handle_optimization(self, reading: SensorReading, now: datetime):
        t20 = reading.tensiometer_20cm
        days_in_window = (now - self.state.two_week_window_start).days

        print(
            f"[OPT] T20 daily avg: {t20:.2f}mb | VWC daily avg: {reading.vwc:.2f}% | "
            f"Pulses: {self.state.program.num_pulses} | Window day {days_in_window}"
        )

        if t20 > OPT_HIGH_MB:
            self.state.days_above_40mb_20cm += 1
            self.state.days_below_10mb_20cm = 0
        elif t20 < OPT_LOW_MB:
            self.state.days_below_10mb_20cm += 1
            self.state.days_above_40mb_20cm = 0
        else:
            self.state.days_above_40mb_20cm = 0
            self.state.days_below_10mb_20cm = 0

        if days_in_window >= 14:
            self._evaluate_optimization_window(reading, now)

    def _evaluate_optimization_window(self, reading: SensorReading, now: datetime):
        t20 = reading.tensiometer_20cm
        vwc = reading.vwc
        p   = self.state.program

        optimal_min, _ = OPTIMAL_VWC[self.config.soil_type]
        vwc_below_optimal = vwc < optimal_min
        t20_high = t20 > OPT_HIGH_MB
        t20_low  = t20 < OPT_LOW_MB

        add_pulses    = vwc_below_optimal or t20_high
        remove_pulses = t20_low

        if remove_pulses:
            new_pulses = p.num_pulses - OPT_PULSE_ADJUST
            print(f"[OPT] T20 < 10mb -- reducing pulses {p.num_pulses}->{new_pulses}")
        elif add_pulses:
            new_pulses = p.num_pulses + OPT_PULSE_ADJUST
            reason = []
            if vwc_below_optimal:
                reason.append(f"VWC {vwc:.2f}% < optimal {optimal_min}%")
            if t20_high:
                reason.append(f"T20 daily avg {t20:.2f}mb > 40mb")
            print(f"[OPT] Adding pulses ({', '.join(reason)}) {p.num_pulses}->{new_pulses}")
        else:
            new_pulses = p.num_pulses
            print(f"[OPT] Conditions stable -- no change ({p.num_pulses} pulses)")

        self._set_program(new_pulses, OPT_PULSE_SEC)

        self.state.two_week_window_start = now
        self.state.vwc_at_window_start   = vwc
        self.state.days_above_40mb_20cm  = 0
        self.state.days_below_10mb_20cm  = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition_to(self, stage: Stage, now: datetime):
        print(f"\n{'='*50}")
        print(f"  STAGE TRANSITION: {self.state.stage.value} -> {stage.value}")
        print(f"{'='*50}\n")
        self.state.stage            = stage
        self.state.stage_entered_at = now
        self.state.days_below_10mb_20cm          = 0
        self.state.days_above_40mb_20cm          = 0
        self.state.alert_cal1_no_drop_fired      = False
        self.state.alert_cal2_no_rise_fired      = False
        self.state.alert_vwc_not_rising_fired    = False
        self.state.alert_cal2_dropped_below10_fired = False
        self.state.alert_cal3_below10_fired      = False
        self.state.alert_cal3_above40_fired      = False

    def _set_program(self, num_pulses: int, pulse_duration_sec: int):
        num_pulses = max(PULSE_FLOOR, min(PULSE_CEILING, num_pulses))
        self.state.program = IrrigationProgram(
            num_pulses=num_pulses,
            pulse_duration_sec=pulse_duration_sec,
            cycle_duration_min=self.config.cycle_duration_min,
        )
        print(f"[PROGRAM] {self.state.program.describe()}")
