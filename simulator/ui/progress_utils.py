from __future__ import annotations

from typing import Iterable


PHASE_DEFS = [
    ("Deserialize state", "advance", 1),
    ("Simulation step (overall)", "advance", 1),
    ("Agent movement", "sim", 0),
    ("Lane assignment", "sim", 0),
    ("Occupancy tally", "sim", 0),
    ("Unilateral accident checks", "sim", 0),
    ("Multi-agent accident checks", "sim", 0),
    ("Event + accident logging", "sim", 0),
    ("Process accidents", "advance", 1),
    ("Serialize state", "advance", 1),
    ("Finalize + history update", "advance", 1),
    ("Render: deserialize state", "render", 1),
    ("Render: summarize", "render", 1),
    ("Render: build figure", "render", 1),
    ("Render: overhead", "render", 1),
    ("Outside (network/browser)", "outside", 1),
]


def build_phase_template() -> list[dict]:
    phases = []
    for name, category, default_total in PHASE_DEFS:
        phases.append(
            {
                "name": name,
                "category": category,
                "total": default_total,
                "completed": 0,
                "duration_ms": 0,
                "progress_pct": 0,
                "state": "pending",
            }
        )
    return phases


def merge_phases(phases: list[dict], updates: Iterable[dict]) -> list[dict]:
    by_name = {phase.get("name"): phase for phase in phases}
    for update in updates:
        name = update.get("name")
        if not name:
            continue
        if name in by_name:
            by_name[name].update(update)
        else:
            phases.append(update)
            by_name[name] = update
    return phases


def normalize_progress(progress_data: dict | None) -> dict:
    progress_data = progress_data or {}
    template = build_phase_template()
    existing = progress_data.get("phases", [])
    progress_data["phases"] = merge_phases(template, existing)
    return progress_data


def update_phase(phases: list[dict], name: str, **updates) -> None:
    for phase in phases:
        if phase.get("name") == name:
            phase.update(updates)
            return
    phases.append({"name": name, **updates})
