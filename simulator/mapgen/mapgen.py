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
    kind: str = "junction"  # junction, roundabout, residence, work, visit


@dataclass
class Edge:
    start: int
    end: int
    speed_limit: int
    risk_factor: float


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
        for y in range(self.config.height):
            for x in range(self.config.width):
                if self.random.random() > self.config.road_density:
                    continue
                nodes[node_id] = Node(node_id=node_id, x=x, y=y)
                adjacency[node_id] = []
                node_id += 1

        node_positions = {(node.x, node.y): node_id for node_id, node in nodes.items()}
        for node in nodes.values():
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = node_positions.get((node.x + dx, node.y + dy))
                if neighbor is None:
                    continue
                speed_limit = self.random.choice(self.config.speed_limits)
                risk_factor = self.random.uniform(0.8, 1.4)
                edges.append(Edge(start=node.node_id, end=neighbor, speed_limit=speed_limit, risk_factor=risk_factor))
                adjacency[node.node_id].append(neighbor)

        node_ids = list(nodes.keys())
        self.random.shuffle(node_ids)
        roundabouts = node_ids[: self.config.roundabout_count]
        for node_id in roundabouts:
            nodes[node_id].kind = "roundabout"

        poi_sets = {
            "residence": self.config.residential_count,
            "work": self.config.work_count,
            "visit": self.config.visit_count,
        }
        available_nodes = [nid for nid in nodes if nodes[nid].kind == "junction"]
        self.random.shuffle(available_nodes)
        pois: Dict[str, List[int]] = {"residence": [], "work": [], "visit": []}
        idx = 0
        for kind, count in poi_sets.items():
            for _ in range(count):
                if idx >= len(available_nodes):
                    break
                node_id = available_nodes[idx]
                nodes[node_id].kind = kind
                pois[kind].append(node_id)
                idx += 1

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
