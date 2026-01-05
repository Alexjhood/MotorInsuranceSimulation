from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import List

from simulator.agents.driver import DriverProfile
from simulator.agents.vehicle import VehicleProfile
from simulator.mapgen.mapgen import Edge


@dataclass(frozen=True)
class AccidentEvent:
    step: int
    location: int
    participants: List[int]
    severity: str
    at_fault: int
    total_claim: float
    claim_breakdown: dict


SEVERITY_LEVELS = ("minor", "moderate", "severe")


def accident_probability(edge: Edge, driver: DriverProfile, time_of_day: str) -> float:
    time_factor = 1.0 if time_of_day == "day" else 1.2
    risk_level_factor = {"low": 0.6, "medium": 1.0, "high": 1.5}[driver.risk_level]
    speed_factor = 1.0 + (edge.speed_limit / 80.0) * driver.speed_bias
    road_type_factor = {"single_lane": 1.05, "two_lane": 1.0, "highway": 1.2}.get(edge.road_type, 1.0)
    crossing_factor = 1.15 if edge.has_crossing else 1.0
    cyclist_factor = 1.1 if edge.has_cycle_lane else 1.0
    return (
        0.002
        * edge.risk_factor
        * time_factor
        * risk_level_factor
        * speed_factor
        * road_type_factor
        * crossing_factor
        * cyclist_factor
    )


def severity_from_speed(speed: float) -> str:
    if speed < 22:
        return "minor"
    if speed < 35:
        return "moderate"
    return "severe"


def claim_amount(vehicle: VehicleProfile, severity: str, rng: random.Random) -> dict:
    severity_multiplier = {"minor": 0.15, "moderate": 0.45, "severe": 0.9}[severity]
    property_damage = vehicle.value * severity_multiplier * rng.uniform(0.75, 1.25)
    bodily_injury = vehicle.value * (severity_multiplier / 2.5) * rng.uniform(0.5, 1.5)
    return {
        "property_damage": property_damage,
        "bodily_injury": bodily_injury,
        "total": property_damage + bodily_injury,
    }


def assign_liability(participant_ids: List[int], driver_risks: List[DriverProfile], rng: random.Random) -> int:
    if len(participant_ids) == 1:
        return participant_ids[0]
    risk_scores = [
        {"low": 0.4, "medium": 0.6, "high": 0.85}[profile.risk_level] for profile in driver_risks
    ]
    total = sum(risk_scores)
    pick = rng.random() * total
    cumulative = 0.0
    for participant_id, score in zip(participant_ids, risk_scores):
        cumulative += score
        if pick <= cumulative:
            return participant_id
    return participant_ids[-1]


def build_accident(
    step: int,
    location: int,
    participant_ids: List[int],
    driver_profiles: List[DriverProfile],
    vehicle_profiles: List[VehicleProfile],
    speed: float,
    rng: random.Random,
) -> AccidentEvent:
    severity = severity_from_speed(speed)
    at_fault = assign_liability(participant_ids, driver_profiles, rng)
    claims = [claim_amount(vehicle, severity, rng) for vehicle in vehicle_profiles]
    total = sum(item["total"] for item in claims)
    return AccidentEvent(
        step=step,
        location=location,
        participants=participant_ids,
        severity=severity,
        at_fault=at_fault,
        total_claim=total,
        claim_breakdown={
            "by_vehicle": claims,
            "severity": severity,
            "impact_speed": speed,
        },
    )
