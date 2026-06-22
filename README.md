# Agrinoze Smart Irrigation System

**Precision irrigation that encodes a master agronomist's expertise into an algorithmic engine.**
Engine name: **SensAItion** · Parent system: **Agrinoze**

Status as of 18 June 2026 — engine built & verified against PRD 18.6.26, agronomist-facing simulator complete and ready for validation by Eitan Shapira.

---

## What this is

Agrinoze is an automated, ML-driven irrigation controller. It maintains optimal soil moisture in the root zone using frequent, precisely-measured water pulses, eliminating the human-in-the-loop. The **SensAItion engine** is the brain: a five-stage state machine that takes a field from first watering through calibration to continuous optimization, driven by tensiometer and VWC sensor readings.

Claimed benefits (per PRD): up to 50% water savings, up to 100% fertilization savings, improved yield and quality.

---

## Project structure

```
Agrinoze/
├── 01_engine/              The SensAItion engine — Python (BUILT + VERIFIED)
│   ├── engine/
│   │   ├── models.py         Data models, enums, pulse bounds, override state
│   │   ├── algorithm.py      Stage machine, override engine, cycle-boundary logic
│   │   └── alerts.py         RED/YELLOW alerts, delivery tiers, persist-until-ack
│   ├── simulator/
│   │   └── sensor_sim.py     Soil physics model (litre-based) for headless testing
│   ├── tests/
│   │   ├── test_verification.py   80-test verification suite (PRD clause audit, boundaries, invariants)
│   │   ├── monte_carlo.py         2,000-run stress test (360k decisions, zero safety violations)
│   │   └── test_algorithm.py      Original unit tests
│   └── run_simulation.py     End-to-end console simulation runner
│
├── 02_simulator_ui/        Agronomist-facing live simulator — React (BUILT)
│   └── SensAItion_Simulator.jsx   Self-contained: engine ported to JS + soil model + full control UI
│
├── 03_diagrams/            Reference diagrams (PNG, SVG, PDF)
│   ├── sys_overview.*        System architecture & component map
│   ├── algo_tree.*           Full algorithm stage-machine tree
│   └── Agrinoze_Diagrams.pdf  Both bundled with a cover page
│
└── 04_docs/
    └── prd_history/          PRD evolution and the agronomist Q&A
        ├── PRD_v13.6.26_original.pdf
        ├── PRD_v18.6.26_updated.docx     (current spec)
        ├── PRD_Annotated_Questions.pdf   (12 questions raised, as sticky notes)
        └── PRD_answers_by_Eitan.pdf      (Eitan's answers — all now implemented)
```

---

## The algorithm in brief

Five stages, advancing on sensor-driven triggers:

1. **Awaiting Start** — sensors monitored; requires manual agronomist confirmation to begin.
2. **Calibration 1 (Drenching)** — 200 pulses × 120s. Advances when 20cm tensiometer < 10mb for 3 consecutive days.
3. **Calibration 2 (Reduction)** — 180 pulses × 30s. Advances when tensiometer > 40mb for 3 consecutive days.
4. **Calibration 3 (Stabilisation)** — repeating 2-week windows, ±20 pulses, until stable 20–40mb.
5. **Continuous Optimization** — fixed 30s pulses; 2-week VWC + tensiometer checks adjust ±20 pulses.

**Universal alerts** fire in any stage (40cm < 10mb → RED until acknowledged; 20cm < 1mb → YELLOW; etc.).
**Pulse bounds:** 0–200. **Changes apply only at cycle boundary (midnight), never mid-cycle.**

### Manual override (the centerpiece feature)
- **On Execute:** snapshot current auto values FIRST, then stage the manual change (applies next midnight).
- **Two entry modes:** Full Manual (auto paused) · Semi-Auto (algorithm continues from the fixed manual baseline).
- **Two exit modes:** Resume Last Auto (restore snapshot) · Resume Modified Auto (keep manual values as baseline).
- **Irrigation Freeze:** closes the tap (0 pulses) while timers and logic keep running.

---

## Verification status

- **80/80** verification tests passing (PRD clause audit, boundary conditions, counter logic, scenarios, invariants).
- **Monte Carlo:** 2,000 runs × 180 days = 360,000 irrigation decisions, **zero safety violations**, pulses always within [0,200], no alert spam.
- All four soil types (Heavy, Medium, Sandy, Soilless) verified to progress cleanly through every stage.

To run:
```bash
cd 01_engine
python3 tests/test_verification.py    # full verification suite
python3 tests/monte_carlo.py 2000     # stress test
python3 run_simulation.py             # watch one run in the console
```

---

## Architecture & roadmap

The engine is deliberately decoupled from hardware via a **ControllerAdapter** boundary:
- **Built:** SimulatedAdapter (soil physics model) — powers the current demo.
- **Future:** PhysicalAdapter — connects to the real field controller (REST / MQTT / Modbus — TBD when hardware is chosen).

This is what lets the simulator *evolve into* the production application by swapping one component.

**Planned phases:**
- Phase 2 — Data persistence (PostgreSQL: 3-year sensor history, logs, config)
- Phase 3 — FastAPI layer (REST endpoints, agronomist/farmer roles) + ControllerAdapter interface
- Later — physical controller integration, multi-site management, push/SMS/email alert delivery

---

## Key context for future work

- **User:** Eitan Shapira, master agronomist — the primary user and validator. Owns the irrigation expertise the engine encodes.
- **Soil model caveat:** the simulator's soil physics is a *demonstration model* tuned for watchable timing, NOT calibrated to real field data. Field calibration against real sensor traces is a separate future step. The engine logic is the real, verified algorithm.
- **All 12 of Eitan's PRD answers are implemented** (pulse cap 200, configurable Cal2 timeout & discharge threshold, soilless handling, manual start, the full override model, etc.).
- **Tech stack:** Python engine + React frontend. FastAPI + PostgreSQL planned. Keep the adapter boundary clean.

---

*Confidential — Agrinoze. Contains proprietary algorithm and product specification.*
