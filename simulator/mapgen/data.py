from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
