from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class MapConfig:
    width: int = 20
    height: int = 14
    road_density: float = 0.85
    roundabout_count: int = 3
    speed_limits: List[int] = field(default_factory=lambda: [20, 30, 40, 50])
    residential_count: int = 12
    work_count: int = 6
    visit_count: int = 8


@dataclass(frozen=True)
class DriverConfig:
    count: int = 20
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
