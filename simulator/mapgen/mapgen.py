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
    kind: str = "junction"  # junction, major_junction, minor_junction, roundabout, residence, work, commerce, leisure, crossing, cyclist
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
        for y in range(self.config.height):
            for x in range(self.config.width):
                if self.random.random() > self.config.road_density:
                    continue
                nodes[node_id] = Node(node_id=node_id, x=x, y=y)
                adjacency[node_id] = []
                node_id += 1

        if not nodes:
            return MapData(nodes=nodes, edges=edges, adjacency=adjacency, pois={})

        clusters = self._build_clusters(list(nodes.values()))
        for node in nodes.values():
            node.district = self._assign_cluster(node, clusters)

        node_positions = {(node.x, node.y): node_id for node_id, node in nodes.items()}
        trunk_positions = self._carve_trunk_routes(nodes, adjacency, node_positions, clusters, node_id)
        node_id = max(nodes.keys(), default=-1) + 1

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

        single_weight = self.config.road_type_weights.get("single_lane", 0.6)
        two_weight = self.config.road_type_weights.get("two_lane", 0.4)
        highway_weight = self.config.road_type_weights.get("highway", 0.0)
        total_weight = single_weight + two_weight or 1.0
        for node in nodes.values():
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = node_positions.get((node.x + dx, node.y + dy))
                if neighbor is None:
                    continue
                neighbor_node = nodes[neighbor]
                if (node.x, node.y) in trunk_positions and (neighbor_node.x, neighbor_node.y) in trunk_positions:
                    road_type = "highway"
                elif node.district != neighbor_node.district:
                    road_type = "highway"
                elif highway_weight and (
                    (node.x, node.y) in trunk_positions or (neighbor_node.x, neighbor_node.y) in trunk_positions
                ):
                    road_type = self.random.choices(
                        ["single_lane", "two_lane", "highway"],
                        weights=[single_weight, two_weight, highway_weight],
                        k=1,
                    )[0]
                else:
                    road_type = self.random.choices(
                        ["single_lane", "two_lane"],
                        weights=[single_weight / total_weight, two_weight / total_weight],
                        k=1,
                    )[0]
                speed_limit = self.config.speed_limits_by_type.get(road_type, 30)
                lanes = self.config.lanes_by_type.get(road_type, 1)
                risk_factor = self.random.uniform(0.8, 1.4)
                has_crossing = node.kind == "crossing" or nodes[neighbor].kind == "crossing"
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

        self._assign_junction_types(nodes, adjacency, trunk_positions)
        return MapData(nodes=nodes, edges=edges, adjacency=adjacency, pois=pois)

    def _carve_trunk_routes(
        self,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        node_positions: Dict[Tuple[int, int], int],
        clusters: Dict[str, List[Tuple[int, int]]],
        node_id: int,
    ) -> set[Tuple[int, int]]:
        trunk_positions: set[Tuple[int, int]] = set()
        residential = clusters.get("residential", [])
        commercial = clusters.get("commercial", [])
        work = clusters.get("work", [])
        pair_count = min(len(residential), len(commercial), len(work))
        trunk_pairs: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        for idx in range(pair_count):
            trunk_pairs.extend(
                [
                    (residential[idx], commercial[idx]),
                    (commercial[idx], work[idx]),
                    (residential[idx], work[idx]),
                ]
            )
        if not trunk_pairs:
            centers = [*residential, *commercial, *work]
            if len(centers) >= 2:
                trunk_pairs.append((centers[0], centers[-1]))

        def ensure_node(x: int, y: int) -> int:
            nonlocal node_id
            existing = node_positions.get((x, y))
            if existing is not None:
                return existing
            nodes[node_id] = Node(node_id=node_id, x=x, y=y)
            nodes[node_id].district = self._assign_cluster(nodes[node_id], clusters)
            adjacency[node_id] = []
            node_positions[(x, y)] = node_id
            node_id += 1
            return node_id - 1

        for start, end in trunk_pairs:
            for x, y in self._manhattan_path(start, end):
                ensure_node(x, y)
                trunk_positions.add((x, y))
        return trunk_positions

    def _manhattan_path(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        path = []
        x, y = start
        end_x, end_y = end
        step_x = 1 if end_x >= x else -1
        step_y = 1 if end_y >= y else -1
        while x != end_x:
            path.append((x, y))
            x += step_x
        while y != end_y:
            path.append((x, y))
            y += step_y
        path.append((x, y))
        return path

    def _assign_junction_types(
        self,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        trunk_positions: set[Tuple[int, int]],
    ) -> None:
        junction_nodes = [
            node_id
            for node_id, node in nodes.items()
            if node.kind == "junction" and (node.x, node.y) in trunk_positions
        ]
        if not junction_nodes:
            junction_nodes = [node_id for node_id, node in nodes.items() if node.kind == "junction"]
        junction_nodes.sort(key=lambda nid: len(adjacency.get(nid, [])), reverse=True)
        major_count = max(1, len(junction_nodes) // 8)
        major_set = set(junction_nodes[:major_count])
        for node_id, node in nodes.items():
            if node.kind != "junction":
                continue
            node.kind = "major_junction" if node_id in major_set else "minor_junction"

    def _build_clusters(self, nodes: List[Node]) -> Dict[str, List[Tuple[int, int]]]:
        cluster_count = max(1, min(3, (self.config.width + self.config.height) // 18))
        positions = [(node.x, node.y) for node in nodes]
        self.random.shuffle(positions)
        return {
            "residential": positions[:cluster_count],
            "commercial": positions[cluster_count : cluster_count * 2],
            "work": positions[cluster_count * 2 : cluster_count * 3],
        }

    def _assign_cluster(self, node: Node, clusters: Dict[str, List[Tuple[int, int]]]) -> str:
        best_kind = "residential"
        best_distance = float("inf")
        for kind, centers in clusters.items():
            for center_x, center_y in centers:
                distance = (node.x - center_x) ** 2 + (node.y - center_y) ** 2
                if distance < best_distance:
                    best_distance = distance
                    best_kind = kind
        return best_kind


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
