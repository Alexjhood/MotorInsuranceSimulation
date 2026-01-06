from __future__ import annotations

from dataclasses import dataclass
import math
import random

from simulator.config import MapConfig
from simulator.mapgen.data import Node


@dataclass
class MapContext:
    config: MapConfig
    rng: random.Random
    node_id_counter: int = 0

    def next_node_id(self) -> int:
        node_id = self.node_id_counter
        self.node_id_counter += 1
        return node_id

    @staticmethod
    def distance(n1: Node, n2: Node) -> float:
        return math.sqrt((n1.x - n2.x) ** 2 + (n1.y - n2.y) ** 2)

    @staticmethod
    def distance_to_point(node: Node, x: float, y: float) -> float:
        return math.sqrt((node.x - x) ** 2 + (node.y - y) ** 2)
