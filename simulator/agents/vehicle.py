from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleProfile:
    class_name: str
    value: float
    safety_rating: float


VEHICLE_CLASSES = [
    ("compact", 15000.0, 0.9),
    ("sedan", 22000.0, 1.0),
    ("suv", 35000.0, 1.1),
    ("truck", 42000.0, 1.2),
]

BICYCLE_PROFILE = VehicleProfile(class_name="bicycle", value=800.0, safety_rating=0.6)
