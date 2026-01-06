from __future__ import annotations

import math
from typing import Dict, List, Set, Tuple

from simulator.mapgen.context import MapContext
from simulator.mapgen.data import Cluster, Edge, Node


def build_cluster_road_network(
    ctx: MapContext,
    cluster: Cluster,
    nodes: Dict[int, Node],
    adjacency: Dict[int, List[int]],
    edges: List[Edge],
) -> None:
    """Build realistic road network within a cluster."""
    if len(cluster.node_ids) < 2:
        return

    cluster_nodes = [nodes[nid] for nid in cluster.node_ids]

    mst_edges = minimum_spanning_tree(ctx, cluster_nodes)
    extra_edges = add_extra_connections(ctx, cluster_nodes, mst_edges)
    all_connections = mst_edges + extra_edges

    for n1, n2 in all_connections:
        if n2.node_id in adjacency[n1.node_id]:
            continue

        is_dual = ctx.rng.random() < ctx.config.intra_cluster_dual_road_chance
        road_type = "dual_carriageway" if is_dual else "single_lane"

        dist = ctx.distance(n1, n2)
        if dist > ctx.config.cluster_radius * 0.5 and ctx.rng.random() < ctx.config.intra_cluster_roundabout_chance:
            mid_x = (n1.x + n2.x) / 2
            mid_y = (n1.y + n2.y) / 2
            roundabout_id = ctx.next_node_id()
            roundabout = Node(
                node_id=roundabout_id,
                x=mid_x,
                y=mid_y,
                kind="roundabout",
                district=cluster.cluster_type,
                cluster_id=cluster.cluster_id,
            )
            nodes[roundabout_id] = roundabout
            adjacency[roundabout_id] = []
            cluster.node_ids.append(roundabout_id)

            add_road(ctx, n1.node_id, roundabout_id, road_type, adjacency, edges, nodes)
            add_road(ctx, roundabout_id, n2.node_id, road_type, adjacency, edges, nodes)
        else:
            add_road(ctx, n1.node_id, n2.node_id, road_type, adjacency, edges, nodes)


def minimum_spanning_tree(ctx: MapContext, cluster_nodes: List[Node]) -> List[Tuple[Node, Node]]:
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
                dist = ctx.distance(node, other)
                if dist < best_dist:
                    best_dist = dist
                    best_edge = (node, other)

        if best_edge:
            mst_edges.append(best_edge)
            in_tree.add(best_edge[1].node_id)

    return mst_edges


def add_extra_connections(
    ctx: MapContext,
    cluster_nodes: List[Node],
    mst_edges: List[Tuple[Node, Node]],
) -> List[Tuple[Node, Node]]:
    """Add some extra edges beyond MST for more realistic road network."""
    extra: List[Tuple[Node, Node]] = []
    mst_set = {(e[0].node_id, e[1].node_id) for e in mst_edges}
    mst_set.update((e[1].node_id, e[0].node_id) for e in mst_edges)

    target_extra = max(1, int(len(mst_edges) * 0.3))

    candidates: List[Tuple[Node, Node, float]] = []
    for i, n1 in enumerate(cluster_nodes):
        for n2 in cluster_nodes[i + 1 :]:
            if (n1.node_id, n2.node_id) not in mst_set:
                candidates.append((n1, n2, ctx.distance(n1, n2)))

    candidates.sort(key=lambda x: x[2])
    for n1, n2, _ in candidates[:target_extra]:
        extra.append((n1, n2))

    return extra


def add_road(
    ctx: MapContext,
    start_id: int,
    end_id: int,
    road_type: str,
    adjacency: Dict[int, List[int]],
    edges: List[Edge],
    nodes: Dict[int, Node],
    is_highway: bool = False,
) -> None:
    """Add a bidirectional road between two nodes."""
    if end_id not in adjacency[start_id]:
        adjacency[start_id].append(end_id)
    if start_id not in adjacency[end_id]:
        adjacency[end_id].append(start_id)

    speed_limit = ctx.config.speed_limits_by_type.get(road_type, 30)
    lanes = ctx.config.lanes_by_type.get(road_type, 1)

    start_node = nodes[start_id]
    end_node = nodes[end_id]
    has_crossing = start_node.kind == "crossing" or end_node.kind == "crossing"
    has_cycle_lane = ctx.rng.random() < ctx.config.cycle_lane_chance

    for s, e in [(start_id, end_id), (end_id, start_id)]:
        edges.append(
            Edge(
                start=s,
                end=e,
                speed_limit=speed_limit,
                risk_factor=ctx.rng.uniform(0.8, 1.4),
                road_type=road_type,
                lanes=lanes,
                has_cycle_lane=has_cycle_lane,
                has_crossing=has_crossing,
                is_highway=is_highway,
            )
        )


def build_highway_network(
    ctx: MapContext,
    clusters: List[Cluster],
    nodes: Dict[int, Node],
    adjacency: Dict[int, List[int]],
    edges: List[Edge],
) -> Set[int]:
    """Build highway network connecting clusters."""
    highway_node_ids: Set[int] = set()

    if len(clusters) < 2:
        return highway_node_ids

    cluster_mst = cluster_mst_graph(clusters)
    extra_highways = extra_highway_connections(clusters, cluster_mst)
    all_highway_pairs = cluster_mst + extra_highways

    highway_junctions: Dict[Tuple[float, float], List[int]] = {}

    for c1, c2 in all_highway_pairs:
        new_highway_nodes = create_highway_route(ctx, c1, c2, nodes, adjacency, edges, highway_junctions)
        highway_node_ids.update(new_highway_nodes)

    add_highway_roundabouts(ctx, highway_junctions, nodes, adjacency, edges)

    return highway_node_ids


def cluster_mst_graph(clusters: List[Cluster]) -> List[Tuple[Cluster, Cluster]]:
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
                dist = math.sqrt((c1.center_x - c2.center_x) ** 2 + (c1.center_y - c2.center_y) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    best_edge = (c1, c2)

        if best_edge:
            mst_edges.append(best_edge)
            in_tree.add(best_edge[1].cluster_id)

    return mst_edges


def extra_highway_connections(
    clusters: List[Cluster],
    mst: List[Tuple[Cluster, Cluster]],
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
        for c2 in clusters[i + 1 :]:
            if (c1.cluster_id, c2.cluster_id) not in mst_set:
                dist = math.sqrt((c1.center_x - c2.center_x) ** 2 + (c1.center_y - c2.center_y) ** 2)
                candidates.append((c1, c2, dist))

    candidates.sort(key=lambda x: x[2])
    for c1, c2, _ in candidates[:target]:
        extra.append((c1, c2))

    return extra


def create_highway_route(
    ctx: MapContext,
    c1: Cluster,
    c2: Cluster,
    nodes: Dict[int, Node],
    adjacency: Dict[int, List[int]],
    edges: List[Edge],
    highway_junctions: Dict[Tuple[float, float], List[int]],
) -> List[int]:
    """Create highway route between two clusters with intermediate nodes."""
    new_node_ids: List[int] = []

    start_id = c1.entry_node_id
    end_id = c2.entry_node_id

    if start_id is None or end_id is None:
        return new_node_ids

    start_node = nodes[start_id]
    end_node = nodes[end_id]

    dist = math.sqrt((end_node.x - start_node.x) ** 2 + (end_node.y - start_node.y) ** 2)

    segment_length = 20.0
    num_segments = max(1, int(dist / segment_length))

    prev_id = start_id
    for i in range(1, num_segments):
        t = i / num_segments
        x = start_node.x + t * (end_node.x - start_node.x)
        y = start_node.y + t * (end_node.y - start_node.y)

        junction_key = (round(x / 10) * 10, round(y / 10) * 10)

        node_id = ctx.next_node_id()
        node = Node(
            node_id=node_id,
            x=x,
            y=y,
            kind="highway_junction",
            district="mixed",
            cluster_id=-1,
        )
        nodes[node_id] = node
        adjacency[node_id] = []
        new_node_ids.append(node_id)

        if junction_key not in highway_junctions:
            highway_junctions[junction_key] = []
        highway_junctions[junction_key].append(node_id)

        add_road(ctx, prev_id, node_id, "highway", adjacency, edges, nodes, is_highway=True)
        prev_id = node_id

    add_road(ctx, prev_id, end_id, "highway", adjacency, edges, nodes, is_highway=True)

    return new_node_ids


def add_highway_roundabouts(
    ctx: MapContext,
    highway_junctions: Dict[Tuple[float, float], List[int]],
    nodes: Dict[int, Node],
    adjacency: Dict[int, List[int]],
    edges: List[Edge],
) -> None:
    """Add roundabouts where highways merge."""
    for _, node_ids in highway_junctions.items():
        if len(node_ids) >= 2 and ctx.rng.random() < ctx.config.highway_merge_roundabout_chance:
            avg_x = sum(nodes[nid].x for nid in node_ids) / len(node_ids)
            avg_y = sum(nodes[nid].y for nid in node_ids) / len(node_ids)

            roundabout_id = ctx.next_node_id()
            roundabout = Node(
                node_id=roundabout_id,
                x=avg_x,
                y=avg_y,
                kind="roundabout",
                district="mixed",
                cluster_id=-1,
            )
            nodes[roundabout_id] = roundabout
            adjacency[roundabout_id] = []

            for nid in node_ids:
                add_road(ctx, nid, roundabout_id, "highway", adjacency, edges, nodes, is_highway=True)
