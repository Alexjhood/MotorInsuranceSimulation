# Simulator Documentation

This document provides deeper details about how each module works and how to extend the simulator.

---

## Configuration (`simulator/config.py`)

- `SimulationConfig`
  - `seed`: controls deterministic replay.
  - `steps`: number of simulation steps per run.
  - `map_config`: size/density/POI configuration.
  - `driver_config`: driver population settings.
  - `time_of_day`: impacts accident probabilities.
  - `enable_parallel`: reserved for future per-step parallelism.
  - `parallel_workers`: batch parallelism count.

- `MapConfig`
  - `width`, `height`: map grid dimensions.
  - `road_density`: probability of nodes existing in each grid cell.
  - `roundabout_count`: number of roundabouts.
  - `speed_limits`: list of allowable speed limits.
  - `residential_count`, `work_count`, `visit_count`: POI counts.

- `DriverConfig`
  - `count`: number of drivers.
  - `risk_profiles`: probabilities for low/medium/high drivers.

---

## Map Generation (`simulator/mapgen/mapgen.py`)

- `MapGenerator.generate()` builds a grid-based graph with metadata.
- `Node.kind` values: `junction`, `roundabout`, `residence`, `work`, `visit`.
- `Edge` contains speed limits and a per-edge risk factor.
- `shortest_path()` computes a basic BFS route for agent navigation.

---

## Agents (`simulator/agents/`)

- `driver.py`: defines `DriverProfile` and the speed/aggression settings by risk tier.
- `vehicle.py`: defines `VehicleProfile` and default vehicle classes.

---

## Accidents (`simulator/accidents/model.py`)

- `accident_probability()` evaluates crash probability per step based on:
  - edge risk, time of day, driver risk, speed.
- `build_accident()` emits a single event with:
  - participants, severity, at-fault, and claim estimates.

---

## Engine (`simulator/engine/`)

- `Simulation`
  - Owns the map, agents, and event log.
  - `step()` advances all agents, evaluates accidents, logs events.
  - `run()` advances for a configured number of steps.

- `SimulationRunner`
  - `run_headless()` for a single run.
  - `run_parallel()` for multiple seeded runs using multiprocessing.

---

## Reporting (`simulator/reporting/summary.py`)

- `summarize_run()` provides:
  - total accidents
  - severity breakdown
  - total claim amount
  - hotspots and impacted agents

---

## UI (`simulator/ui/app.py`)

- Dash control panel for:
  - seed, agent count, map size
  - start, pause, reset
- Visualization panel:
  - map nodes and edges
  - agent positions
  - accident markers

---

## Extending the Simulator

Suggested expansions:
- Add cyclists/pedestrians and interactions.
- Introduce congestion impacts on routing.
- Improve collision modeling (lane-level, junction priority).
- Export full event logs to CSV/Parquet.
