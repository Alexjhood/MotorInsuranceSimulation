# Motor Insurance Simulation (Prototype)

This repository contains a **Python-based traffic simulator** with a focus on **insurance costs**. The model is intentionally simplified to make it easy to visualize and iterate on. Vehicles move in discrete steps, accidents are evaluated stochastically at each step, and summaries are produced for underwriting-style analysis.

## Features

- **Synthetic map generation** (configurable size, road density, speed limits, roundabouts, POIs).
- **Agent-based traffic** with driver risk profiles and vehicle attributes.
- **Accident modeling** including severity, liability assignment, and claims estimates.
- **Dash UI** with a control panel and live visualization.
- **Deterministic replay** via seeded simulations.
- **Headless runs** and **parallel batch runs** for performance testing.

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
python -m simulator.cli --headless --steps 200 --agents 25
```

### 4) Run multiple simulations in parallel (batch mode)

```bash
python -m simulator.cli --headless --parallel-runs 4 --steps 200
```

---

## Simulation Model (High-Level)

### Movement
- Each agent moves **one node per step** on a generated road graph.
- Routes are shortest paths between home/work/visit nodes.
- When an agent completes a route, a new destination is selected.

### Driver & Vehicle Profiles
- Driver risk profile influences speed bias and accident probability.
- Vehicle class influences value and safety rating.

### Accident Modeling
- **Single-vehicle incidents** are sampled per agent per step.
- **Multi-vehicle collisions** occur when multiple agents occupy the same node.
- Severity is based on speed and a stochastic factor.
- Claim amounts are derived from vehicle value and severity.
- Liability is assigned probabilistically based on driver risk.

---

## Outputs

Headless runs output a JSON summary, including:
- Total accidents
- Severity distribution
- Total claim value
- Hotspots and most impacted agents

---

## Project Structure

```
MotorInsuranceSimulation/
├─ simulator/
│  ├─ agents/          # driver + vehicle profiles
│  ├─ accidents/       # accident probability & claims
│  ├─ engine/          # simulation + runner
│  ├─ mapgen/          # synthetic map generation
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
- Pedestrians and cyclists
- More sophisticated liability rules
- Additional insurance products (limits/deductibles)
- Advanced visual analytics (heatmaps, timelines, etc.)

---

## License

Prototype / demo usage only.
