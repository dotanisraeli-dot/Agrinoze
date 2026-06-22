"""
SensAItion - Full Simulation Runner
Runs the engine + simulator together through the complete stage progression.
"""

from datetime import datetime, timedelta

from agrinoze.engine.models import SiteConfig, SoilType, WaterType
from agrinoze.engine.algorithm import IrrigationEngine
from agrinoze.simulator.sensor_sim import SensorSimulator


def run_simulation(max_days: int = 200):
    print("=" * 60)
    print("  SENSAITION SMART IRRIGATION -- FULL SIMULATION")
    print("=" * 60)

    config = SiteConfig(
        soil_type=SoilType.MEDIUM,
        water_type=WaterType.REGULAR,
        discharge_rate_lph=1.0,
        num_drippers=100,
        use_extended_pulse_sub2=False,
    )

    engine    = IrrigationEngine(config)
    simulator = SensorSimulator(soil_type=config.soil_type)

    start_date = datetime(2026, 1, 1)

    # Agronomist confirms start immediately (skip the manual confirmation wait)
    engine.confirm_start(start_date)

    history = []

    for day in range(max_days):
        now = start_date + timedelta(days=day)
        program  = engine.current_program
        readings = simulator.simulate_day_readings(program, now, seed=day)
        engine.process_daily_reading(readings, now)

        avg = engine.state.last_daily_avg
        history.append({
            "day":       day + 1,
            "date":      now.strftime("%Y-%m-%d"),
            "stage":     engine.current_stage.value,
            "t20":       avg.t20_avg,
            "t40":       avg.t40_avg,
            "vwc":       avg.vwc_avg,
            "pulses":    program.num_pulses,
            "pulse_sec": program.pulse_duration_sec,
        })

        if engine.current_stage.value == "optimization" and day > 100:
            print(f"\n  Reached stable optimization by day {day + 1}")
            break

    print("\n" + "=" * 60)
    print("  SIMULATION SUMMARY")
    print("=" * 60)
    print(f"  {'Day':>4} {'Date':>12} {'Stage':>16} {'T20avg':>7} {'T40avg':>7} {'VWCavg':>7} {'Pulses':>7} {'Sec':>5}")
    print("  (T20/T40/VWC = daily averages of 144 readings -- PRD 19.6.26)")
    print("  " + "-" * 68)

    prev_stage = None
    for h in history:
        if h["stage"] != prev_stage:
            print(f"\n  >> {h['stage'].upper()}")
            prev_stage = h["stage"]

        if h["day"] % 5 == 0 or h["day"] <= 3:
            print(
                f"  {h['day']:>4} {h['date']:>12} {h['stage']:>16} "
                f"{h['t20']:>6.1f} {h['t40']:>6.1f} {h['vwc']:>6.1f}% "
                f"{h['pulses']:>7} {h['pulse_sec']:>5}s"
            )

    alerts = engine.get_alerts()
    print(f"\n  Total alerts fired: {len(alerts)}")
    for a in alerts:
        print(f"  [{a.level.value.upper()}] {a.message[:80]}")

    print("\n  Done.")
    return history, engine


if __name__ == "__main__":
    run_simulation()
