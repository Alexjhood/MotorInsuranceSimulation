from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import List

from simulator.config import SimulationConfig
from simulator.engine.simulation import Simulation, SimulationStepResult
from simulator.reporting.summary import summarize_run


@dataclass
class RunResult:
    steps: List[SimulationStepResult]
    summary: dict


def _run_single(seed: int, config: SimulationConfig) -> RunResult:
    config = SimulationConfig(
        seed=seed,
        steps=config.steps,
        map_config=config.map_config,
        driver_config=config.driver_config,
        accident_config=config.accident_config,
        time_of_day=config.time_of_day,
        enable_parallel=False,
        parallel_workers=config.parallel_workers,
    )
    simulation = Simulation(config)
    steps = simulation.run()
    return RunResult(steps=steps, summary=summarize_run(simulation))


class SimulationRunner:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.simulation = Simulation(config)

    def run_headless(self) -> RunResult:
        steps = self.simulation.run()
        return RunResult(steps=steps, summary=summarize_run(self.simulation))

    def run_parallel(self, runs: int) -> List[RunResult]:
        workers = min(self.config.parallel_workers, multiprocessing.cpu_count())
        seeds = [self.config.seed + i for i in range(runs)]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            runner = partial(_run_single, config=self.config)
            results = list(executor.map(runner, seeds))
        return results
