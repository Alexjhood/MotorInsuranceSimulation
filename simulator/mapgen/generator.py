from __future__ import annotations

import random
from typing import Dict, List

from simulator.config import MapConfig
from simulator.mapgen.clusters import generate_clusters, populate_cluster
from simulator.mapgen.context import MapContext
from simulator.mapgen.data import Cluster, Edge, MapData, Node
from simulator.mapgen.pois import assign_junction_types, assign_pois
from simulator.mapgen.roads import build_cluster_road_network, build_highway_network


class MapGenerator:
    def __init__(self, config: MapConfig, seed: int) -> None:
        self.context = MapContext(config=config, rng=random.Random(seed))

    def generate(self) -> MapData:
        nodes: Dict[int, Node] = {}
        adjacency: Dict[int, List[int]] = {}
        edges: List[Edge] = []

        clusters = generate_clusters(self.context)

        if not clusters:
            clusters = [
                Cluster(
                    cluster_id=0,
                    center_x=self.context.config.map_scale / 2,
                    center_y=self.context.config.map_scale / 2,
                    cluster_type="residential",
                )
            ]

        for cluster in clusters:
            populate_cluster(self.context, cluster, nodes, adjacency)

        for cluster in clusters:
            build_cluster_road_network(self.context, cluster, nodes, adjacency, edges)

        highway_nodes = build_highway_network(self.context, clusters, nodes, adjacency, edges)

        pois = assign_pois(self.context, nodes, clusters)

        assign_junction_types(self.context, nodes, adjacency, highway_nodes)

        return MapData(
            nodes=nodes,
            edges=edges,
            adjacency=adjacency,
            pois=pois,
            clusters=clusters,
        )
