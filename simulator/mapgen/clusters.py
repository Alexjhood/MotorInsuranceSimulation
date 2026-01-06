from __future__ import annotations

import math
from typing import Dict, List, Tuple

from simulator.mapgen.context import MapContext
from simulator.mapgen.data import Cluster, Node


def generate_clusters(ctx: MapContext) -> List[Cluster]:
    """Generate clusters using Poisson process with minimum of 1."""
    num_clusters = max(1, poisson(ctx, ctx.config.cluster_lambda))

    clusters: List[Cluster] = []
    cluster_types = list(ctx.config.cluster_type_weights.keys())
    cluster_weights = list(ctx.config.cluster_type_weights.values())

    for i in range(num_clusters):
        center = pick_cluster_center(ctx, clusters)
        cluster_type = ctx.rng.choices(cluster_types, weights=cluster_weights, k=1)[0]

        clusters.append(
            Cluster(
                cluster_id=i,
                center_x=center[0],
                center_y=center[1],
                cluster_type=cluster_type,
            )
        )

    return clusters


def poisson(ctx: MapContext, lam: float) -> int:
    """Sample from Poisson distribution using inverse transform."""
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while p > limit:
        k += 1
        p *= ctx.rng.random()
    return k - 1


def pick_cluster_center(ctx: MapContext, existing_clusters: List[Cluster]) -> Tuple[float, float]:
    """Pick a cluster center respecting minimum spacing."""
    max_attempts = 100

    for _ in range(max_attempts):
        x = ctx.rng.uniform(ctx.config.cluster_radius, ctx.config.map_scale - ctx.config.cluster_radius)
        y = ctx.rng.uniform(ctx.config.cluster_radius, ctx.config.map_scale - ctx.config.cluster_radius)

        valid = True
        for cluster in existing_clusters:
            dist = math.sqrt((x - cluster.center_x) ** 2 + (y - cluster.center_y) ** 2)
            if dist < ctx.config.min_cluster_spacing:
                valid = False
                break

        if valid:
            return (x, y)

    return (
        ctx.rng.uniform(0, ctx.config.map_scale),
        ctx.rng.uniform(0, ctx.config.map_scale),
    )


def populate_cluster(
    ctx: MapContext,
    cluster: Cluster,
    nodes: Dict[int, Node],
    adjacency: Dict[int, List[int]],
) -> None:
    """Generate locations within a cluster using separate Poisson processes for homes and other locations."""
    num_homes = max(1, poisson(ctx, ctx.config.homes_per_cluster_lambda))
    num_other_locations = max(0, poisson(ctx, ctx.config.other_locations_per_cluster_lambda))

    for _ in range(num_homes):
        node = create_location_node(ctx, cluster, "residence")
        nodes[node.node_id] = node
        adjacency[node.node_id] = []
        cluster.node_ids.append(node.node_id)

    for _ in range(num_other_locations):
        node = create_location_node(ctx, cluster, "junction")
        nodes[node.node_id] = node
        adjacency[node.node_id] = []
        cluster.node_ids.append(node.node_id)

    if cluster.node_ids:
        cluster.entry_node_id = min(
            cluster.node_ids,
            key=lambda nid: ctx.distance_to_point(nodes[nid], cluster.center_x, cluster.center_y),
        )


def create_location_node(ctx: MapContext, cluster: Cluster, kind: str) -> Node:
    """Create a location node within cluster radius."""
    angle = ctx.rng.uniform(0, 2 * math.pi)
    radius = ctx.rng.uniform(0, ctx.config.cluster_radius) * math.sqrt(ctx.rng.random())

    x = cluster.center_x + radius * math.cos(angle)
    y = cluster.center_y + radius * math.sin(angle)

    node_id = ctx.next_node_id()
    return Node(
        node_id=node_id,
        x=x,
        y=y,
        kind=kind,
        district=cluster.cluster_type,
        cluster_id=cluster.cluster_id,
    )
