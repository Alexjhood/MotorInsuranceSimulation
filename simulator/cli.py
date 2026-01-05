from __future__ import annotations

import argparse
import json

from simulator.config import DriverConfig, MapConfig, SimulationConfig
from simulator.engine.runner import SimulationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Motor insurance traffic simulator")
    parser.add_argument("--headless", action="store_true", help="Run a headless simulation")
    parser.add_argument("--steps", type=int, default=200, help="Number of steps to run")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--agents", type=int, default=20, help="Number of drivers")
    parser.add_argument("--map-width", type=int, default=20, help="Map width")
    parser.add_argument("--map-height", type=int, default=14, help="Map height")
    parser.add_argument("--parallel-runs", type=int, default=1, help="Number of runs to parallelize")
    parser.add_argument("--serve", action="store_true", help="Launch the Dash UI")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.serve:
        from simulator.ui.app import create_app

        app = create_app()
        app.run_server(debug=True)
        return

    config = SimulationConfig(
        seed=args.seed,
        steps=args.steps,
        map_config=MapConfig(width=args.map_width, height=args.map_height),
        driver_config=DriverConfig(count=args.agents),
    )
    runner = SimulationRunner(config)

    if args.parallel_runs > 1:
        results = runner.run_parallel(args.parallel_runs)
        summaries = [result.summary for result in results]
        print(json.dumps(summaries, indent=2))
        return

    result = runner.run_headless()
    print(json.dumps(result.summary, indent=2))


if __name__ == "__main__":
    main()
