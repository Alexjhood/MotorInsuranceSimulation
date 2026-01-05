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
    district: str = "mixed"  # residential, commerce, work, leisure, mixed


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
        self._ensure_district_capacity(
            nodes,
            adjacency,
            node_positions,
            clusters,
            {
                "residential": self.config.residential_count,
                "work": self.config.work_count,
                "commerce": self.config.commerce_count,
                "leisure": self.config.leisure_count,
            },
        )
        available_nodes = [
            nid
            for nid in nodes
            if nodes[nid].kind == "junction" and (nodes[nid].x, nodes[nid].y) not in trunk_positions
        ]
        self.random.shuffle(available_nodes)
        pois: Dict[str, List[int]] = {
            "residence": [],
            "work": [],
            "commerce": [],
            "leisure": [],
            "crossing": [],
            "cyclist": [],
        }
        def _filter_by_district(options: List[int], target: str) -> List[int]:
            return [nid for nid in options if nodes[nid].district == target]

        for kind, count in poi_sets.items():
            for _ in range(count):
                if not available_nodes:
                    break
                if kind == "residence":
                    candidates = _filter_by_district(available_nodes, "residential")
                elif kind == "commerce":
                    candidates = _filter_by_district(available_nodes, "commerce")
                elif kind == "leisure":
                    candidates = _filter_by_district(available_nodes, "leisure")
                elif kind in {"crossing", "cyclist"}:
                    candidates = _filter_by_district(available_nodes, "commerce")
                elif kind == "work":
                    candidates = _filter_by_district(available_nodes, "work")
                else:
                    candidates = available_nodes
                node_id = self.random.choice(candidates) if candidates else available_nodes[0]
                nodes[node_id].kind = kind
                pois[kind].append(node_id)
                available_nodes.remove(node_id)

        intensity = max(0.0, min(self.config.lane_intensity, 1.0))
        single_weight, two_weight = self._lane_weights(intensity)
        for node_id, neighbors in adjacency.items():
            node = nodes[node_id]
            for neighbor in neighbors:
                neighbor_node = nodes[neighbor]
                if self._is_highway_edge(node, neighbor_node, trunk_positions, clusters, cluster_radius):
                    road_type = "highway"
                else:
                    local_single, local_two = self._local_lane_weights(
                        node.district,
                        neighbor_node.district,
                        intensity,
                        single_weight,
                        two_weight,
                    )
                    road_type = self.random.choices(
                        ["single_lane", "two_lane"],
                        weights=[local_single, local_two],
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
        commercial = clusters.get("commerce", [])
        work = clusters.get("work", [])
        leisure = clusters.get("leisure", [])
        centers = [*residential, *commercial, *work, *leisure]
        trunk_pairs: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        if len(centers) >= 2:
            ordered = centers[:]
            self.random.shuffle(ordered)
            trunk_pairs.extend(zip(ordered, ordered[1:]))
            extra_connections = max(1, int(len(centers) * 0.4))
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
        cluster_counts = {
            "residential": self._clamp_cluster_count(self.config.residential_cluster_count),
            "work": self._clamp_cluster_count(self.config.work_cluster_count),
            "commerce": self._clamp_cluster_count(self.config.commerce_cluster_count),
            "leisure": self._clamp_cluster_count(self.config.leisure_cluster_count),
        }
        total_clusters = sum(cluster_counts.values())
        min_distance = max(4, min(self.config.width, self.config.height) // 3)
        centers = self._pick_cluster_centers(total_clusters, min_distance)
        cluster_map: Dict[str, List[Tuple[int, int]]] = {}
        index = 0
        for kind, count in cluster_counts.items():
            cluster_map[kind] = centers[index : index + count]
            index += count
        return cluster_map

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

    def _clamp_cluster_count(self, count: int) -> int:
        return max(1, min(count, self.config.width * self.config.height))

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

    def _local_lane_weights(
        self,
        district_a: str,
        district_b: str,
        intensity: float,
        base_single: float,
        base_two: float,
    ) -> Tuple[float, float]:
        single = base_single
        two = base_two
        if district_a == district_b == "residential":
            single *= 1.4
            two *= 0.6
        elif district_a == district_b and district_a in {"work", "commerce", "leisure"}:
            single *= 0.6
            two *= 1.4
        elif district_a != district_b:
            single *= 0.9
            two *= 1.1
        if intensity > 0.7:
            two *= 1.1
        total = single + two
        return single / total, two / total

    def _is_highway_edge(
        self,
        node: Node,
        neighbor: Node,
        trunk_positions: set[Tuple[int, int]],
        clusters: Dict[str, List[Tuple[int, int]]],
        cluster_radius: int,
    ) -> bool:
        if (node.x, node.y) not in trunk_positions or (neighbor.x, neighbor.y) not in trunk_positions:
            return False
        allowed_kinds = {"junction", "roundabout", "major_junction", "minor_junction"}
        if node.kind not in allowed_kinds or neighbor.kind not in allowed_kinds:
            return False
        if self._in_cluster_core(node, clusters, cluster_radius) or self._in_cluster_core(
            neighbor, clusters, cluster_radius
        ):
            return False
        return True

    def _in_cluster_core(
        self,
        node: Node,
        clusters: Dict[str, List[Tuple[int, int]]],
        cluster_radius: int,
    ) -> bool:
        centers = clusters.get(node.district, [])
        if not centers:
            return False
        closest = min(abs(node.x - cx) + abs(node.y - cy) for cx, cy in centers)
        return closest <= cluster_radius

    def _ensure_district_capacity(
        self,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        node_positions: Dict[Tuple[int, int], int],
        clusters: Dict[str, List[Tuple[int, int]]],
        required_by_district: Dict[str, int],
    ) -> None:
        for district, required in required_by_district.items():
            current = sum(
                1
                for node in nodes.values()
                if node.kind == "junction" and node.district == district
            )
            deficit = max(0, required - current)
            for _ in range(deficit):
                position = self._pick_adjacent_position(clusters.get(district, []), node_positions)
                if position is None:
                    break
                node_id = max(nodes.keys(), default=-1) + 1
                nodes[node_id] = Node(node_id=node_id, x=position[0], y=position[1], district=district)
                adjacency[node_id] = []
                node_positions[position] = node_id
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    neighbor_pos = (position[0] + dx, position[1] + dy)
                    neighbor_id = node_positions.get(neighbor_pos)
                    if neighbor_id is not None:
                        adjacency[node_id].append(neighbor_id)
                        adjacency.setdefault(neighbor_id, []).append(node_id)

    def _pick_adjacent_position(
        self,
        centers: List[Tuple[int, int]],
        node_positions: Dict[Tuple[int, int], int],
    ) -> Tuple[int, int] | None:
        adjacent_positions = set()
        for x, y in node_positions:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx = x + dx
                ny = y + dy
                if 0 <= nx < self.config.width and 0 <= ny < self.config.height:
                    if (nx, ny) not in node_positions:
                        adjacent_positions.add((nx, ny))
        if not adjacent_positions:
            return None
        if not centers:
            return self.random.choice(list(adjacent_positions))
        def _distance(candidate: Tuple[int, int]) -> int:
            cx, cy = min(centers, key=lambda center: abs(candidate[0] - center[0]) + abs(candidate[1] - center[1]))
            return abs(candidate[0] - cx) + abs(candidate[1] - cy)
        return min(adjacent_positions, key=_distance)


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
