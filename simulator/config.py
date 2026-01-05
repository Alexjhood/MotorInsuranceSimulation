from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class MapConfig:
    width: int = 20
    height: int = 14
    road_density: float = 0.85
    roundabout_count: int = 3
    residential_count: int = 12
    work_count: int = 6
    commerce_count: int = 6
    leisure_count: int = 6
    pedestrian_crossing_count: int = 6
    cyclist_hub_count: int = 5
    road_type_weights: Dict[str, float] = field(
        default_factory=lambda: {"single_lane": 0.55, "two_lane": 0.3, "highway": 0.15}
    )
    speed_limits_by_type: Dict[str, int] = field(
        default_factory=lambda: {"single_lane": 25, "two_lane": 35, "highway": 55}
    )
    lanes_by_type: Dict[str, int] = field(
        default_factory=lambda: {"single_lane": 1, "two_lane": 2, "highway": 4}
    )
    cycle_lane_chance: float = 0.2


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
