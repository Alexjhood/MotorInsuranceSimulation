from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriverProfile:
    risk_level: str
    speed_bias: float
    aggression: float


RISK_LEVELS = {
    "low": (0.85, 0.8),
    "medium": (1.0, 1.0),
    "high": (1.2, 1.2),
}


def build_driver(risk_level: str) -> DriverProfile:
    speed_bias, aggression = RISK_LEVELS[risk_level]
    return DriverProfile(risk_level=risk_level, speed_bias=speed_bias, aggression=aggression)
