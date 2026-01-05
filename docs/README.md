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
  - `residential_count`, `work_count`, `commerce_count`, `leisure_count`: POI counts.
  - `pedestrian_crossing_count`, `cyclist_hub_count`: mobility POI counts.
  - `road_type_weights`: weighted distribution of road types.
  - `speed_limits_by_type`: per-road-type speed limits.
  - `lanes_by_type`: per-road-type lane counts.
  - `cycle_lane_chance`: probability a segment has a cycle lane.

- `DriverConfig`
  - `count`: number of drivers.
  - `risk_profiles`: probabilities for low/medium/high drivers.

---

## Map Generation (`simulator/mapgen/mapgen.py`)

- `MapGenerator.generate()` builds a grid-based graph with metadata.
- `Node.kind` values: `junction`, `roundabout`, `residence`, `work`, `commerce`, `leisure`, `crossing`, `cyclist`.
- `Node.district` partitions the map into residential, commercial, and work bands.
- `Edge` includes speed limits, risk factors, road type, lane count, and cycle/crossing flags.
- `shortest_path()` computes a basic BFS route for agent navigation.

---

## Agents (`simulator/agents/`)

- `driver.py`: defines `DriverProfile` and the speed/aggression settings by risk tier.
- `vehicle.py`: defines `VehicleProfile` and default vehicle classes.

---

## Accidents (`simulator/accidents/model.py`)

- `accident_probability()` evaluates crash probability per step based on:
  - edge risk, time of day, driver risk, speed.
  - road type, pedestrian crossings, and cycle lanes.
- `build_accident()` emits a single event with:
  - participants, severity, at-fault, and claim estimates.

---

## Engine (`simulator/engine/`)

- `Simulation`
  - Owns the map, agents, and event log.
  - `step()` advances all agents, evaluates accidents, logs events.
  - Agents cycle between home, work, and commerce/leisure destinations.
  - Each agent tracks a destination and previous node for heading visualization.
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
  - start, pause, step, back, reset
  - playback speed
- Visualization panel:
  - district-aware roads with lane offsets and cycle lanes
  - POI markers with icons offset from roads
  - numbered vehicles with selectable routes
  - accident markers

---

## Extending the Simulator

Suggested expansions:
- Add cyclists/pedestrians interactions beyond static POIs.
- Introduce congestion impacts on routing.
- Improve collision modeling (lane-level, junction priority).
- Export full event logs to CSV/Parquet.
