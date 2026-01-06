from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Dict

from simulator.engine.simulation import Simulation


def summarize_run(simulation: Simulation) -> Dict[str, object]:
    accidents = simulation.accidents
    severity_counts = Counter(accident.severity for accident in accidents)
    total_claims = sum(accident.total_claim for accident in accidents)
    participant_counts = Counter()
    participant_type_counts = Counter()
    driver_risk_counts = Counter()
    vehicle_class_counts = Counter()
    accident_type_counts = Counter()
    location_kind_counts = Counter()
    road_type_counts = Counter()
    claims_by_severity = Counter()
    for accident in accidents:
        participant_counts.update(accident.participants)
        location_kind_counts.update([simulation.map_data.nodes[accident.location].kind])
        edge = simulation.node_edge.get(accident.location, simulation.default_edge)
        if edge:
            road_type_counts.update([edge.road_type])
        accident_type_counts.update(["single_vehicle" if len(accident.participants) == 1 else "multi_vehicle"])
        claims_by_severity.update({accident.severity: accident.total_claim})
        for participant_id in accident.participants:
            agent = simulation.agents.get(participant_id)
            if not agent:
                continue
            participant_type_counts.update([agent.agent_type])
            driver_risk_counts.update([agent.driver.risk_level])
            vehicle_class_counts.update([agent.vehicle.class_name])
    hotspot_nodes = Counter(accident.location for accident in accidents).most_common(5)
    journey_distances = simulation.journey_distances
    total_journey_distance = simulation.total_journey_distance
    total_journeys_completed = simulation.total_journeys_completed
    avg_journey_length = (
        total_journey_distance / total_journeys_completed if total_journeys_completed > 0 else 0.0
    )
    median_journey_length = median(journey_distances) if journey_distances else 0.0
    min_journey_length = min(journey_distances) if journey_distances else 0.0
    max_journey_length = max(journey_distances) if journey_distances else 0.0

    total_distance = simulation.total_distance
    avg_distance_per_step = total_distance / simulation.step_index if simulation.step_index > 0 else 0.0

    node_visit_counts = simulation.node_visit_counts or {}
    total_node_visits = sum(node_visit_counts.values())
    active_nodes = sum(1 for count in node_visit_counts.values() if count > 0)
    avg_node_visits = total_node_visits / active_nodes if active_nodes else 0.0
    top_traffic_nodes = sorted(node_visit_counts.items(), key=lambda item: item[1], reverse=True)[:8]
    traffic_by_node_kind = Counter()
    for node_id, count in node_visit_counts.items():
        if count <= 0:
            continue
        node_kind = simulation.map_data.nodes[node_id].kind
        traffic_by_node_kind[node_kind] += count
    return {
        "steps": simulation.step_index,
        "total_accidents": len(accidents),
        "severity_counts": dict(severity_counts),
        "total_claims": round(total_claims, 2),
        "active_agents": len(simulation.agents),
        "top_hotspots": hotspot_nodes,
        "most_impacted_agents": participant_counts.most_common(5),
        "participant_type_counts": dict(participant_type_counts),
        "driver_risk_counts": dict(driver_risk_counts),
        "vehicle_class_counts": dict(vehicle_class_counts),
        "accident_type_counts": dict(accident_type_counts),
        "location_kind_counts": dict(location_kind_counts),
        "road_type_counts": dict(road_type_counts),
        "claims_by_severity": {key: round(value, 2) for key, value in claims_by_severity.items()},
        "total_distance": round(total_distance, 2),
        "avg_distance_per_step": round(avg_distance_per_step, 2),
        "total_journeys_started": simulation.total_journeys_started,
        "total_journeys_completed": total_journeys_completed,
        "total_journey_distance": round(total_journey_distance, 2),
        "avg_journey_length": round(avg_journey_length, 2),
        "median_journey_length": round(median_journey_length, 2),
        "min_journey_length": round(min_journey_length, 2),
        "max_journey_length": round(max_journey_length, 2),
        "total_node_visits": total_node_visits,
        "avg_node_visits": round(avg_node_visits, 2),
        "active_nodes": active_nodes,
        "top_traffic_nodes": top_traffic_nodes,
        "traffic_by_node_kind": dict(traffic_by_node_kind),
    }
