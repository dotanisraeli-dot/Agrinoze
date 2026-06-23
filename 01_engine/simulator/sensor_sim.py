"""
Agrinoze - Sensor Simulator
Generates realistic sensor readings day-by-day so we can test the
full algorithm without physical hardware.

PRD 19.6.26: sensors are sampled every 10 minutes -> 144 readings/day.
  simulate_day_readings() produces all 144 readings for a given day.
  simulate_day() is kept for backward compatibility (returns a single reading).
"""

import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional

from ..engine.models import SensorReading, IrrigationProgram, SoilType


@dataclass
class SimulatorState:
    tensiometer_20cm: float = 80.0
    tensiometer_40cm: float = 60.0
    vwc: float = 25.0
    soil_type: SoilType = SoilType.MEDIUM


class SensorSimulator:
    """
    Simulates one day of soil-moisture response given an irrigation program.

    Physics model:
      daily_litres  = pulses x (pulse_sec / 3600) x discharge_Lph
      tension_drop  = daily_litres x mb_per_litre   (soil wetted)
      tension_rise  = drying_rate_mb_per_day         (evaporation/drainage)
      net_delta_T20 = tension_rise - tension_drop
    """

    # Dripper defaults (agronomist-configurable):
    #   num_drippers    : 21,600  (adjust in steps of 100)
    #   dripper_flow_lph: 1.0 L/hr (adjust in steps of 0.25 L/hr)
    DEFAULT_NUM_DRIPPERS     = 21_600
    DEFAULT_DRIPPER_FLOW_LPH = 1.0
    DRIPPER_STEP             = 100
    DRIPPER_FLOW_STEP        = 0.25

    MB_PER_LITRE         = 1.5
    DRYING_RATE          = 4.0
    DEPTH_LAG_FACTOR     = 0.55
    VWC_RISE_PER_LITRE   = 0.8
    VWC_DROP_PER_DAY     = 0.35
    NOISE_MB             = 1.5
    NOISE_VWC            = 0.3
    READINGS_PER_DAY     = 144
    SAMPLE_INTERVAL_MIN  = 10

    def __init__(
        self,
        soil_type: SoilType = SoilType.MEDIUM,
        num_drippers: int = DEFAULT_NUM_DRIPPERS,
        dripper_flow_lph: float = DEFAULT_DRIPPER_FLOW_LPH,
        mb_per_litre: float = None,
        drying_rate: float = None,
    ):
        self.soil             = SimulatorState(soil_type=soil_type)
        self.num_drippers     = num_drippers
        self.dripper_flow_lph = dripper_flow_lph
        self.mb_per_litre     = mb_per_litre or self.MB_PER_LITRE
        self.drying_rate      = drying_rate  or self.DRYING_RATE

    def simulate_day_readings(
        self,
        program: IrrigationProgram,
        day_start: datetime,
        seed: Optional[int] = None,
    ) -> List[SensorReading]:
        """
        PRD 19.6.26: produce all 144 sensor readings for a single day.
        Readings are spaced 10 minutes apart starting at day_start (midnight).
        Soil physics step once at start-of-day; per-reading noise is added
        independently so each reading differs slightly (as in real hardware).
        Returns a list of 144 SensorReadings.
        """
        if seed is not None:
            random.seed(seed)

        daily_litres = (
            program.num_pulses
            * (program.pulse_duration_sec / 3600)
            * self.num_drippers
            * self.dripper_flow_lph
        )

        tension_drop = daily_litres * self.mb_per_litre
        tension_rise = self.drying_rate
        delta_20 = tension_rise - tension_drop
        delta_40 = delta_20 * self.DEPTH_LAG_FACTOR

        self.soil.tensiometer_20cm = max(0.0, self.soil.tensiometer_20cm + delta_20)
        self.soil.tensiometer_40cm = max(0.0, self.soil.tensiometer_40cm + delta_40)

        vwc_rise = daily_litres * self.VWC_RISE_PER_LITRE
        self.soil.vwc = min(100.0, max(0.0,
            self.soil.vwc + vwc_rise - self.VWC_DROP_PER_DAY))

        base_t20 = self.soil.tensiometer_20cm
        base_t40 = self.soil.tensiometer_40cm
        base_vwc = self.soil.vwc

        readings: List[SensorReading] = []
        for i in range(self.READINGS_PER_DAY):
            ts  = day_start + timedelta(minutes=i * self.SAMPLE_INTERVAL_MIN)
            t20 = base_t20 + random.gauss(0, self.NOISE_MB)
            t40 = base_t40 + random.gauss(0, self.NOISE_MB)
            vwc = base_vwc + random.gauss(0, self.NOISE_VWC)
            readings.append(SensorReading(
                timestamp=ts,
                tensiometer_20cm=max(0.0, round(t20, 2)),
                tensiometer_40cm=max(0.0, round(t40, 2)),
                vwc=max(0.0, min(100.0, round(vwc, 2))),
                soil_temp=round(random.gauss(20, 1.5), 1),
                ec_bulk=round(random.gauss(0.8, 0.05), 3),
                ec_pore=round(random.gauss(1.2, 0.08), 3),
                ph=round(random.gauss(6.5, 0.1), 2),
            ))
        return readings

    def simulate_day(self, program: IrrigationProgram, now: datetime,
                     seed: Optional[int] = None) -> SensorReading:
        """
        Backward-compatible single-reading API.
        Internally generates 144 readings and returns the last one.
        """
        readings = self.simulate_day_readings(program, now, seed=seed)
        return readings[-1]

    def force_state(self, tensiometer_20cm=None, tensiometer_40cm=None, vwc=None):
        if tensiometer_20cm is not None: self.soil.tensiometer_20cm = tensiometer_20cm
        if tensiometer_40cm is not None: self.soil.tensiometer_40cm = tensiometer_40cm
        if vwc              is not None: self.soil.vwc              = vwc
