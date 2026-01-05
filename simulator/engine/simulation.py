from __future__ import annotations

from dataclasses import dataclass, replace
import random
from typing import Dict, List

from simulator.accidents.model import AccidentEvent, accident_probability, build_accident
from simulator.agents.driver import DriverProfile, build_driver
from simulator.agents.vehicle import VEHICLE_CLASSES, VehicleProfile
from simulator.config import SimulationConfig
from simulator.mapgen.mapgen import MapData, MapGenerator, shortest_path


@dataclass
class AgentState:
    agent_id: int
    current_node: int
    route: List[int]
    route_index: int
    driver: DriverProfile
    vehicle: VehicleProfile
    home_node: int
    work_node: int
    destination_node: int
    previous_node: int


@dataclass
class SimulationStepResult:
    step: int
    accidents: List[AccidentEvent]
    events: List[dict]


class Simulation:
    def __init__(self, config: SimulationConfig) -> None:
        if config.map_config.residential_count < config.driver_config.count:
            map_config = replace(config.map_config, residential_count=config.driver_config.count)
            self.config = replace(config, map_config=map_config)
        else:
            self.config = config
        self.random = random.Random(config.seed)
        self.map_data = MapGenerator(self.config.map_config, self.config.seed).generate()
        self.agents: Dict[int, AgentState] = {}
        self.step_index = 0
        self.event_log: List[dict] = []
        self.accidents: List[AccidentEvent] = []
        self._init_agents()

    def _pick_node(self, kind: str) -> int:
        choices = self.map_data.pois.get(kind, [])
        if not choices:
            return self.random.choice(list(self.map_data.nodes.keys()))
        return self.random.choice(choices)

    def _init_agents(self) -> None:
        risk_levels = list(self.config.driver_config.risk_profiles.keys())
        risk_weights = list(self.config.driver_config.risk_profiles.values())
        available_homes = list(self.map_data.pois.get("residence", []))
        self.random.shuffle(available_homes)
        for agent_id in range(self.config.driver_config.count):
            risk_level = self.random.choices(risk_levels, weights=risk_weights, k=1)[0]
            driver = build_driver(risk_level)
            vehicle_class = self.random.choice(VEHICLE_CLASSES)
            vehicle = VehicleProfile(*vehicle_class)
            home_node = available_homes.pop() if available_homes else self._pick_node("residence")
            work_node = self._pick_node("work")
            route = shortest_path(self.map_data.adjacency, home_node, work_node)
            self.agents[agent_id] = AgentState(
                agent_id=agent_id,
                current_node=home_node,
                route=route,
                route_index=0,
                driver=driver,
                vehicle=vehicle,
                home_node=home_node,
                work_node=work_node,
                destination_node=work_node,
                previous_node=home_node,
            )

    def _select_destination(self, agent: AgentState) -> int:
        commerce = self.map_data.pois.get("commerce", [])
        leisure = self.map_data.pois.get("leisure", [])
        if agent.destination_node == agent.work_node:
            options = commerce + leisure
            return self.random.choice(options) if options else agent.home_node
        if agent.destination_node in commerce + leisure:
            return agent.home_node
        return agent.work_node

    def _advance_agent(self, agent: AgentState) -> Dict[str, float | int | None]:
        if agent.route_index + 1 >= len(agent.route):
            agent.destination_node = self._select_destination(agent)
            agent.route = shortest_path(self.map_data.adjacency, agent.current_node, agent.destination_node)
            agent.route_index = 0
        next_index = min(agent.route_index + 1, len(agent.route) - 1)
        next_node = agent.route[next_index]
        agent.route_index = next_index
        agent.previous_node = agent.current_node
        agent.current_node = next_node
        return {"agent_id": agent.agent_id, "node": next_node}

    def step(self) -> SimulationStepResult:
        self.step_index += 1
        step_events: List[dict] = []
        accidents: List[AccidentEvent] = []

        movements = [self._advance_agent(agent) for agent in self.agents.values()]
        step_events.extend({"type": "movement", **movement, "step": self.step_index} for movement in movements)

        node_occupancy: Dict[int, List[int]] = {}
        for agent in self.agents.values():
            node_occupancy.setdefault(agent.current_node, []).append(agent.agent_id)

        for node_id, agents in node_occupancy.items():
            if len(agents) < 1:
                continue
            edge = self._edge_for_node(node_id)
            for agent_id in agents:
                agent = self.agents[agent_id]
                rng = random.Random(self.config.seed + self.step_index * 1000 + agent_id)
                probability = accident_probability(edge, agent.driver, self.config.time_of_day)
                if rng.random() < probability:
                    speed = edge.speed_limit * agent.driver.speed_bias
                    accident = build_accident(
                        step=self.step_index,
                        location=node_id,
                        participant_ids=[agent_id],
                        driver_profiles=[agent.driver],
                        vehicle_profiles=[agent.vehicle],
                        speed=speed,
                        rng=rng,
                    )
                    accidents.append(accident)

            if len(agents) > 1:
                collision_probability = min(0.02 * len(agents), 0.15)
                rng = random.Random(self.config.seed + self.step_index * 2000 + node_id)
                if rng.random() < collision_probability:
                    participant_ids = agents[:2]
                    profiles = [self.agents[pid].driver for pid in participant_ids]
                    vehicles = [self.agents[pid].vehicle for pid in participant_ids]
                    speed = edge.speed_limit * sum(profile.speed_bias for profile in profiles) / len(profiles)
                    accidents.append(
                        build_accident(
                            step=self.step_index,
                            location=node_id,
                            participant_ids=participant_ids,
                            driver_profiles=profiles,
                            vehicle_profiles=vehicles,
                            speed=speed,
                            rng=rng,
                        )
                    )

        for accident in accidents:
            step_events.append({
                "type": "accident",
                "step": accident.step,
                "location": accident.location,
                "participants": accident.participants,
                "severity": accident.severity,
                "total_claim": accident.total_claim,
            })
            self.accidents.append(accident)

        self.event_log.extend(step_events)
        return SimulationStepResult(step=self.step_index, accidents=accidents, events=step_events)

    def _edge_for_node(self, node_id: int) -> "Edge":
        for edge in self.map_data.edges:
            if edge.start == node_id:
                return edge
        return self.map_data.edges[0]

    def run(self, steps: int | None = None) -> List[SimulationStepResult]:
        if steps is None:
            steps = self.config.steps
        results = []
        for _ in range(steps):
            results.append(self.step())
        return results
