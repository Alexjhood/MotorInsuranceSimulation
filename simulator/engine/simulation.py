from __future__ import annotations

from dataclasses import dataclass, replace
import random
import heapq
import time
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
    home_label: str  # Label for the home location (e.g., "H1", "H2")
    work_node: int
    destination_node: int
    previous_node: int
    agent_type: str
    heading: Tuple[int, int] | None
    lane_index: int
    wait_steps: int
    is_idle: bool = True  # True when agent is not on a journey
    journey_distance: float = 0.0


@dataclass
class StepTiming:
    """Detailed timing breakdown for a simulation step."""
    agent_movement_ms: float = 0.0
    lane_assignment_ms: float = 0.0
    occupancy_calc_ms: float = 0.0
    unilateral_accidents_ms: float = 0.0
    multi_agent_accidents_ms: float = 0.0
    event_logging_ms: float = 0.0
    total_step_ms: float = 0.0


@dataclass
class SimulationStepResult:
    step: int
    accidents: List[AccidentEvent]
    events: List[dict]
    timing: StepTiming | None = None


class Simulation:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.random = random.Random(config.seed)
        self.map_data = MapGenerator(self.config.map_config, self.config.seed).generate()
        self.edge_lookup = {(edge.start, edge.end): edge for edge in self.map_data.edges}
        self.node_edge = {edge.start: edge for edge in self.map_data.edges}
        self.default_edge = self.map_data.edges[0] if self.map_data.edges else None
        self.node_wait_steps = {
            node_id: 1 if node.kind in {"roundabout", "major_junction"} else 0
            for node_id, node in self.map_data.nodes.items()
        }
        self.nav_adjacency = self._build_navigation_graph(self.map_data)
        self.node_accident_multiplier = {
            node_id: self._compute_accident_multiplier(node_id)
            for node_id in self.map_data.nodes
        }
        self.route_cache: Dict[Tuple[int, int], Tuple[int, ...]] = {}
        self.agents: Dict[int, AgentState] = {}
        self.step_index = 0
        self.event_log: List[dict] = []
        self.accidents: List[AccidentEvent] = []
        self.total_distance = 0.0
        self.total_journeys_started = 0
        self.total_journeys_completed = 0
        self.total_journey_distance = 0.0
        self.journey_distances: List[float] = []
        self.node_visit_counts = {node_id: 0 for node_id in self.map_data.nodes}
        self._init_agents()

    def _pick_node(self, kind: str) -> int:
        choices = self.map_data.pois.get(kind, [])
        if not choices:
            return self.random.choice(list(self.map_data.nodes.keys()))
        return self.random.choice(choices)

    def _init_agents(self) -> None:
        risk_levels = list(self.config.driver_config.risk_profiles.keys())
        risk_weights = list(self.config.driver_config.risk_profiles.values())
        
        # Create one driver agent AND one cyclist per home (residence)
        all_homes = list(self.map_data.pois.get("residence", []))
        agent_id = 0
        
        for home_index, home_node in enumerate(all_homes):
            home_label = f"H{home_index + 1}"  # Home labels: H1, H2, H3, etc.
            
            # Create driver for this home
            risk_level = self.random.choices(risk_levels, weights=risk_weights, k=1)[0]
            driver = build_driver(risk_level)
            vehicle_class = self.random.choice(VEHICLE_CLASSES)
            vehicle = VehicleProfile(*vehicle_class)
            work_node = self._pick_node("work")
            
            self.agents[agent_id] = AgentState(
                agent_id=agent_id,
                current_node=home_node,
                route=[home_node],
                route_index=0,
                driver=driver,
                vehicle=vehicle,
                home_node=home_node,
                home_label=home_label,
                work_node=work_node,
                destination_node=home_node,
                previous_node=home_node,
                agent_type="driver",
                heading=None,
                lane_index=0,
                wait_steps=0,
                is_idle=True,
                journey_distance=0.0,
            )
            agent_id += 1
            
            # Create cyclist for this home
            self.agents[agent_id] = AgentState(
                agent_id=agent_id,
                current_node=home_node,
                route=[home_node],
                route_index=0,
                driver=build_driver("low"),
                vehicle=BICYCLE_PROFILE,
                home_node=home_node,
                home_label=home_label,
                work_node=self._pick_node("commerce"),
                destination_node=home_node,
                previous_node=home_node,
                agent_type="cyclist",
                heading=None,
                lane_index=0,
                wait_steps=0,
                is_idle=True,
                journey_distance=0.0,
            )
            agent_id += 1

    def _node_wait_steps(self, node_id: int) -> int:
        return self.node_wait_steps.get(node_id, 0)

    def _select_destination(self, agent: AgentState) -> int:
        """Select a destination for the agent. Can include other homes."""
        commerce = self.map_data.pois.get("commerce", [])
        leisure = self.map_data.pois.get("leisure", [])
        cyclist_hubs = self.map_data.pois.get("cyclist", [])
        residences = self.map_data.pois.get("residence", [])
        work_locations = self.map_data.pois.get("work", [])
        
        # Filter out current location from options
        other_homes = [h for h in residences if h != agent.current_node]
        
        if agent.agent_type == "cyclist":
            options = leisure + commerce + cyclist_hubs + other_homes
            return self.random.choice(options) if options else agent.home_node
        
        # For drivers, select from various location types
        if agent.current_node == agent.home_node:
            # From home, can go to work, commerce, leisure, or visit other homes
            options = work_locations + commerce + leisure + other_homes
        elif agent.current_node == agent.work_node:
            # From work, go to commerce, leisure, other homes, or back home
            options = commerce + leisure + other_homes + [agent.home_node]
        else:
            # From other locations, go home or to another destination
            options = [agent.home_node] + commerce + leisure + other_homes
        
        return self.random.choice(options) if options else agent.home_node

    def _advance_agent(self, agent: AgentState) -> Dict[str, float | int | None]:
        # Handle wait steps (at junctions/roundabouts)
        if agent.wait_steps > 0:
            agent.wait_steps -= 1
            return {"agent_id": agent.agent_id, "node": agent.current_node, "action": "wait"}
        
        # Handle idle agents (not currently on a journey)
        if agent.is_idle:
            # Use agent-type-specific journey start probability
            if agent.agent_type == "cyclist":
                journey_prob = self.config.driver_config.cyclist_journey_start_probability
            else:
                journey_prob = self.config.driver_config.journey_start_probability
            
            if self.random.random() < journey_prob:
                # Start a new journey
                agent.destination_node = self._select_destination(agent)
                agent.route = self._find_route(agent.current_node, agent.destination_node)
                agent.route_index = 0
                agent.is_idle = False
                agent.journey_distance = 0.0
                self.total_journeys_started += 1
            else:
                # Stay idle
                return {"agent_id": agent.agent_id, "node": agent.current_node, "action": "idle"}
        
        # Check if journey is complete
        if agent.route_index + 1 >= len(agent.route):
            # Arrived at destination, become idle
            agent.is_idle = True
            if agent.journey_distance > 0:
                self.total_journeys_completed += 1
                self.total_journey_distance += agent.journey_distance
                self.journey_distances.append(agent.journey_distance)
                agent.journey_distance = 0.0
            return {"agent_id": agent.agent_id, "node": agent.current_node, "action": "arrived"}
        
        # Continue journey
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
        dx = target_node.x - current_node.x
        dy = target_node.y - current_node.y
        distance = (dx * dx + dy * dy) ** 0.5
        agent.journey_distance += distance
        self.total_distance += distance
        return {"agent_id": agent.agent_id, "node": next_node, "action": "move"}

    @staticmethod
    def _rand_float(seed: int) -> float:
        value = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return value / float(1 << 64)

    def step(self) -> SimulationStepResult:
        total_start = time.perf_counter()
        timing = StepTiming()
        
        self.step_index += 1
        step_events: List[dict] = []
        accidents: List[AccidentEvent] = []

        # Phase 1: Agent movement
        t0 = time.perf_counter()
        movements = [self._advance_agent(agent) for agent in self.agents.values()]
        step_events.extend({"type": "movement", **movement, "step": self.step_index} for movement in movements)
        timing.agent_movement_ms = (time.perf_counter() - t0) * 1000

        # Phase 2: Lane assignment
        t0 = time.perf_counter()
        self._assign_lanes()
        timing.lane_assignment_ms = (time.perf_counter() - t0) * 1000

        # Phase 3: Calculate node occupancy
        t0 = time.perf_counter()
        node_occupancy: Dict[int, List[int]] = {}
        for agent in self.agents.values():
            node_occupancy.setdefault(agent.current_node, []).append(agent.agent_id)
        for node_id, agents_at_node in node_occupancy.items():
            self.node_visit_counts[node_id] = self.node_visit_counts.get(node_id, 0) + len(agents_at_node)
        timing.occupancy_calc_ms = (time.perf_counter() - t0) * 1000

        # Phase 4: Unilateral accidents
        t0 = time.perf_counter()
        for node_id, agents_at_node in node_occupancy.items():
            if len(agents_at_node) < 1:
                continue

            edge = self.node_edge.get(node_id, self.default_edge)
            multiplier = self.node_accident_multiplier.get(node_id, 1.0)
            accident_config = self.config.accident_config
            
            # Only check accidents for agents that are actively moving (not idle)
            active_agents = [aid for aid in agents_at_node if not self.agents[aid].is_idle]
            
            # Unilateral accidents - only for drivers (cyclists cannot have unilateral accidents)
            active_drivers = [aid for aid in active_agents if self.agents[aid].agent_type == "driver"]
            for agent_id in active_drivers:
                agent = self.agents[agent_id]
                base_seed = self.config.seed + self.step_index * 1_000_003 + agent_id * 9_973
                
                # Base unilateral probability with multipliers
                unilateral_prob = accident_config.unilateral_probability * multiplier
                
                if self._rand_float(base_seed) < unilateral_prob:
                    rng = random.Random(base_seed)
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
        timing.unilateral_accidents_ms = (time.perf_counter() - t0) * 1000

        # Phase 5: Multi-agent accidents
        t0 = time.perf_counter()
        for node_id, agents_at_node in node_occupancy.items():
            if len(agents_at_node) < 1:
                continue
            
            edge = self.node_edge.get(node_id, self.default_edge)
            multiplier = self.node_accident_multiplier.get(node_id, 1.0)
            accident_config = self.config.accident_config
            active_agents = [aid for aid in agents_at_node if not self.agents[aid].is_idle]

            # Multi-agent encounters
            if len(active_agents) > 1:
                base_seed = self.config.seed + self.step_index * 2_000_003 + node_id * 9_947
                
                # Separate drivers from cyclists
                drivers = [aid for aid in active_agents if self.agents[aid].agent_type == "driver"]
                cyclists = [aid for aid in active_agents if self.agents[aid].agent_type == "cyclist"]
                
                # Vehicle-vehicle encounters
                if len(drivers) > 1:
                    vehicle_prob = accident_config.vehicle_encounter_probability * multiplier
                    if self._rand_float(base_seed + 11) < vehicle_prob:
                        participant_ids = drivers[:2]
                        profiles = [self.agents[pid].driver for pid in participant_ids]
                        vehicles = [self.agents[pid].vehicle for pid in participant_ids]
                        speed = edge.speed_limit * sum(p.speed_bias for p in profiles) / len(profiles)
                        accidents.append(
                            build_accident(
                                step=self.step_index,
                                location=node_id,
                                participant_ids=participant_ids,
                                driver_profiles=profiles,
                                vehicle_profiles=vehicles,
                                speed=speed,
                                rng=random.Random(base_seed + 12),
                            )
                        )
                
                # Vehicle-cyclist encounters
                if drivers and cyclists:
                    cyclist_prob = accident_config.cyclist_encounter_probability * multiplier
                    if self._rand_float(base_seed + 21) < cyclist_prob:
                        participant_ids = [drivers[0], cyclists[0]]
                        profiles = [self.agents[pid].driver for pid in participant_ids]
                        vehicles = [self.agents[pid].vehicle for pid in participant_ids]
                        speed = edge.speed_limit * self.agents[drivers[0]].driver.speed_bias
                        accidents.append(
                            build_accident(
                                step=self.step_index,
                                location=node_id,
                                participant_ids=participant_ids,
                                driver_profiles=profiles,
                                vehicle_profiles=vehicles,
                                speed=speed,
                                rng=random.Random(base_seed + 22),
                            )
                        )
        timing.multi_agent_accidents_ms = (time.perf_counter() - t0) * 1000

        # Phase 6: Event logging
        t0 = time.perf_counter()
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
        timing.event_logging_ms = (time.perf_counter() - t0) * 1000
        
        timing.total_step_ms = (time.perf_counter() - total_start) * 1000
        return SimulationStepResult(step=self.step_index, accidents=accidents, events=step_events, timing=timing)

    def _edge_for_node(self, node_id: int) -> "Edge" | None:
        return self.node_edge.get(node_id, self.default_edge)

    def _compute_accident_multiplier(self, node_id: int) -> float:
        """Compute the combined multiplier based on road type and junction type."""
        accident_config = self.config.accident_config

        edge = self._edge_for_node(node_id)
        if edge is None:
            return 1.0

        # Road type multiplier
        road_multiplier = accident_config.road_type_multipliers.get(edge.road_type, 1.0)
        
        # Junction type multiplier
        node = self.map_data.nodes[node_id]
        junction_multiplier = accident_config.junction_multipliers.get(node.kind, 1.0)
        
        return road_multiplier * junction_multiplier

    def _build_navigation_graph(self, map_data: MapData) -> Dict[int, List[Tuple[int, float]]]:
        adjacency: Dict[int, List[Tuple[int, float]]] = {node_id: [] for node_id in map_data.nodes}
        for edge in map_data.edges:
            weight = self._edge_weight(edge.road_type)
            adjacency[edge.start].append((edge.end, weight))
        return adjacency

    def _edge_weight(self, road_type: str) -> float:
        weights = {"highway": 0.7, "dual_carriageway": 0.85, "single_lane": 1.0}
        return weights.get(road_type, 1.0)

    def _heuristic(self, node_id: int, goal_id: int) -> float:
        node = self.map_data.nodes[node_id]
        goal = self.map_data.nodes[goal_id]
        dx = goal.x - node.x
        dy = goal.y - node.y
        return (dx * dx + dy * dy) ** 0.5

    def _find_route(self, start: int, goal: int) -> List[int]:
        cached = self.route_cache.get((start, goal))
        if cached is not None:
            return list(cached)
        if start == goal:
            return [start]
        g_scores: Dict[int, float] = {start: 0.0}
        came_from: Dict[int, int | None] = {start: None}
        queue: List[Tuple[float, float, int]] = [(self._heuristic(start, goal), 0.0, start)]
        visited: set[int] = set()

        while queue:
            _, current_g, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current == goal:
                break
            for neighbor, weight in self.nav_adjacency.get(current, []):
                tentative_g = current_g + weight
                if tentative_g < g_scores.get(neighbor, float("inf")):
                    g_scores[neighbor] = tentative_g
                    came_from[neighbor] = current
                    f_score = tentative_g + self._heuristic(neighbor, goal)
                    heapq.heappush(queue, (f_score, tentative_g, neighbor))

        if goal not in came_from:
            return [start]
        path = [goal]
        while path[-1] != start:
            path.append(came_from[path[-1]])
        path.reverse()
        self.route_cache[(start, goal)] = tuple(path)
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
            for idx, agent_id in enumerate(agent_ids):
                lane_index = allowed[idx % len(allowed)]
                self.agents[agent_id].lane_index = lane_index

    def run(self, steps: int | None = None) -> List[SimulationStepResult]:
        if steps is None:
            steps = self.config.steps
        results = []
        for _ in range(steps):
            results.append(self.step())
        return results
