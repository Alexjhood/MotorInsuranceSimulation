from __future__ import annotations

from collections import Counter
from typing import Dict

from simulator.engine.simulation import Simulation


def summarize_run(simulation: Simulation) -> Dict[str, object]:
    accidents = simulation.accidents
    severity_counts = Counter(accident.severity for accident in accidents)
    total_claims = sum(accident.total_claim for accident in accidents)
    participant_counts = Counter()
    for accident in accidents:
        participant_counts.update(accident.participants)
    hotspot_nodes = Counter(accident.location for accident in accidents).most_common(5)
    return {
        "steps": simulation.step_index,
        "total_accidents": len(accidents),
        "severity_counts": dict(severity_counts),
        "total_claims": round(total_claims, 2),
        "active_agents": len(simulation.agents),
        "top_hotspots": hotspot_nodes,
        "most_impacted_agents": participant_counts.most_common(5),
    }
