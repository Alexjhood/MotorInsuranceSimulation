from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from simulator.accidents.model import AccidentEvent
from simulator.config import AccidentConfig, DriverConfig, MapConfig, SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.ui.utils import log_to_linear


def config_from_inputs(
    seed: int,
    map_scale: float,
    cluster_lambda: float,
    homes_lambda: float,
    other_locations_lambda: float,
    cluster_spacing: float,
    dual_road_chance: float,
    roundabout_chance: float,
    highway_roundabout_chance: float,
    major_junction_ratio: float,
    journey_start_probability: float = 0.05,
    cyclist_journey_start_probability: float = 0.01,
    unilateral_probability: float = 0.01,
    vehicle_encounter_probability: float = 0.03,
    cyclist_encounter_probability: float = 0.03,
) -> SimulationConfig:
    map_config = MapConfig(
        cluster_lambda=cluster_lambda if cluster_lambda is not None else 1.0,
        homes_per_cluster_lambda=homes_lambda if homes_lambda is not None else 4.0,
        other_locations_per_cluster_lambda=other_locations_lambda if other_locations_lambda is not None else 4.0,
        map_scale=map_scale if map_scale is not None else 100.0,
        min_cluster_spacing=cluster_spacing if cluster_spacing is not None else 40.0,
        intra_cluster_dual_road_chance=dual_road_chance if dual_road_chance is not None else 0.3,
        intra_cluster_roundabout_chance=roundabout_chance if roundabout_chance is not None else 0.15,
        highway_merge_roundabout_chance=highway_roundabout_chance if highway_roundabout_chance is not None else 0.4,
        major_junction_ratio=major_junction_ratio if major_junction_ratio is not None else 0.14,
    )
    journey_start_probability = (
        log_to_linear(journey_start_probability, 0.0001, 1.0) if journey_start_probability is not None else 0.05
    )
    cyclist_journey_start_probability = (
        log_to_linear(cyclist_journey_start_probability, 0.0001, 1.0)
        if cyclist_journey_start_probability is not None
        else 0.01
    )
    unilateral_probability = (
        log_to_linear(unilateral_probability, 0.0001, 0.1) if unilateral_probability is not None else 0.01
    )
    vehicle_encounter_probability = (
        log_to_linear(vehicle_encounter_probability, 0.0001, 0.1)
        if vehicle_encounter_probability is not None
        else 0.03
    )
    cyclist_encounter_probability = (
        log_to_linear(cyclist_encounter_probability, 0.0001, 0.1)
        if cyclist_encounter_probability is not None
        else 0.03
    )

    driver_config = DriverConfig(
        journey_start_probability=journey_start_probability,
        cyclist_journey_start_probability=cyclist_journey_start_probability,
    )
    accident_config = AccidentConfig(
        unilateral_probability=unilateral_probability,
        vehicle_encounter_probability=vehicle_encounter_probability,
        cyclist_encounter_probability=cyclist_encounter_probability,
    )
    return SimulationConfig(
        seed=seed or 42,
        map_config=map_config,
        driver_config=driver_config,
        accident_config=accident_config,
    )


def serialize_sim(simulation: Simulation) -> Dict[str, Any]:
    agents = []
    for agent in simulation.agents.values():
        agents.append(
            {
                "agent_id": agent.agent_id,
                "current_node": agent.current_node,
                "route": agent.route,
                "route_index": agent.route_index,
                "driver": asdict(agent.driver),
                "vehicle": asdict(agent.vehicle),
                "home_node": agent.home_node,
                "home_label": agent.home_label,
                "work_node": agent.work_node,
                "destination_node": agent.destination_node,
                "previous_node": agent.previous_node,
                "agent_type": agent.agent_type,
                "heading": list(agent.heading) if agent.heading else None,
                "lane_index": agent.lane_index,
                "wait_steps": agent.wait_steps,
                "is_idle": agent.is_idle,
                "journey_distance": agent.journey_distance,
            }
        )
    return {
        "config": asdict(simulation.config),
        "map_data": {
            "nodes": {nid: asdict(node) for nid, node in simulation.map_data.nodes.items()},
            "edges": [asdict(edge) for edge in simulation.map_data.edges],
            "adjacency": simulation.map_data.adjacency,
            "pois": simulation.map_data.pois,
        },
        "step_index": simulation.step_index,
        "random_state": [
            simulation.random.getstate()[0],
            list(simulation.random.getstate()[1]),
            simulation.random.getstate()[2],
        ],
        "agents": agents,
        "accidents": [accident.__dict__ for accident in simulation.accidents],
        "metrics": {
            "total_distance": simulation.total_distance,
            "total_journeys_started": simulation.total_journeys_started,
            "total_journeys_completed": simulation.total_journeys_completed,
            "total_journey_distance": simulation.total_journey_distance,
            "journey_distances": simulation.journey_distances,
            "node_visit_counts": simulation.node_visit_counts,
        },
    }


def deserialize_sim(state: Dict[str, Any]) -> Simulation:
    config_data = state["config"]
    driver_config_data = config_data["driver_config"].copy()
    for legacy_field in ["count", "cyclist_count"]:
        if legacy_field in driver_config_data:
            del driver_config_data[legacy_field]
    accident_config_data = config_data.get("accident_config", {})
    config = SimulationConfig(
        seed=config_data["seed"],
        steps=config_data["steps"],
        map_config=MapConfig(**config_data["map_config"]),
        driver_config=DriverConfig(**driver_config_data),
        accident_config=AccidentConfig(**accident_config_data) if accident_config_data else AccidentConfig(),
        time_of_day=config_data.get("time_of_day", "day"),
        enable_parallel=config_data.get("enable_parallel", False),
        parallel_workers=config_data.get("parallel_workers", 2),
    )
    simulation = Simulation(config)
    simulation.step_index = state["step_index"]
    if "random_state" in state:
        rs = state["random_state"]
        simulation.random.setstate((rs[0], tuple(rs[1]), rs[2]))
    metrics = state.get("metrics", {})
    simulation.total_distance = metrics.get("total_distance", 0.0)
    simulation.total_journeys_started = metrics.get("total_journeys_started", 0)
    simulation.total_journeys_completed = metrics.get("total_journeys_completed", 0)
    simulation.total_journey_distance = metrics.get("total_journey_distance", 0.0)
    simulation.journey_distances = metrics.get("journey_distances", [])
    node_visit_counts = metrics.get("node_visit_counts", simulation.node_visit_counts)
    simulation.node_visit_counts = {int(k): v for k, v in node_visit_counts.items()}
    simulation.accidents = [AccidentEvent(**accident) for accident in state.get("accidents", [])]
    for agent in state["agents"]:
        sim_agent = simulation.agents[agent["agent_id"]]
        sim_agent.current_node = agent["current_node"]
        sim_agent.route = agent["route"]
        sim_agent.route_index = agent["route_index"]
        sim_agent.destination_node = agent.get("destination_node", sim_agent.work_node)
        sim_agent.previous_node = agent.get("previous_node", sim_agent.current_node)
        sim_agent.agent_type = agent.get("agent_type", sim_agent.agent_type)
        heading = agent.get("heading")
        sim_agent.heading = tuple(heading) if heading else None
        sim_agent.lane_index = agent.get("lane_index", 0)
        sim_agent.wait_steps = agent.get("wait_steps", 0)
        sim_agent.is_idle = agent.get("is_idle", True)
        sim_agent.home_label = agent.get("home_label", sim_agent.home_label)
        sim_agent.journey_distance = agent.get("journey_distance", 0.0)
    return simulation
