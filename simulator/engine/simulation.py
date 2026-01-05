from __future__ import annotations

from dataclasses import dataclass, replace
import random
import heapq
from typing import Dict, List, Tuple

from simulator.accidents.model import AccidentEvent, accident_probability, build_accident
from simulator.agents.driver import DriverProfile, build_driver
from simulator.agents.vehicle import BICYCLE_PROFILE, VEHICLE_CLASSES, VehicleProfile
from simulator.config import SimulationConfig
from simulator.mapgen.mapgen import MapData, MapGenerator


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
    agent_type: str
    heading: Tuple[int, int] | None
    lane_index: int
    wait_steps: int


@dataclass
class SimulationStepResult:
    step: int
    accidents: List[AccidentEvent]
    events: List[dict]


class Simulation:
    def __init__(self, config: SimulationConfig) -> None:
        # Ensure minimum residences can accommodate drivers
        if config.map_config.min_residences < config.driver_config.count:
            map_config = replace(config.map_config, min_residences=config.driver_config.count)
            self.config = replace(config, map_config=map_config)
        else:
            self.config = config
        self.random = random.Random(config.seed)
        self.map_data = MapGenerator(self.config.map_config, self.config.seed).generate()
        self.edge_lookup = {(edge.start, edge.end): edge for edge in self.map_data.edges}
        self.nav_adjacency = self._build_navigation_graph(self.map_data)
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
        agent_id = 0
        for _ in range(self.config.driver_config.count):
            risk_level = self.random.choices(risk_levels, weights=risk_weights, k=1)[0]
            driver = build_driver(risk_level)
            vehicle_class = self.random.choice(VEHICLE_CLASSES)
            vehicle = VehicleProfile(*vehicle_class)
            home_node = available_homes.pop() if available_homes else self._pick_node("residence")
            work_node = self._pick_node("work")
            route = self._find_route(home_node, work_node)
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
                agent_type="driver",
                heading=None,
                lane_index=0,
                wait_steps=self._node_wait_steps(home_node),
            )
            agent_id += 1

        cyclist_hubs = list(self.map_data.pois.get("cyclist", []))
        self.random.shuffle(cyclist_hubs)
        for _ in range(self.config.driver_config.cyclist_count):
            if cyclist_hubs:
                home_node = cyclist_hubs.pop()
            else:
                home_node = self._pick_node("cyclist")
            destination_node = self._pick_node("commerce")
            route = self._find_route(home_node, destination_node)
            self.agents[agent_id] = AgentState(
                agent_id=agent_id,
                current_node=home_node,
                route=route,
                route_index=0,
                driver=build_driver("low"),
                vehicle=BICYCLE_PROFILE,
                home_node=home_node,
                work_node=destination_node,
                destination_node=destination_node,
                previous_node=home_node,
                agent_type="cyclist",
                heading=None,
                lane_index=0,
                wait_steps=self._node_wait_steps(home_node),
            )
            agent_id += 1

    def _node_wait_steps(self, node_id: int) -> int:
        node_kind = self.map_data.nodes[node_id].kind
        return 1 if node_kind in {"roundabout", "major_junction"} else 0

    def _select_destination(self, agent: AgentState) -> int:
        commerce = self.map_data.pois.get("commerce", [])
        leisure = self.map_data.pois.get("leisure", [])
        cyclist_hubs = self.map_data.pois.get("cyclist", [])
        if agent.agent_type == "cyclist":
            options = leisure + commerce + cyclist_hubs
            return self.random.choice(options) if options else agent.home_node
        if agent.destination_node == agent.work_node:
            options = commerce + leisure
            return self.random.choice(options) if options else agent.home_node
        if agent.destination_node in commerce + leisure:
            return agent.home_node
        return agent.work_node
        choices = (
            [agent.home_node, agent.work_node]
            + self.map_data.pois.get("commerce", [])
            + self.map_data.pois.get("leisure", [])
        )
        return self.random.choice(choices)

    def _advance_agent(self, agent: AgentState) -> Dict[str, float | int | None]:
        if agent.wait_steps > 0:
            agent.wait_steps -= 1
            return {"agent_id": agent.agent_id, "node": agent.current_node, "action": "wait"}
        if agent.route_index + 1 >= len(agent.route):
            agent.destination_node = self._select_destination(agent)
            agent.route = self._find_route(agent.current_node, agent.destination_node)
            agent.route_index = 0
        next_index = min(agent.route_index + 1, len(agent.route) - 1)
        next_node = agent.route[next_index]
        current_node = self.map_data.nodes[agent.current_node]
        target_node = self.map_data.nodes[next_node]
        desired_heading = (target_node.x - current_node.x, target_node.y - current_node.y)
        if agent.heading is None or agent.heading != desired_heading:
            agent.heading = desired_heading
            return {"agent_id": agent.agent_id, "node": agent.current_node, "action": "turn"}
        agent.route_index = next_index
        agent.previous_node = agent.current_node
        agent.current_node = next_node
        agent.heading = desired_heading
        agent.wait_steps = self._node_wait_steps(next_node)
        return {"agent_id": agent.agent_id, "node": next_node, "action": "move"}

    def step(self) -> SimulationStepResult:
        self.step_index += 1
        step_events: List[dict] = []
        accidents: List[AccidentEvent] = []

        movements = [self._advance_agent(agent) for agent in self.agents.values()]
        step_events.extend({"type": "movement", **movement, "step": self.step_index} for movement in movements)
        self._assign_lanes()

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

    def _build_navigation_graph(self, map_data: MapData) -> Dict[int, List[Tuple[int, float]]]:
        adjacency: Dict[int, List[Tuple[int, float]]] = {node_id: [] for node_id in map_data.nodes}
        for edge in map_data.edges:
            weight = self._edge_weight(edge.road_type)
            adjacency[edge.start].append((edge.end, weight))
        return adjacency

    def _edge_weight(self, road_type: str) -> float:
        weights = {"highway": 0.7, "dual_carriageway": 0.85, "single_lane": 1.0}
        return weights.get(road_type, 1.0)

    def _find_route(self, start: int, goal: int) -> List[int]:
        if start == goal:
            return [start]
        distances: Dict[int, float] = {start: 0.0}
        came_from: Dict[int, int | None] = {start: None}
        queue: List[Tuple[float, int]] = [(0.0, start)]
        visited: set[int] = set()

        while queue:
            current_dist, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current == goal:
                break
            for neighbor, weight in self.nav_adjacency.get(current, []):
                new_dist = current_dist + weight
                if new_dist < distances.get(neighbor, float("inf")):
                    distances[neighbor] = new_dist
                    came_from[neighbor] = current
                    heapq.heappush(queue, (new_dist, neighbor))

        if goal not in came_from:
            return [start]
        path = [goal]
        while path[-1] != start:
            path.append(came_from[path[-1]])
        path.reverse()
        return path

    def _assign_lanes(self) -> None:
        edge_groups: Dict[Tuple[int, int], List[int]] = {}
        for agent in self.agents.values():
            if agent.previous_node != agent.current_node:
                edge_groups.setdefault((agent.previous_node, agent.current_node), []).append(agent.agent_id)

        for edge_key, agent_ids in edge_groups.items():
            edge = self.edge_lookup.get(edge_key)
            lanes = edge.lanes if edge else 1
            if edge and edge.road_type == "highway" and lanes > 1:
                allowed = list(range(max(lanes - 2, 0), lanes))
            elif lanes > 1:
                allowed = [lanes - 1]
            else:
                allowed = [0]
            for idx, agent_id in enumerate(sorted(agent_ids)):
                lane_index = allowed[idx % len(allowed)]
                self.agents[agent_id].lane_index = lane_index

    def run(self, steps: int | None = None) -> List[SimulationStepResult]:
        if steps is None:
            steps = self.config.steps
        results = []
        for _ in range(steps):
            results.append(self.step())
        return results
