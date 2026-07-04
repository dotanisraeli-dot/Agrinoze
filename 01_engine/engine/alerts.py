"""
Agrinoze - Alert Manager
All alert conditions defined in the PRD, centralised here.
"""

from datetime import datetime
from .models import Alert, AlertLevel, Stage, SystemState, SensorReading


def _alert(state: SystemState, level: AlertLevel, message: str) -> Alert:
    a = Alert(
        timestamp=datetime.now(),
        level=level,
        message=message,
        stage=state.stage,
    )
    state.alerts.append(a)
    print(f"[ALERT {level.value.upper()}] {message}")
    return a


# ---------------------------------------------------------------------------
# Sensor-level alerts — checked on EVERY reading, regardless of stage
# ---------------------------------------------------------------------------

def check_universal_sensor_alerts(
    state: SystemState, reading: SensorReading
) -> list[Alert]:
    """
    Fire universal alerts on ONSET of condition, not every day it persists.
    Alert fires when condition first becomes true; silenced until it clears,
    then re-arms so it fires again if the condition returns.
    """
    alerts = []

    # 40cm tensiometer below 10mb — RED alert (PRD 18.6.26: fires CONTINUOUSLY
    # until administrator acknowledges). Re-arms if condition clears.
    if reading.tensiometer_40cm < 10:
        if not state.alert_t40_below_10_acknowledged:
            alerts.append(_alert(
                state, AlertLevel.RED,
                f"40cm tensiometer below 10mb ({reading.tensiometer_40cm:.1f}mb) — "
                "risk of over-saturation at depth. Acknowledge to silence."
            ))
        state.alert_t40_below_10_active = True
    else:
        # Condition cleared — reset both the active flag and the acknowledgement
        state.alert_t40_below_10_active = False
        state.alert_t40_below_10_acknowledged = False

    # 20cm tensiometer below 1mb — YELLOW alert on onset only
    # Cooldown: minimum 14 days between firings (handles noisy sensors near 0)
    if state.alert_t20_below_1_cooldown > 0:
        state.alert_t20_below_1_cooldown -= 1

    if reading.tensiometer_20cm < 1:
        if not state.alert_t20_below_1_active and state.alert_t20_below_1_cooldown == 0:
            alerts.append(_alert(
                state, AlertLevel.YELLOW,
                f"20cm tensiometer dropped below 1mb ({reading.tensiometer_20cm:.1f}mb)."
            ))
            state.alert_t20_below_1_active = True
            state.alert_t20_below_1_cooldown = 14
    elif reading.tensiometer_20cm > 3:
        state.alert_t20_below_1_active = False   # re-arm only after rising above 3mb

    return alerts


def check_20cm_below_1mb_for_3_days(
    state: SystemState, reading: SensorReading
) -> list[Alert]:
    """
    Fires RED alert when T20 < 1mb for 3 consecutive days.
    After firing, enters a 14-day cooldown before it can fire again
    (prevents spam if condition persists; agronomist already notified).
    """
    alerts = []

    # Decrement cooldown each day
    if state.alert_1mb_red_cooldown_days > 0:
        state.alert_1mb_red_cooldown_days -= 1

    if reading.tensiometer_20cm < 1:
        state.days_below_1mb_20cm += 1
    else:
        state.days_below_1mb_20cm = 0

    if state.days_below_1mb_20cm >= 3 and state.alert_1mb_red_cooldown_days == 0:
        alerts.append(_alert(
            state, AlertLevel.RED,
            "20cm tensiometer has been below 1mb for 3+ consecutive days — "
            "immediate administrator action required."
        ))
        state.days_below_1mb_20cm = 0
        state.alert_1mb_red_cooldown_days = 14   # suppress for 14 days
    return alerts


# ---------------------------------------------------------------------------
# Q8: Soilless-specific universal alerts
# No 40cm tensiometer. 20cm optimal range is 10-20mb (not 10-40mb).
# ---------------------------------------------------------------------------

def check_universal_sensor_alerts_soilless(
    state: SystemState, reading: SensorReading
) -> list[Alert]:
    """
    Soilless sites: only 20cm tensiometer present.
    Alert if T20 drops below 10mb (too wet) or rises above 20mb (too dry).
    """
    alerts = []

    # T20 below 10mb on soilless — onset alert
    if reading.tensiometer_20cm < 10:
        if not state.alert_t40_below_10_active:  # reuse flag for soilless low
            alerts.append(_alert(
                state, AlertLevel.RED,
                f"Soilless: 20cm tensiometer below 10mb ({reading.tensiometer_20cm:.1f}mb) — "
                "over-saturation risk. Check drainage."
            ))
            state.alert_t40_below_10_active = True
    else:
        state.alert_t40_below_10_active = False

    # T20 above 20mb on soilless — dry alert
    if reading.tensiometer_20cm > 20:
        if not state.alert_t20_below_1_active:  # reuse flag for soilless high
            alerts.append(_alert(
                state, AlertLevel.YELLOW,
                f"Soilless: 20cm tensiometer above 20mb ({reading.tensiometer_20cm:.1f}mb) — "
                "substrate drying out."
            ))
            state.alert_t20_below_1_active = True
    elif reading.tensiometer_20cm <= 20:
        state.alert_t20_below_1_active = False

    # Below 1mb — yellow onset only (reuses 1mb cooldown from main alert system)
    if reading.tensiometer_20cm < 1:
        if state.alert_t20_below_1_cooldown == 0:
            alerts.append(_alert(
                state, AlertLevel.YELLOW,
                f"Soilless: 20cm tensiometer at {reading.tensiometer_20cm:.1f}mb — near saturation."
            ))
            state.alert_t20_below_1_cooldown = 14
    elif reading.tensiometer_20cm > 3:
        pass   # cooldown ticks naturally in check_20cm_below_1mb_for_3_days

    return alerts


# ---------------------------------------------------------------------------
# Q11: Alert delivery metadata
# RED  → push notification + SMS + email to admin
# YELLOW → in-app only, no push/SMS/email
# This is attached to every alert so the delivery layer can act on it.
# ---------------------------------------------------------------------------

DELIVERY_CHANNELS = {
    AlertLevel.RED:    ["push", "sms", "email"],
    AlertLevel.YELLOW: ["in_app"],
}


# ---------------------------------------------------------------------------
# Stage-specific alerts
# ---------------------------------------------------------------------------

def alert_tensiometer_no_drop_after_5_days(state: SystemState) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        "Calibration Sub-Stage 1: Tensiometer has not dropped below 40mb "
        "after 5 days (120 hours). Check soil/dripper setup."
    )


def alert_cal2_no_rise_within_2_weeks(state: SystemState) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        "Calibration Sub-Stage 2: Tensiometer did not rise above 40mb "
        "within 2 weeks. Administrator action required."
    )


def alert_cal2_dropped_below_10mb(state: SystemState) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        "Calibration Sub-Stage 2: Tensiometer dropped below 10mb again. "
        "Administrator action required."
    )


def alert_cal3_below_10mb(state: SystemState) -> Alert:
    return _alert(
        state, AlertLevel.YELLOW,
        "Calibration Sub-Stage 3: Tensiometer reading below 10mb for 3 days."
    )


def alert_cal3_above_40mb(state: SystemState) -> Alert:
    return _alert(
        state, AlertLevel.YELLOW,
        "Calibration Sub-Stage 3: Tensiometer reading above 40mb for 3 days."
    )


def alert_vwc_not_rising(
    state: SystemState, initial_vwc: float, current_vwc: float
) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        f"VWC has not risen by 10% after 1 week "
        f"(started {initial_vwc:.1f}%, now {current_vwc:.1f}%, "
        f"expected ≥{initial_vwc + 10:.1f}%)."
    )


def alert_cal3_no_stabilisation(state: SystemState) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        "Calibration Sub-Stage 3: System has not stabilised between "
        "20-40mb. Administrator review required."
    )


def alert_discharge_mismatch(
    state: SystemState,
    planned_litres: float,
    actual_litres: float,
    pct_diff: float,
    threshold_pct: float = 20.0,   # Q7: default 20% per agronomist, configurable
) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        f"Discharge mismatch: planned {planned_litres:.1f}L, "
        f"actual {actual_litres:.1f}L ({pct_diff:+.2f}% vs {threshold_pct}% threshold). "
        "Check for leaks or clogged drippers."
    )


def alert_override_stuck_3_days(state: SystemState, mode: str, days: int) -> Alert:
    """PRD 18.6.26: alert if running in manual override >3 days without reverting."""
    return _alert(
        state, AlertLevel.YELLOW,
        f"System has been in {mode} manual override for {days} days "
        "without reverting to auto. Consider resuming automatic control."
    )


# ---------------------------------------------------------------------------
# Sensor-fault / implausible-reading alert (controller requirement: "read
# health of the sensors -- faulty/working/unplausible readings"). Tensiometer
# readings outside 0-200mb and VWC outside 0-100% are excluded from the daily
# average by compute_daily_average(); this alert tells the administrator why.
# ---------------------------------------------------------------------------

def alert_sensor_fault(
    state: SystemState,
    sensor_name: str,
    anomaly_count: int,
    total_readings: int,
) -> Alert:
    return _alert(
        state, AlertLevel.RED,
        f"{sensor_name}: {anomaly_count}/{total_readings} readings today were outside "
        "the physically plausible range -- malfunction suspected. Anomalous readings "
        "were excluded from today's average. Check sensor wiring/calibration."
    )
