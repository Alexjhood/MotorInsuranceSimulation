from __future__ import annotations

import math
from dataclasses import dataclass, field
import random
from typing import Dict, List, Optional, Set, Tuple

from simulator.config import MapConfig


@dataclass
class Node:
    node_id: int
    x: float
    y: float
    kind: str = "junction"  # junction, major_junction, minor_junction, roundabout, residence, work, commerce, leisure, crossing, cyclist, highway_junction
    district: str = "mixed"  # residential, commerce, work, leisure, mixed
    cluster_id: int = -1  # Which cluster this node belongs to (-1 for highway nodes)


@dataclass
class Edge:
    start: int
    end: int
    speed_limit: int
    risk_factor: float
    road_type: str  # single_lane, dual_carriageway, highway
    lanes: int
    has_cycle_lane: bool
    has_crossing: bool
    is_highway: bool = False


@dataclass
class MapData:
    nodes: Dict[int, Node]
    edges: List[Edge]
    adjacency: Dict[int, List[int]]
    pois: Dict[str, List[int]] = field(default_factory=dict)
    clusters: List["Cluster"] = field(default_factory=list)


@dataclass
class Cluster:
    cluster_id: int
    center_x: float
    center_y: float
    cluster_type: str  # residential, work, commerce, leisure
    node_ids: List[int] = field(default_factory=list)
    entry_node_id: Optional[int] = None  # Node where highways connect


class MapGenerator:
    def __init__(self, config: MapConfig, seed: int) -> None:
        self.config = config
        self.random = random.Random(seed)
        self.node_id_counter = 0

    def generate(self) -> MapData:
        nodes: Dict[int, Node] = {}
        adjacency: Dict[int, List[int]] = {}
        edges: List[Edge] = []

        # Step 1: Generate clusters using Poisson process
        clusters = self._generate_clusters()
        
        if not clusters:
            # Fallback: create at least one cluster
            clusters = [Cluster(
                cluster_id=0,
                center_x=self.config.map_scale / 2,
                center_y=self.config.map_scale / 2,
                cluster_type="residential"
            )]

        # Step 2: Generate locations within each cluster using Poisson process
        for cluster in clusters:
            self._populate_cluster(cluster, nodes, adjacency)

        # Step 3: Build intra-cluster road networks
        for cluster in clusters:
            self._build_cluster_road_network(cluster, nodes, adjacency, edges)

        # Step 4: Build highway network connecting clusters
        highway_nodes = self._build_highway_network(clusters, nodes, adjacency, edges)

        # Step 5: Assign POIs and special node types
        pois = self._assign_pois(nodes, clusters)

        # Step 6: Assign junction types
        self._assign_junction_types(nodes, adjacency, highway_nodes)

        return MapData(
            nodes=nodes,
            edges=edges,
            adjacency=adjacency,
            pois=pois,
            clusters=clusters
        )

    def _generate_clusters(self) -> List[Cluster]:
        """Generate clusters using Poisson process with minimum of 1."""
        # Sample number of clusters from Poisson, minimum 1
        num_clusters = max(1, self._poisson(self.config.cluster_lambda))
        
        clusters: List[Cluster] = []
        cluster_types = list(self.config.cluster_type_weights.keys())
        cluster_weights = list(self.config.cluster_type_weights.values())
        
        for i in range(num_clusters):
            # Pick cluster center with spacing constraints
            center = self._pick_cluster_center(clusters)
            cluster_type = self.random.choices(cluster_types, weights=cluster_weights, k=1)[0]
            
            clusters.append(Cluster(
                cluster_id=i,
                center_x=center[0],
                center_y=center[1],
                cluster_type=cluster_type
            ))
        
        return clusters

    def _poisson(self, lam: float) -> int:
        """Sample from Poisson distribution using inverse transform."""
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= self.random.random()
        return k - 1

    def _pick_cluster_center(self, existing_clusters: List[Cluster]) -> Tuple[float, float]:
        """Pick a cluster center respecting minimum spacing."""
        max_attempts = 100
        
        for _ in range(max_attempts):
            x = self.random.uniform(self.config.cluster_radius, 
                                   self.config.map_scale - self.config.cluster_radius)
            y = self.random.uniform(self.config.cluster_radius, 
                                   self.config.map_scale - self.config.cluster_radius)
            
            # Check spacing from existing clusters
            valid = True
            for cluster in existing_clusters:
                dist = math.sqrt((x - cluster.center_x) ** 2 + (y - cluster.center_y) ** 2)
                if dist < self.config.min_cluster_spacing:
                    valid = False
                    break
            
            if valid:
                return (x, y)
        
        # Fallback: expand map or place anyway
        return (
            self.random.uniform(0, self.config.map_scale),
            self.random.uniform(0, self.config.map_scale)
        )

    def _populate_cluster(
        self,
        cluster: Cluster,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]]
    ) -> None:
        """Generate locations within a cluster using separate Poisson processes for homes and other locations."""
        # Sample number of homes from Poisson (minimum 1)
        num_homes = max(1, self._poisson(self.config.homes_per_cluster_lambda))
        
        # Sample number of other locations from Poisson (minimum 0)
        num_other_locations = max(0, self._poisson(self.config.other_locations_per_cluster_lambda))
        
        # Generate homes
        for _ in range(num_homes):
            node = self._create_location_node(cluster, "residence")
            nodes[node.node_id] = node
            adjacency[node.node_id] = []
            cluster.node_ids.append(node.node_id)
        
        # Generate other locations
        for _ in range(num_other_locations):
            node = self._create_location_node(cluster, "junction")
            nodes[node.node_id] = node
            adjacency[node.node_id] = []
            cluster.node_ids.append(node.node_id)
        
        # Designate entry point (closest to center or create one)
        if cluster.node_ids:
            cluster.entry_node_id = min(
                cluster.node_ids,
                key=lambda nid: self._distance_to_point(
                    nodes[nid], cluster.center_x, cluster.center_y
                )
            )

    def _create_location_node(self, cluster: Cluster, kind: str) -> int:
        """Create a location node within cluster radius."""
        # Place location within cluster radius using polar coordinates
        angle = self.random.uniform(0, 2 * math.pi)
        radius = self.random.uniform(0, self.config.cluster_radius) * math.sqrt(self.random.random())
        
        x = cluster.center_x + radius * math.cos(angle)
        y = cluster.center_y + radius * math.sin(angle)
        
        node_id = self._next_node_id()
        return Node(
            node_id=node_id,
            x=x,
            y=y,
            kind=kind,
            district=cluster.cluster_type,
            cluster_id=cluster.cluster_id
        )

    def _next_node_id(self) -> int:
        nid = self.node_id_counter
        self.node_id_counter += 1
        return nid

    def _distance(self, n1: Node, n2: Node) -> float:
        return math.sqrt((n1.x - n2.x) ** 2 + (n1.y - n2.y) ** 2)

    def _distance_to_point(self, node: Node, x: float, y: float) -> float:
        return math.sqrt((node.x - x) ** 2 + (node.y - y) ** 2)

    def _build_cluster_road_network(
        self,
        cluster: Cluster,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        edges: List[Edge]
    ) -> None:
        """Build realistic road network within a cluster."""
        if len(cluster.node_ids) < 2:
            return
        
        cluster_nodes = [nodes[nid] for nid in cluster.node_ids]
        
        # Build minimum spanning tree first for connectivity
        mst_edges = self._minimum_spanning_tree(cluster_nodes)
        
        # Add some additional edges for realism (not just a tree)
        extra_edges = self._add_extra_connections(cluster_nodes, mst_edges)
        
        all_connections = mst_edges + extra_edges
        
        # Create road segments with appropriate types
        for n1, n2 in all_connections:
            if n2.node_id in adjacency[n1.node_id]:
                continue  # Already connected
            
            # Decide road type
            is_dual = self.random.random() < self.config.intra_cluster_dual_road_chance
            road_type = "dual_carriageway" if is_dual else "single_lane"
            
            # Maybe add intermediate junction/roundabout for longer roads
            dist = self._distance(n1, n2)
            if dist > self.config.cluster_radius * 0.5 and self.random.random() < self.config.intra_cluster_roundabout_chance:
                # Add roundabout in the middle
                mid_x = (n1.x + n2.x) / 2
                mid_y = (n1.y + n2.y) / 2
                roundabout_id = self._next_node_id()
                roundabout = Node(
                    node_id=roundabout_id,
                    x=mid_x,
                    y=mid_y,
                    kind="roundabout",
                    district=cluster.cluster_type,
                    cluster_id=cluster.cluster_id
                )
                nodes[roundabout_id] = roundabout
                adjacency[roundabout_id] = []
                cluster.node_ids.append(roundabout_id)
                
                # Connect n1 -> roundabout -> n2
                self._add_road(n1.node_id, roundabout_id, road_type, adjacency, edges, nodes)
                self._add_road(roundabout_id, n2.node_id, road_type, adjacency, edges, nodes)
            else:
                self._add_road(n1.node_id, n2.node_id, road_type, adjacency, edges, nodes)

    def _minimum_spanning_tree(self, cluster_nodes: List[Node]) -> List[Tuple[Node, Node]]:
        """Build MST using Prim's algorithm."""
        if len(cluster_nodes) < 2:
            return []
        
        in_tree: Set[int] = {cluster_nodes[0].node_id}
        mst_edges: List[Tuple[Node, Node]] = []
        
        while len(in_tree) < len(cluster_nodes):
            best_edge = None
            best_dist = float("inf")
            
            for node in cluster_nodes:
                if node.node_id not in in_tree:
                    continue
                for other in cluster_nodes:
                    if other.node_id in in_tree:
                        continue
                    dist = self._distance(node, other)
                    if dist < best_dist:
                        best_dist = dist
                        best_edge = (node, other)
            
            if best_edge:
                mst_edges.append(best_edge)
                in_tree.add(best_edge[1].node_id)
        
        return mst_edges

    def _add_extra_connections(
        self,
        cluster_nodes: List[Node],
        mst_edges: List[Tuple[Node, Node]]
    ) -> List[Tuple[Node, Node]]:
        """Add some extra edges beyond MST for more realistic road network."""
        extra: List[Tuple[Node, Node]] = []
        mst_set = {(e[0].node_id, e[1].node_id) for e in mst_edges}
        mst_set.update((e[1].node_id, e[0].node_id) for e in mst_edges)
        
        # Add ~30% more edges
        target_extra = max(1, int(len(mst_edges) * 0.3))
        
        candidates: List[Tuple[Node, Node, float]] = []
        for i, n1 in enumerate(cluster_nodes):
            for n2 in cluster_nodes[i+1:]:
                if (n1.node_id, n2.node_id) not in mst_set:
                    candidates.append((n1, n2, self._distance(n1, n2)))
        
        # Sort by distance and pick shortest extras
        candidates.sort(key=lambda x: x[2])
        for n1, n2, _ in candidates[:target_extra]:
            extra.append((n1, n2))
        
        return extra

    def _add_road(
        self,
        start_id: int,
        end_id: int,
        road_type: str,
        adjacency: Dict[int, List[int]],
        edges: List[Edge],
        nodes: Dict[int, Node],
        is_highway: bool = False
    ) -> None:
        """Add a bidirectional road between two nodes."""
        if end_id not in adjacency[start_id]:
            adjacency[start_id].append(end_id)
        if start_id not in adjacency[end_id]:
            adjacency[end_id].append(start_id)
        
        speed_limit = self.config.speed_limits_by_type.get(road_type, 30)
        lanes = self.config.lanes_by_type.get(road_type, 1)
        
        start_node = nodes[start_id]
        end_node = nodes[end_id]
        has_crossing = start_node.kind == "crossing" or end_node.kind == "crossing"
        has_cycle_lane = self.random.random() < self.config.cycle_lane_chance
        
        # Add edge in both directions
        for s, e in [(start_id, end_id), (end_id, start_id)]:
            edges.append(Edge(
                start=s,
                end=e,
                speed_limit=speed_limit,
                risk_factor=self.random.uniform(0.8, 1.4),
                road_type=road_type,
                lanes=lanes,
                has_cycle_lane=has_cycle_lane,
                has_crossing=has_crossing,
                is_highway=is_highway
            ))

    def _build_highway_network(
        self,
        clusters: List[Cluster],
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        edges: List[Edge]
    ) -> Set[int]:
        """Build highway network connecting clusters."""
        highway_node_ids: Set[int] = set()
        
        if len(clusters) < 2:
            return highway_node_ids
        
        # Build MST of cluster centers for primary highway network
        cluster_mst = self._cluster_mst(clusters)
        
        # Add some extra highway connections for redundancy
        extra_highways = self._extra_highway_connections(clusters, cluster_mst)
        
        all_highway_pairs = cluster_mst + extra_highways
        
        # Track where highways meet for potential roundabouts
        highway_junctions: Dict[Tuple[float, float], List[int]] = {}
        
        for c1, c2 in all_highway_pairs:
            # Create highway route between cluster entry points
            new_highway_nodes = self._create_highway_route(
                c1, c2, nodes, adjacency, edges, highway_junctions
            )
            highway_node_ids.update(new_highway_nodes)
        
        # Add roundabouts at highway merge points
        self._add_highway_roundabouts(highway_junctions, nodes, adjacency, edges)
        
        return highway_node_ids

    def _cluster_mst(self, clusters: List[Cluster]) -> List[Tuple[Cluster, Cluster]]:
        """Build MST connecting cluster centers."""
        if len(clusters) < 2:
            return []
        
        in_tree: Set[int] = {clusters[0].cluster_id}
        mst_edges: List[Tuple[Cluster, Cluster]] = []
        
        while len(in_tree) < len(clusters):
            best_edge = None
            best_dist = float("inf")
            
            for c1 in clusters:
                if c1.cluster_id not in in_tree:
                    continue
                for c2 in clusters:
                    if c2.cluster_id in in_tree:
                        continue
                    dist = math.sqrt(
                        (c1.center_x - c2.center_x) ** 2 + 
                        (c1.center_y - c2.center_y) ** 2
                    )
                    if dist < best_dist:
                        best_dist = dist
                        best_edge = (c1, c2)
            
            if best_edge:
                mst_edges.append(best_edge)
                in_tree.add(best_edge[1].cluster_id)
        
        return mst_edges

    def _extra_highway_connections(
        self,
        clusters: List[Cluster],
        mst: List[Tuple[Cluster, Cluster]]
    ) -> List[Tuple[Cluster, Cluster]]:
        """Add extra highway connections beyond MST."""
        if len(clusters) < 3:
            return []
        
        mst_set = {(c1.cluster_id, c2.cluster_id) for c1, c2 in mst}
        mst_set.update((c2.cluster_id, c1.cluster_id) for c1, c2 in mst)
        
        extra: List[Tuple[Cluster, Cluster]] = []
        target = max(1, len(clusters) // 3)
        
        candidates: List[Tuple[Cluster, Cluster, float]] = []
        for i, c1 in enumerate(clusters):
            for c2 in clusters[i+1:]:
                if (c1.cluster_id, c2.cluster_id) not in mst_set:
                    dist = math.sqrt(
                        (c1.center_x - c2.center_x) ** 2 + 
                        (c1.center_y - c2.center_y) ** 2
                    )
                    candidates.append((c1, c2, dist))
        
        candidates.sort(key=lambda x: x[2])
        for c1, c2, _ in candidates[:target]:
            extra.append((c1, c2))
        
        return extra

    def _create_highway_route(
        self,
        c1: Cluster,
        c2: Cluster,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        edges: List[Edge],
        highway_junctions: Dict[Tuple[float, float], List[int]]
    ) -> List[int]:
        """Create highway route between two clusters with intermediate nodes."""
        new_node_ids: List[int] = []
        
        # Get entry points
        start_id = c1.entry_node_id
        end_id = c2.entry_node_id
        
        if start_id is None or end_id is None:
            return new_node_ids
        
        start_node = nodes[start_id]
        end_node = nodes[end_id]
        
        # Calculate distance and number of intermediate nodes
        dist = math.sqrt(
            (end_node.x - start_node.x) ** 2 + 
            (end_node.y - start_node.y) ** 2
        )
        
        # Add intermediate highway nodes every ~20 units
        segment_length = 20.0
        num_segments = max(1, int(dist / segment_length))
        
        prev_id = start_id
        for i in range(1, num_segments):
            t = i / num_segments
            x = start_node.x + t * (end_node.x - start_node.x)
            y = start_node.y + t * (end_node.y - start_node.y)
            
            # Check if near an existing highway junction
            junction_key = (round(x / 10) * 10, round(y / 10) * 10)
            
            node_id = self._next_node_id()
            node = Node(
                node_id=node_id,
                x=x,
                y=y,
                kind="highway_junction",
                district="mixed",
                cluster_id=-1
            )
            nodes[node_id] = node
            adjacency[node_id] = []
            new_node_ids.append(node_id)
            
            # Track for potential roundabout placement
            if junction_key not in highway_junctions:
                highway_junctions[junction_key] = []
            highway_junctions[junction_key].append(node_id)
            
            # Connect to previous
            self._add_road(prev_id, node_id, "highway", adjacency, edges, nodes, is_highway=True)
            prev_id = node_id
        
        # Connect last segment to end
        self._add_road(prev_id, end_id, "highway", adjacency, edges, nodes, is_highway=True)
        
        return new_node_ids

    def _add_highway_roundabouts(
        self,
        highway_junctions: Dict[Tuple[float, float], List[int]],
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        edges: List[Edge]
    ) -> None:
        """Add roundabouts where highways merge."""
        for junction_key, node_ids in highway_junctions.items():
            if len(node_ids) >= 2 and self.random.random() < self.config.highway_merge_roundabout_chance:
                # Create a roundabout connecting these highway nodes
                avg_x = sum(nodes[nid].x for nid in node_ids) / len(node_ids)
                avg_y = sum(nodes[nid].y for nid in node_ids) / len(node_ids)
                
                roundabout_id = self._next_node_id()
                roundabout = Node(
                    node_id=roundabout_id,
                    x=avg_x,
                    y=avg_y,
                    kind="roundabout",
                    district="mixed",
                    cluster_id=-1
                )
                nodes[roundabout_id] = roundabout
                adjacency[roundabout_id] = []
                
                # Connect all nearby highway nodes to the roundabout
                for nid in node_ids:
                    self._add_road(nid, roundabout_id, "highway", adjacency, edges, nodes, is_highway=True)

    def _assign_pois(
        self,
        nodes: Dict[int, Node],
        clusters: List[Cluster]
    ) -> Dict[str, List[int]]:
        """Assign POI types to nodes based on cluster types."""
        pois: Dict[str, List[int]] = {
            "residence": [],
            "work": [],
            "commerce": [],
            "leisure": [],
            "crossing": [],
            "cyclist": [],
        }
        
        # First, add all nodes that already have POI types (e.g., residences created in _populate_cluster)
        for nid, node in nodes.items():
            if node.kind in pois:
                pois[node.kind].append(nid)
        
        # Map cluster types to POI types
        cluster_to_poi = {
            "residential": "residence",
            "work": "work",
            "commerce": "commerce",
            "leisure": "leisure"
        }
        
        for cluster in clusters:
            poi_type = cluster_to_poi.get(cluster.cluster_type, "residence")
            available = [
                nid for nid in cluster.node_ids 
                if nodes[nid].kind == "junction"
            ]
            
            # Assign main POI type to some nodes
            num_pois = max(1, len(available) // 2)
            self.random.shuffle(available)
            
            for nid in available[:num_pois]:
                nodes[nid].kind = poi_type
                pois[poi_type].append(nid)
        
        # Ensure minimums are met
        self._ensure_minimum_pois(nodes, pois, "residence", self.config.min_residences)
        self._ensure_minimum_pois(nodes, pois, "work", self.config.min_workplaces)
        self._ensure_minimum_pois(nodes, pois, "commerce", self.config.min_commerce)
        self._ensure_minimum_pois(nodes, pois, "leisure", self.config.min_leisure)
        
        # Add crossings and cyclist hubs
        junction_nodes = [nid for nid, n in nodes.items() if n.kind in {"junction", "minor_junction"}]
        
        crossing_count = max(1, int(len(junction_nodes) * self.config.pedestrian_crossing_ratio))
        cyclist_count = max(1, int(len(junction_nodes) * self.config.cyclist_hub_ratio))
        
        self.random.shuffle(junction_nodes)
        for nid in junction_nodes[:crossing_count]:
            nodes[nid].kind = "crossing"
            pois["crossing"].append(nid)
        
        remaining = [nid for nid in junction_nodes if nodes[nid].kind != "crossing"]
        for nid in remaining[:cyclist_count]:
            nodes[nid].kind = "cyclist"
            pois["cyclist"].append(nid)
        
        return pois

    def _ensure_minimum_pois(
        self,
        nodes: Dict[int, Node],
        pois: Dict[str, List[int]],
        poi_type: str,
        minimum: int
    ) -> None:
        """Ensure minimum number of POIs of a given type."""
        current = len(pois[poi_type])
        if current >= minimum:
            return
        
        available = [
            nid for nid, n in nodes.items()
            if n.kind == "junction"
        ]
        self.random.shuffle(available)
        
        needed = minimum - current
        for nid in available[:needed]:
            nodes[nid].kind = poi_type
            pois[poi_type].append(nid)

    def _assign_junction_types(
        self,
        nodes: Dict[int, Node],
        adjacency: Dict[int, List[int]],
        highway_nodes: Set[int]
    ) -> None:
        """Assign major/minor junction types based on connectivity."""
        junction_nodes = [
            nid for nid, node in nodes.items()
            if node.kind == "junction"
        ]
        
        # Sort by number of connections
        junction_nodes.sort(key=lambda nid: len(adjacency.get(nid, [])), reverse=True)
        
        major_count = int(len(junction_nodes) * self.config.major_junction_ratio)
        major_set = set(junction_nodes[:major_count])
        
        for nid in junction_nodes:
            if nid in highway_nodes:
                nodes[nid].kind = "major_junction"
            elif nid in major_set:
                nodes[nid].kind = "major_junction"
            else:
                nodes[nid].kind = "minor_junction"


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
