# Motor Insurance Simulation (Prototype)

This repository contains a **Python-based traffic simulator** with a focus on **insurance costs**. The model is intentionally simplified to make it easy to visualize and iterate on. The simulator generates a clustered road network, spawns both drivers and cyclists, advances them in discrete steps, evaluates accidents stochastically, and produces summary metrics for underwriting-style analysis.

## Features

- **Cluster-based map generation** with residential/work/commerce/leisure clusters, highways, roundabouts, and junction types.
- **POIs and mobility nodes** (homes, work, commerce, leisure, crossings, cyclist hubs).
- **Dual population** of driver and cyclist agents, each with distinct behaviors.
- **Accident modeling** for single-vehicle, multi-vehicle, and vehicle-cyclist encounters with claims and liability.
- **Dash UI** with setup sliders, playback controls, live progress, timing breakdowns, summary panels, and map visualization.
- **Deterministic replay** via seeded simulations, plus batch parallel runs via the engine runner.

---

## Quick Start

### 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install dash plotly
```

### 2) Run the UI

```bash
python -m simulator.cli --serve
```

### 3) Run a headless simulation

```bash
python -m simulator.cli --headless --steps 200
```

### 4) Run multiple simulations in parallel (batch mode)

```bash
python -m simulator.cli --headless --parallel-runs 4 --steps 200
```

Note: the CLI headless arguments are currently out of sync with `MapConfig`/`DriverConfig` and may error. For headless runs and full control, use the Python API in `simulator/engine`.

---

## Simulation Model (High-Level)

### Movement
- Each agent moves **one node per step** on a generated road graph.
- Agents are idle until a **journey start probability** triggers a new trip.
- Routes are A* paths weighted by road type (highways are preferred).
- Agents wait at major junctions and roundabouts to simulate delays.
- Drivers and cyclists both move between homes, work, commerce, leisure, and cyclist hubs.

### Driver & Vehicle Profiles
- Driver risk profile influences speed bias and liability.
- Vehicles influence value and claim estimates.
- Each residence spawns one driver **and** one cyclist.

### Accident Modeling
- **Single-vehicle incidents** are sampled for active drivers only.
- **Multi-agent collisions** include driver-driver and driver-cyclist encounters.
- Severity is derived from impact speed; claim amounts are derived from vehicle value.
- Liability is assigned probabilistically based on driver risk profile.
- Road type and junction type apply multiplicative risk modifiers.

---

## Outputs

Headless runs output a JSON summary, including:
- Total accidents
- Severity distribution
- Total claim value
- Hotspots, road/junction breakdowns, and most impacted agents
- Journey and traffic metrics (distance, node visits, journey lengths)

---

## Project Structure

```
MotorInsuranceSimulation/
├─ simulator/
│  ├─ agents/          # driver + vehicle profiles
│  ├─ accidents/       # accident probability & claims
│  ├─ engine/          # simulation + runner
│  ├─ mapgen/          # clustered map generation
│  ├─ reporting/       # summary metrics
│  ├─ ui/              # Dash visualization
│  ├─ cli.py           # CLI entrypoint
│  └─ config.py        # simulation config
└─ README.md
```

---

## Notes & Next Steps

This is a prototype intended for exploration and visualization. The following areas are designed to be expanded:
- Route choice strategies and congestion
- Pedestrians and cyclists interactions beyond risk modifiers
- More sophisticated liability rules
- Additional insurance products (limits/deductibles)
- Advanced visual analytics (heatmaps, timelines, etc.)

---

## License

Prototype / demo usage only.
