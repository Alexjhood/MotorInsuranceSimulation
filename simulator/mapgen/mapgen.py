from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Dict, List, Tuple

from simulator.config import MapConfig


@dataclass
class Node:
    node_id: int
    x: int
    y: int
    kind: str = "junction"  # junction, roundabout, residence, work, commerce, leisure, crossing, cyclist
    district: str = "mixed"  # residential, commercial, work, mixed


@dataclass
class Edge:
    start: int
    end: int
    speed_limit: int
    risk_factor: float
    road_type: str
    lanes: int
    has_cycle_lane: bool
    has_crossing: bool


@dataclass
class MapData:
    nodes: Dict[int, Node]
    edges: List[Edge]
    adjacency: Dict[int, List[int]]
    pois: Dict[str, List[int]] = field(default_factory=dict)


class MapGenerator:
    def __init__(self, config: MapConfig, seed: int) -> None:
        self.config = config
        self.random = random.Random(seed)

    def generate(self) -> MapData:
        nodes: Dict[int, Node] = {}
        adjacency: Dict[int, List[int]] = {}
        edges: List[Edge] = []

        node_id = 0
        district_width = max(1, self.config.width // 3)
        for y in range(self.config.height):
            for x in range(self.config.width):
                if self.random.random() > self.config.road_density:
                    continue
                if x < district_width:
                    district = "residential"
                elif x < district_width * 2:
                    district = "commercial"
                else:
                    district = "work"
                nodes[node_id] = Node(node_id=node_id, x=x, y=y, district=district)
                adjacency[node_id] = []
                node_id += 1

        node_ids = list(nodes.keys())
        self.random.shuffle(node_ids)
        roundabouts = node_ids[: self.config.roundabout_count]
        for node_id in roundabouts:
            nodes[node_id].kind = "roundabout"

        poi_sets = {
            "residence": self.config.residential_count,
            "work": self.config.work_count,
            "commerce": self.config.commerce_count,
            "leisure": self.config.leisure_count,
            "crossing": self.config.pedestrian_crossing_count,
            "cyclist": self.config.cyclist_hub_count,
        }
        available_nodes = [nid for nid in nodes if nodes[nid].kind == "junction"]
        self.random.shuffle(available_nodes)
        pois: Dict[str, List[int]] = {
            "residence": [],
            "work": [],
            "commerce": [],
            "leisure": [],
            "crossing": [],
            "cyclist": [],
        }
        idx = 0
        def _filter_by_district(options: List[int], target: str) -> List[int]:
            return [nid for nid in options if nodes[nid].district == target]

        for kind, count in poi_sets.items():
            for _ in range(count):
                if idx >= len(available_nodes):
                    break
                if kind == "residence":
                    candidates = _filter_by_district(available_nodes[idx:], "residential")
                elif kind in {"commerce", "leisure", "crossing", "cyclist"}:
                    candidates = _filter_by_district(available_nodes[idx:], "commercial")
                elif kind == "work":
                    candidates = _filter_by_district(available_nodes[idx:], "work")
                else:
                    candidates = available_nodes[idx:]
                node_id = candidates[0] if candidates else available_nodes[idx]
                nodes[node_id].kind = kind
                pois[kind].append(node_id)
                idx += 1

        node_positions = {(node.x, node.y): node_id for node_id, node in nodes.items()}
        for node in nodes.values():
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = node_positions.get((node.x + dx, node.y + dy))
                if neighbor is None:
                    continue
                neighbor_node = nodes[neighbor]
                if node.district != neighbor_node.district:
                    road_type = "highway"
                elif node.district == "residential":
                    road_type = self.random.choices(["single_lane", "two_lane"], weights=[0.75, 0.25], k=1)[0]
                elif node.district == "commercial":
                    road_type = self.random.choices(["two_lane", "single_lane"], weights=[0.7, 0.3], k=1)[0]
                else:
                    road_type = self.random.choices(["two_lane", "single_lane"], weights=[0.65, 0.35], k=1)[0]
                speed_limit = self.config.speed_limits_by_type.get(road_type, 30)
                lanes = self.config.lanes_by_type.get(road_type, 1)
                risk_factor = self.random.uniform(0.8, 1.4)
                has_crossing = node.kind == "crossing" or neighbor_node.kind == "crossing"
                has_cycle_lane = self.random.random() < self.config.cycle_lane_chance
                edges.append(
                    Edge(
                        start=node.node_id,
                        end=neighbor,
                        speed_limit=speed_limit,
                        risk_factor=risk_factor,
                        road_type=road_type,
                        lanes=lanes,
                        has_cycle_lane=has_cycle_lane,
                        has_crossing=has_crossing,
                    )
                )
                adjacency[node.node_id].append(neighbor)

        return MapData(nodes=nodes, edges=edges, adjacency=adjacency, pois=pois)


def shortest_path(adjacency: Dict[int, List[int]], start: int, goal: int) -> List[int]:
    if start == goal:
        return [start]
    queue: List[int] = [start]
    came_from: Dict[int, int | None] = {start: None}
    for current in queue:
        for neighbor in adjacency.get(current, []):
            if neighbor in came_from:
                continue
            came_from[neighbor] = current
            if neighbor == goal:
                queue = []
                break
            queue.append(neighbor)
    if goal not in came_from:
        return [start]
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    path.reverse()
    return path
