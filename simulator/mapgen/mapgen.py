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

        clusters = self._build_clusters()
        cluster_radius = max(2, min(self.config.width, self.config.height) // 5)
        base_density = self.config.road_density * 0.35
        dense_density = min(0.95, self.config.road_density + 0.3)
        node_id = 0
        for y in range(self.config.height):
            for x in range(self.config.width):
                density = self._cluster_density(x, y, clusters, cluster_radius, base_density, dense_density)
                if self.random.random() > density:
                    continue
                nodes[node_id] = Node(node_id=node_id, x=x, y=y)
                adjacency[node_id] = []
                node_id += 1

        if not nodes:
            return MapData(nodes=nodes, edges=edges, adjacency=adjacency, pois={})

        node_positions = {(node.x, node.y): node_id for node_id, node in nodes.items()}
        trunk_positions = self._carve_trunk_routes(nodes, adjacency, node_positions, clusters, node_id)
        node_id = max(nodes.keys(), default=-1) + 1

        for node in nodes.values():
            node.district = self._assign_cluster(node, clusters)

        self._build_adjacency(nodes, adjacency, node_positions)
        connected = self._connected_nodes(adjacency, trunk_positions, node_positions)
        if not connected:
            return MapData(nodes={}, edges=[], adjacency={}, pois={})
        nodes = {node_id: node for node_id, node in nodes.items() if node_id in connected}
        adjacency = {
            node_id: [neighbor for neighbor in neighbors if neighbor in connected]
            for node_id, neighbors in adjacency.items()
            if node_id in connected
        }
        node_positions = {(node.x, node.y): node_id for node_id, node in nodes.items()}

        junction_ids = [node_id for node_id, node in nodes.items() if node.kind == "junction"]
        self.random.shuffle(junction_ids)
        roundabout_count = int(len(junction_ids) * self.config.roundabout_ratio)
        for node_id in junction_ids[:roundabout_count]:
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

        intensity = max(0.0, min(self.config.lane_intensity, 1.0))
        single_weight, two_weight = self._lane_weights(intensity)
        highway_radius = 1 + int(intensity * 2)
        trunk_buffer = self._expand_trunk_buffer(trunk_positions, node_positions, highway_radius)
        for node_id, neighbors in adjacency.items():
            node = nodes[node_id]
            for neighbor in neighbors:
                neighbor_node = nodes[neighbor]
                if self._is_highway_edge(node, neighbor_node, trunk_positions, trunk_buffer):
                    road_type = "highway"
                else:
                    road_type = self.random.choices(
                        ["single_lane", "two_lane"],
                        weights=[single_weight, two_weight],
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
        centers = [*residential, *commercial, *work]
        trunk_pairs: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        if len(centers) >= 2:
            ordered = centers[:]
            self.random.shuffle(ordered)
            trunk_pairs.extend(zip(ordered, ordered[1:]))
            extra_connections = int(len(centers) * max(0.0, min(self.config.lane_intensity, 1.0)))
            for _ in range(extra_connections):
                start, end = self.random.sample(centers, 2)
                trunk_pairs.append((start, end))

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
        trunk_positions = self._expand_trunk_network(trunk_positions, node_positions, ensure_node)
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
        major_count = int(len(junction_nodes) * max(0.0, min(self.config.major_junction_ratio, 1.0)))
        major_set = set(junction_nodes[:major_count])
        for node_id, node in nodes.items():
            if node.kind != "junction":
                continue
            node.kind = "major_junction" if node_id in major_set else "minor_junction"

    def _build_clusters(self) -> Dict[str, List[Tuple[int, int]]]:
        largest = max(self.config.width, self.config.height)
        if largest < 16:
            cluster_count = 1
        elif largest < 24:
            cluster_count = 2
        else:
            cluster_count = 3
        total_clusters = cluster_count * 3
        min_distance = max(4, min(self.config.width, self.config.height) // 3)
        centers = self._pick_cluster_centers(total_clusters, min_distance)
        return {
            "residential": centers[:cluster_count],
            "commercial": centers[cluster_count : cluster_count * 2],
            "work": centers[cluster_count * 2 : cluster_count * 3],
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

    def _pick_cluster_centers(self, total_clusters: int, min_distance: int) -> List[Tuple[int, int]]:
        centers: List[Tuple[int, int]] = []
        attempts = 0
        while len(centers) < total_clusters and attempts < total_clusters * 80:
            attempts += 1
            x = self.random.randrange(0, self.config.width)
            y = self.random.randrange(0, self.config.height)
            if all(abs(x - cx) + abs(y - cy) >= min_distance for cx, cy in centers):
                centers.append((x, y))
        while len(centers) < total_clusters:
            centers.append(
                (self.random.randrange(0, self.config.width), self.random.randrange(0, self.config.height))
            )
        return centers

    def _cluster_density(
        self,
        x: int,
        y: int,
        clusters: Dict[str, List[Tuple[int, int]]],
        cluster_radius: int,
        base_density: float,
        dense_density: float,
    ) -> float:
        nearest = float("inf")
        for centers in clusters.values():
            for center_x, center_y in centers:
                distance = abs(x - center_x) + abs(y - center_y)
                if distance < nearest:
                    nearest = distance
        influence = max(0.0, 1.0 - (nearest / max(cluster_radius, 1)))
        return base_density + influence * (dense_density - base_density)

    def _build_adjacency(
        self,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        node_positions: Dict[Tuple[int, int], int],
    ) -> None:
        for node_id, node in nodes.items():
            neighbors = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = node_positions.get((node.x + dx, node.y + dy))
                if neighbor is not None:
                    neighbors.append(neighbor)
            adjacency[node_id] = neighbors

    def _connected_nodes(
        self,
        adjacency: Dict[int, List[int]],
        trunk_positions: set[Tuple[int, int]],
        node_positions: Dict[Tuple[int, int], int],
    ) -> set[int]:
        start_nodes = [node_positions[pos] for pos in trunk_positions if pos in node_positions]
        if not start_nodes and node_positions:
            start_nodes = [next(iter(node_positions.values()))]
        if not start_nodes:
            return set()
        visited: set[int] = set()
        queue = list(start_nodes)
        for node_id in queue:
            visited.add(node_id)
        for current in queue:
            for neighbor in adjacency.get(current, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return visited

    def _lane_weights(self, intensity: float) -> Tuple[float, float]:
        two_lane = 0.25 + 0.5 * intensity
        single_lane = max(0.05, 1.0 - two_lane)
        total = single_lane + two_lane
        return single_lane / total, two_lane / total

    def _expand_trunk_network(
        self,
        trunk_positions: set[Tuple[int, int]],
        node_positions: Dict[Tuple[int, int], int],
        ensure_node,
    ) -> set[Tuple[int, int]]:
        intensity = max(0.0, min(self.config.lane_intensity, 1.0))
        radius = 1 + int(intensity * 2)
        expanded = set(trunk_positions)
        for x, y in list(trunk_positions):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) + abs(dy) > radius:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if 0 <= nx < self.config.width and 0 <= ny < self.config.height:
                        ensure_node(nx, ny)
                        expanded.add((nx, ny))
        return expanded

    def _expand_trunk_buffer(
        self,
        trunk_positions: set[Tuple[int, int]],
        node_positions: Dict[Tuple[int, int], int],
        radius: int,
    ) -> set[Tuple[int, int]]:
        buffer: set[Tuple[int, int]] = set()
        for x, y in trunk_positions:
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) + abs(dy) > radius:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if (nx, ny) in node_positions:
                        buffer.add((nx, ny))
        return buffer

    def _is_highway_edge(
        self,
        node: Node,
        neighbor: Node,
        trunk_positions: set[Tuple[int, int]],
        trunk_buffer: set[Tuple[int, int]],
    ) -> bool:
        if (node.x, node.y) in trunk_positions and (neighbor.x, neighbor.y) in trunk_positions:
            return True
        if node.district != neighbor.district:
            return True
        if (node.x, node.y) in trunk_buffer or (neighbor.x, neighbor.y) in trunk_buffer:
            intensity = max(0.0, min(self.config.lane_intensity, 1.0))
            return self.random.random() < 0.2 + 0.6 * intensity
        return False


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
