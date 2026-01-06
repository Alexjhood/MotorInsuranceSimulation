# Simulator Documentation

This document provides deeper details about how each module works and how to extend the simulator.

---

## Configuration (`simulator/config.py`)

- `SimulationConfig`
  - `seed`: controls deterministic replay.
  - `steps`: number of simulation steps per run.
  - `map_config`: clustered map generation parameters.
  - `driver_config`: journey start probabilities and risk distribution.
  - `accident_config`: base probabilities and risk multipliers.
  - `time_of_day`: currently stored but not applied in the simulation step.
  - `enable_parallel`: reserved for future per-step parallelism.
  - `parallel_workers`: batch parallelism count.

- `MapConfig`
  - `cluster_lambda`: expected number of clusters (Poisson).
  - `homes_per_cluster_lambda`, `other_locations_per_cluster_lambda`: Poisson rates for home and non-home nodes.
  - `map_scale`, `cluster_radius`, `min_cluster_spacing`: cluster placement bounds.
  - `intra_cluster_roundabout_chance`, `intra_cluster_dual_road_chance`: local road variety.
  - `highway_merge_roundabout_chance`, `major_junction_ratio`: highway/junction shaping.
  - `cluster_type_weights`: residential/work/commerce/leisure mix.
  - `min_residences`, `min_workplaces`, `min_commerce`, `min_leisure`: POI minimums.
  - `pedestrian_crossing_ratio`, `cyclist_hub_ratio`: mobility POI ratios.
  - `speed_limits_by_type`: per-road-type speed limits.
  - `lanes_by_type`: per-road-type lane counts.
  - `cycle_lane_chance`: probability a segment has a cycle lane.

- `DriverConfig`
  - `journey_start_probability`: driver trip start probability per step when idle.
  - `cyclist_journey_start_probability`: cyclist trip start probability per step when idle.
  - `risk_profiles`: probabilities for low/medium/high drivers.

- `AccidentConfig`
  - `unilateral_probability`: per-driver per-step incident probability.
  - `vehicle_encounter_probability`: base multi-vehicle encounter probability.
  - `cyclist_encounter_probability`: base vehicle-cyclist encounter probability.
  - `road_type_multipliers`: multipliers per road type.
  - `junction_multipliers`: multipliers per junction type.

---

## Map Generation (`simulator/mapgen/generator.py`)

- `MapGenerator.generate()` builds a clustered graph with highways between clusters.
- Clusters are sampled from Poisson processes and spaced apart on a `map_scale` plane.
- Nodes start as residences or junctions, then POIs are assigned by cluster type.
- Highway routes connect cluster entry nodes with roundabouts at merges.
- `Node.kind` values: `junction`, `major_junction`, `minor_junction`, `roundabout`, `residence`, `work`, `commerce`, `leisure`, `crossing`, `cyclist`, `highway_junction`.
- `Edge` includes speed limits, risk factors, road type, lane count, and cycle/crossing flags.

---

## Agents (`simulator/agents/`)

- `driver.py`: defines `DriverProfile` and the speed/aggression settings by risk tier.
- `vehicle.py`: defines `VehicleProfile` and default vehicle classes.
- Each residence spawns one driver agent and one cyclist agent.

---

## Accidents (`simulator/accidents/model.py`)

- `build_accident()` emits a single event with participants, severity, at-fault, and claim estimates.
- Accident severity is derived from impact speed; claims use vehicle value and severity.
- Liability uses driver risk levels to weight fault assignment.
- The simulation applies per-step probabilities plus road/junction multipliers.

---

## Engine (`simulator/engine/`)

- `Simulation`
  - Owns the map, agents, and event log.
  - `step()` advances all agents, assigns lanes, tallies occupancy, evaluates accidents, logs events.
  - Agents are idle until a journey start probability triggers a new trip.
  - Routes are A* paths weighted by road type (highways preferred).
  - Each agent tracks a destination and previous node for heading visualization.
  - Roundabouts and major junctions add per-node wait steps.
  - Per-step progress data is captured for the UI (phase timing + summaries).
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
  - hotspots, road type, and location kind breakdowns
  - journey stats (distance, counts, length distribution)
  - traffic stats (node visit counts, top traffic nodes)

---

## UI (`simulator/ui/app.py`)

- Dash control panel for:
  - seed, cluster/map shaping, journey probabilities, accident probabilities
  - start, pause, step, back, reset, playback speed
  - zoom/pan, label toggles, and visualization on/off
- Logging panel:
  - step log with filters
  - live progress of the current step's phases
  - timing summaries and step-level breakdowns
- Summary panel:
  - run summary stats for accidents, journeys, and traffic
- Server-side cache:
  - avoids regenerating the map on every callback
  - render gating ensures steps do not advance before render completes

---

## Extending the Simulator

Suggested expansions:
- Add cyclists/pedestrians interactions beyond static POIs.
- Introduce congestion impacts on routing.
- Improve collision modeling (lane-level, junction priority).
- Export full event logs to CSV/Parquet.
