from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class MapConfig:
    # Cluster generation (Poisson processes)
    cluster_lambda: float = 3.0  # Expected number of clusters (minimum 1)
    homes_per_cluster_lambda: float = 4.0  # Expected homes per cluster
    other_locations_per_cluster_lambda: float = 4.0  # Expected other locations per cluster
    
    # Map dimensions (used for spacing clusters)
    map_scale: float = 100.0  # Scale factor for cluster spacing
    cluster_radius: float = 15.0  # Radius within which cluster locations are placed
    min_cluster_spacing: float = 40.0  # Minimum distance between cluster centers
    
    # Road network parameters
    intra_cluster_roundabout_chance: float = 0.15  # Chance of roundabout at cluster junctions
    intra_cluster_dual_road_chance: float = 0.3  # Chance of dual carriageway within cluster
    highway_merge_roundabout_chance: float = 0.4  # Chance of roundabout where highways merge
    major_junction_ratio: float = 0.14
    
    # Location type distribution within clusters
    cluster_type_weights: Dict[str, float] = field(
        default_factory=lambda: {"residential": 0.4, "work": 0.2, "commerce": 0.25, "leisure": 0.15}
    )
    
    # POI counts (now derived from cluster generation, but these set minimums)
    min_residences: int = 5
    min_workplaces: int = 3
    min_commerce: int = 3
    min_leisure: int = 2
    pedestrian_crossing_ratio: float = 0.1  # Ratio of nodes that become crossings
    cyclist_hub_ratio: float = 0.08  # Ratio of nodes that become cyclist hubs
    
    # Road specifications
    speed_limits_by_type: Dict[str, int] = field(
        default_factory=lambda: {"single_lane": 25, "dual_carriageway": 40, "highway": 70}
    )
    lanes_by_type: Dict[str, int] = field(
        default_factory=lambda: {"single_lane": 1, "dual_carriageway": 2, "highway": 4}
    )
    cycle_lane_chance: float = 0.0


@dataclass(frozen=True)
class DriverConfig:
    count: int = 20
    cyclist_count: int = 6
    risk_profiles: Dict[str, float] = field(
        default_factory=lambda: {"low": 0.35, "medium": 0.45, "high": 0.2}
    )


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 42
    steps: int = 200
    map_config: MapConfig = field(default_factory=MapConfig)
    driver_config: DriverConfig = field(default_factory=DriverConfig)
    time_of_day: str = "day"
    enable_parallel: bool = False
    parallel_workers: int = 2
