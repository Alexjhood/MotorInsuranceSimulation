from __future__ import annotations

from typing import Dict, List, Set

from simulator.mapgen.context import MapContext
from simulator.mapgen.data import Cluster, Node


def assign_pois(ctx: MapContext, nodes: Dict[int, Node], clusters: List[Cluster]) -> Dict[str, List[int]]:
    """Assign POI types to nodes based on cluster types."""
    pois: Dict[str, List[int]] = {
        "residence": [],
        "work": [],
        "commerce": [],
        "leisure": [],
        "crossing": [],
        "cyclist": [],
    }

    for nid, node in nodes.items():
        if node.kind in pois:
            pois[node.kind].append(nid)

    cluster_to_poi = {
        "residential": "residence",
        "work": "work",
        "commerce": "commerce",
        "leisure": "leisure",
    }

    for cluster in clusters:
        poi_type = cluster_to_poi.get(cluster.cluster_type, "residence")
        available = [nid for nid in cluster.node_ids if nodes[nid].kind == "junction"]

        num_pois = max(1, len(available) // 2)
        ctx.rng.shuffle(available)

        for nid in available[:num_pois]:
            nodes[nid].kind = poi_type
            pois[poi_type].append(nid)

    ensure_minimum_pois(ctx, nodes, pois, "residence", ctx.config.min_residences)
    ensure_minimum_pois(ctx, nodes, pois, "work", ctx.config.min_workplaces)
    ensure_minimum_pois(ctx, nodes, pois, "commerce", ctx.config.min_commerce)
    ensure_minimum_pois(ctx, nodes, pois, "leisure", ctx.config.min_leisure)

    junction_nodes = [nid for nid, n in nodes.items() if n.kind in {"junction", "minor_junction"}]

    crossing_count = max(1, int(len(junction_nodes) * ctx.config.pedestrian_crossing_ratio))
    cyclist_count = max(1, int(len(junction_nodes) * ctx.config.cyclist_hub_ratio))

    ctx.rng.shuffle(junction_nodes)
    for nid in junction_nodes[:crossing_count]:
        nodes[nid].kind = "crossing"
        pois["crossing"].append(nid)

    remaining = [nid for nid in junction_nodes if nodes[nid].kind != "crossing"]
    for nid in remaining[:cyclist_count]:
        nodes[nid].kind = "cyclist"
        pois["cyclist"].append(nid)

    return pois


def ensure_minimum_pois(
    ctx: MapContext,
    nodes: Dict[int, Node],
    pois: Dict[str, List[int]],
    poi_type: str,
    minimum: int,
) -> None:
    """Ensure minimum number of POIs of a given type."""
    current = len(pois[poi_type])
    if current >= minimum:
        return

    available = [nid for nid, n in nodes.items() if n.kind == "junction"]
    ctx.rng.shuffle(available)

    needed = minimum - current
    for nid in available[:needed]:
        nodes[nid].kind = poi_type
        pois[poi_type].append(nid)


def assign_junction_types(
    ctx: MapContext,
    nodes: Dict[int, Node],
    adjacency: Dict[int, List[int]],
    highway_nodes: Set[int],
) -> None:
    """Assign major/minor junction types based on connectivity."""
    junction_nodes = [nid for nid, node in nodes.items() if node.kind == "junction"]

    junction_nodes.sort(key=lambda nid: len(adjacency.get(nid, [])), reverse=True)

    major_count = int(len(junction_nodes) * ctx.config.major_junction_ratio)
    major_set = set(junction_nodes[:major_count])

    for nid in junction_nodes:
        if nid in highway_nodes:
            nodes[nid].kind = "major_junction"
        elif nid in major_set:
            nodes[nid].kind = "major_junction"
        else:
            nodes[nid].kind = "minor_junction"
