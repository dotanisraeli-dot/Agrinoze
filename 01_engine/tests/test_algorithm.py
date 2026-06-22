"""
Agrinoze - Algorithm Engine Tests
Tests every stage transition and alert condition from the PRD.

PRD 19.6.26: engine.process_daily_reading() now accepts a List[SensorReading].
Test helpers wrap the single-reading shorthand in a 144-copy list so each
test simulates the full daily average (all values identical -> avg equals the value).
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from agrinoze.engine.models import (
    SiteConfig, SoilType, WaterType, SensorReading, Stage, AlertLevel,
    DailySensorAverage,
)
from agrinoze.engine.algorithm import IrrigationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

READINGS_PER_DAY = 144   # PRD 19.6.26: 1 reading / 10 min


def make_config(**kwargs) -> SiteConfig:
    defaults = dict(
        soil_type=SoilType.MEDIUM,
        water_type=WaterType.REGULAR,
        discharge_rate_lph=1.0,
        num_drippers=100,
    )
    defaults.update(kwargs)
    return SiteConfig(**defaults)


def make_reading(
    t20: float = 50.0,
    t40: float = 40.0,
    vwc: float = 30.0,
    ts: datetime = None,
) -> SensorReading:
    return SensorReading(
        timestamp=ts or datetime(2026, 1, 1),
        tensiometer_20cm=t20,
        tensiometer_40cm=t40,
        vwc=vwc,
    )


def make_readings(
    t20: float = 50.0,
    t40: float = 40.0,
    vwc: float = 30.0,
    ts: datetime = None,
    n: int = READINGS_PER_DAY,
) -> List[SensorReading]:
    """
    Return n identical SensorReadings for a day.
    Because all values are the same, the daily average equals the input values,
    so stage-transition logic is deterministic in tests.
    """
    base_ts = ts or datetime(2026, 1, 1)
    return [
        SensorReading(
            timestamp=base_ts + timedelta(minutes=i * 10),
            tensiometer_20cm=t20,
            tensiometer_40cm=t40,
            vwc=vwc,
        )
        for i in range(n)
    ]


def day(n: int) -> datetime:
    return datetime(2026, 1, 1) + timedelta(days=n)


def make_engine_at_cal1(config=None) -> IrrigationEngine:
    """
    Create an engine and advance it past AWAITING_START to CALIBRATION_1.
    Use this as a base in all tests that need to be at Cal1 or beyond.
    """
    engine = IrrigationEngine(config or make_config())
    engine.confirm_start(now=day(0))
    return engine


def advance_engine(engine, t20, t40=30.0, vwc=30.0, from_day=0, n_days=1):
    """Feed n days of identical daily readings into the engine."""
    prog = None
    for i in range(n_days):
        prog = engine.process_daily_reading(
            make_readings(t20=t20, t40=t40, vwc=vwc, ts=day(from_day + i)),
            now=day(from_day + i),
        )
    return prog


# ---------------------------------------------------------------------------
# Stage: AWAITING_START / INITIAL -> CALIBRATION_1
# ---------------------------------------------------------------------------

class TestInitialStage:
    def test_starts_in_awaiting_start(self):
        engine = IrrigationEngine(make_config())
        assert engine.current_stage == Stage.AWAITING_START

    def test_confirm_start_transitions_to_cal1(self):
        engine = IrrigationEngine(make_config())
        engine.confirm_start(now=day(0))
        assert engine.current_stage == Stage.CALIBRATION_1

    def test_cal1_program_is_200_pulses_2min(self):
        engine = make_engine_at_cal1()
        p = engine.current_program
        assert p.num_pulses == 200
        assert p.pulse_duration_sec == 120


# ---------------------------------------------------------------------------
# Stage: CALIBRATION_1
# ---------------------------------------------------------------------------

class TestCalibration1:
    def setup_method(self):
        self.engine = make_engine_at_cal1()
        # Feed one high-tension day to initialise counters
        advance_engine(self.engine, t20=80, from_day=1, n_days=1)

    def test_stays_in_cal1_while_above_10mb(self):
        advance_engine(self.engine, t20=50, from_day=2, n_days=10)
        assert self.engine.current_stage == Stage.CALIBRATION_1

    def test_alert_if_no_drop_below_40mb_after_5_days(self):
        # Feed 5 days of readings above 40mb (already 1 in setup -> need 4 more)
        advance_engine(self.engine, t20=80, from_day=2, n_days=4)
        alerts = self.engine.get_alerts()
        red_alerts = [a for a in alerts if a.level == AlertLevel.RED
                      and "5 days" in a.message]
        assert len(red_alerts) >= 1

    def test_advances_to_cal2_after_3_days_below_10mb(self):
        # First bring it into the 10-40 range (no stage change)
        advance_engine(self.engine, t20=25, from_day=2, n_days=5)
        # Now drop below 10 for 3 consecutive days
        advance_engine(self.engine, t20=5, from_day=7, n_days=3)
        assert self.engine.current_stage == Stage.CALIBRATION_2

    def test_does_not_advance_on_only_2_days_below_10mb(self):
        advance_engine(self.engine, t20=25, from_day=2, n_days=3)
        advance_engine(self.engine, t20=5, from_day=5, n_days=2)
        assert self.engine.current_stage == Stage.CALIBRATION_1

    def test_resets_counter_when_rises_above_10mb(self):
        # 2 days below 10, then rises, then 2 more -- should NOT advance
        advance_engine(self.engine, t20=5,  from_day=2, n_days=2)
        advance_engine(self.engine, t20=25, from_day=4, n_days=1)
        advance_engine(self.engine, t20=5,  from_day=5, n_days=2)
        assert self.engine.current_stage == Stage.CALIBRATION_1


# ---------------------------------------------------------------------------
# Stage: CALIBRATION_2
# ---------------------------------------------------------------------------

class TestCalibration2:
    def setup_method(self):
        self.engine = make_engine_at_cal1()
        # Advance to cal2: 3 days below 10mb
        advance_engine(self.engine, t20=5, from_day=1, n_days=3)
        assert self.engine.current_stage == Stage.CALIBRATION_2

    def test_cal2_program_is_180_pulses_30sec(self):
        p = self.engine.current_program
        assert p.num_pulses == 180
        assert p.pulse_duration_sec == 30

    def test_extended_pulse_for_height_difference_site(self):
        engine = make_engine_at_cal1(make_config(use_extended_pulse_sub2=True))
        advance_engine(engine, t20=5, from_day=1, n_days=3)
        assert engine.current_program.pulse_duration_sec == 60

    def test_advances_to_cal3_after_3_days_above_40mb(self):
        advance_engine(self.engine, t20=50, from_day=4, n_days=3)
        assert self.engine.current_stage == Stage.CALIBRATION_3

    def test_alert_if_drops_below_10mb_again(self):
        advance_engine(self.engine, t20=5, from_day=4, n_days=3)
        alerts = self.engine.get_alerts()
        red = [a for a in alerts if a.level == AlertLevel.RED
               and "dropped below 10mb" in a.message]
        assert len(red) >= 1

    def test_alert_if_no_rise_within_14_days(self):
        # Stay below 40mb for 14 days
        advance_engine(self.engine, t20=25, from_day=4, n_days=14)
        alerts = self.engine.get_alerts()
        red = [a for a in alerts if a.level == AlertLevel.RED
               and "2 weeks" in a.message]
        assert len(red) >= 1


# ---------------------------------------------------------------------------
# Stage: CALIBRATION_3
# ---------------------------------------------------------------------------

class TestCalibration3:
    def _reach_cal3(self):
        engine = make_engine_at_cal1()
        advance_engine(engine, t20=5, from_day=1, n_days=3)
        advance_engine(engine, t20=50, from_day=4, n_days=3)
        assert engine.current_stage == Stage.CALIBRATION_3
        return engine

    def test_stable_reading_advances_to_optimization(self):
        engine = self._reach_cal3()
        # Stable between 20-40mb for 14 days
        advance_engine(engine, t20=30, vwc=40, from_day=7, n_days=14)
        assert engine.current_stage == Stage.OPTIMIZATION

    def test_below_10mb_reduces_pulses(self):
        engine = self._reach_cal3()
        initial_pulses = engine.current_program.num_pulses
        # Stay below 10mb for 14 days (full window)
        advance_engine(engine, t20=5, from_day=7, n_days=14)
        assert engine.current_stage == Stage.CALIBRATION_3
        assert engine.current_program.num_pulses == initial_pulses - 20

    def test_above_40mb_increases_pulses(self):
        engine = self._reach_cal3()
        initial_pulses = engine.current_program.num_pulses
        advance_engine(engine, t20=60, from_day=7, n_days=14)
        assert engine.current_program.num_pulses == initial_pulses + 20

    def test_yellow_alert_below_10mb_for_3_days(self):
        engine = self._reach_cal3()
        advance_engine(engine, t20=5, from_day=7, n_days=3)
        alerts = engine.get_alerts()
        yellow = [a for a in alerts if a.level == AlertLevel.YELLOW
                  and "below 10mb" in a.message.lower()]
        assert len(yellow) >= 1

    def test_vwc_alert_if_not_rising_after_7_days(self):
        engine = self._reach_cal3()
        # VWC stays flat for 7+ days
        advance_engine(engine, t20=30, vwc=25, from_day=7, n_days=8)
        alerts = engine.get_alerts()
        vwc_alerts = [a for a in alerts if "VWC" in a.message]
        assert len(vwc_alerts) >= 1


# ---------------------------------------------------------------------------
# Stage: OPTIMIZATION
# ---------------------------------------------------------------------------

class TestOptimization:
    def _reach_optimization(self, vwc=40.0):
        engine = make_engine_at_cal1()
        advance_engine(engine, t20=5,  from_day=1, n_days=3)
        advance_engine(engine, t20=50, from_day=4, n_days=3)
        advance_engine(engine, t20=30, vwc=vwc, from_day=7, n_days=14)
        assert engine.current_stage == Stage.OPTIMIZATION
        return engine

    def test_pulse_duration_fixed_at_30sec(self):
        engine = self._reach_optimization()
        assert engine.current_program.pulse_duration_sec == 30

    def test_adds_pulses_if_vwc_below_optimal(self):
        engine = self._reach_optimization(vwc=35.0)  # medium soil optimal is 40%
        initial = engine.current_program.num_pulses
        # VWC stays below 40% for 14-day window
        advance_engine(engine, t20=30, vwc=35, from_day=22, n_days=14)
        assert engine.current_program.num_pulses == initial + 20

    def test_adds_pulses_if_tensiometer_above_40mb(self):
        engine = self._reach_optimization(vwc=45.0)
        initial = engine.current_program.num_pulses
        advance_engine(engine, t20=50, vwc=45, from_day=22, n_days=14)
        assert engine.current_program.num_pulses == initial + 20

    def test_no_double_increase_when_both_triggers_fire(self):
        """PRD: if both VWC low AND T20 high, still only add 20 pulses."""
        engine = self._reach_optimization(vwc=35.0)
        initial = engine.current_program.num_pulses
        # Both VWC below optimal AND T20 above 40mb
        advance_engine(engine, t20=50, vwc=35, from_day=22, n_days=14)
        assert engine.current_program.num_pulses == initial + 20  # NOT +40

    def test_reduces_pulses_if_tensiometer_below_10mb(self):
        engine = self._reach_optimization(vwc=45.0)
        initial = engine.current_program.num_pulses
        advance_engine(engine, t20=5, vwc=45, from_day=22, n_days=14)
        assert engine.current_program.num_pulses == initial - 20

    def test_no_change_when_conditions_are_optimal(self):
        engine = self._reach_optimization(vwc=45.0)
        initial = engine.current_program.num_pulses
        # T20 between 10-40mb, VWC above optimal
        advance_engine(engine, t20=25, vwc=45, from_day=22, n_days=14)
        assert engine.current_program.num_pulses == initial


# ---------------------------------------------------------------------------
# Universal alerts (fire at any stage)
# ---------------------------------------------------------------------------

class TestUniversalAlerts:
    def test_40cm_below_10mb_fires_red_alert_any_stage(self):
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(
            make_readings(t20=50, t40=5), now=day(0)
        )
        alerts = engine.get_alerts()
        red = [a for a in alerts if a.level == AlertLevel.RED
               and "40cm" in a.message]
        assert len(red) >= 1

    def test_20cm_below_1mb_fires_yellow_alert(self):
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(
            make_readings(t20=0.5, t40=30), now=day(0)
        )
        alerts = engine.get_alerts()
        yellow = [a for a in alerts if a.level == AlertLevel.YELLOW
                  and "1mb" in a.message]
        assert len(yellow) >= 1

    def test_20cm_below_1mb_for_3_days_fires_red_alert(self):
        engine = IrrigationEngine(make_config())
        for i in range(3):
            engine.process_daily_reading(
                make_readings(t20=0.5, t40=30), now=day(i)
            )
        alerts = engine.get_alerts()
        red = [a for a in alerts if a.level == AlertLevel.RED
               and "3+" in a.message]
        assert len(red) >= 1


# ---------------------------------------------------------------------------
# Daily sensor averages (PRD 19.6.26)
# ---------------------------------------------------------------------------

class TestDailySensorAverages:
    def test_daily_average_stored_after_each_day(self):
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(make_readings(t20=50, t40=40, vwc=30), now=day(0))
        engine.process_daily_reading(make_readings(t20=40, t40=35, vwc=32), now=day(1))
        avgs = engine.get_daily_averages()
        assert len(avgs) == 2

    def test_daily_average_values_match_uniform_readings(self):
        """When all 144 readings are identical, avg == that value."""
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(make_readings(t20=55.0, t40=42.0, vwc=28.5), now=day(0))
        avg = engine.get_daily_averages()[0]
        assert avg.t20_avg == 55.0
        assert avg.t40_avg == 42.0
        assert avg.vwc_avg == 28.5

    def test_daily_average_has_correct_reading_count(self):
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(make_readings(t20=50), now=day(0))
        avg = engine.get_daily_averages()[0]
        assert avg.num_readings == READINGS_PER_DAY

    def test_daily_average_per_sensor_independent(self):
        """Each sensor is averaged independently."""
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(
            make_readings(t20=20.0, t40=15.0, vwc=45.0), now=day(0)
        )
        avg = engine.get_daily_averages()[0]
        assert avg.t20_avg == 20.0
        assert avg.t40_avg == 15.0
        assert avg.vwc_avg == 45.0

    def test_last_daily_avg_convenience_property(self):
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(make_readings(t20=50), now=day(0))
        engine.process_daily_reading(make_readings(t20=30), now=day(1))
        assert engine.state.last_daily_avg is not None
        assert engine.state.last_daily_avg.t20_avg == 30.0

    def test_daily_average_date_matches_processing_date(self):
        engine = IrrigationEngine(make_config())
        engine.process_daily_reading(make_readings(t20=50), now=day(5))
        avg = engine.get_daily_averages()[0]
        assert avg.day == day(5).date()


# ---------------------------------------------------------------------------
# IrrigationProgram calculations
# ---------------------------------------------------------------------------

class TestIrrigationProgram:
    def test_interval_200_pulses(self):
        from agrinoze.engine.models import IrrigationProgram
        p = IrrigationProgram(num_pulses=200, pulse_duration_sec=120)
        assert abs(p.interval_min - 7.2) < 0.01

    def test_off_duration_200_pulses_2min(self):
        from agrinoze.engine.models import IrrigationProgram
        p = IrrigationProgram(num_pulses=200, pulse_duration_sec=120)
        assert abs(p.off_duration_min - 5.2) < 0.01

    def test_interval_180_pulses(self):
        from agrinoze.engine.models import IrrigationProgram
        p = IrrigationProgram(num_pulses=180, pulse_duration_sec=30)
        assert abs(p.interval_min - 8.0) < 0.01

    def test_off_duration_180_pulses_30sec(self):
        from agrinoze.engine.models import IrrigationProgram
        p = IrrigationProgram(num_pulses=180, pulse_duration_sec=30)
        assert abs(p.off_duration_min - 7.5) < 0.01
