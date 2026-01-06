from __future__ import annotations

import json
import time
import traceback

import dash
from dash.dependencies import Input, Output, State

from simulator.config import SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.ui.history import server_history
from simulator.ui.serialization import deserialize_sim, serialize_sim


def register_advance_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("sim-state", "data", allow_duplicate=True),
        Output("accident-store", "data", allow_duplicate=True),
        Output("history-index", "data", allow_duplicate=True),
        Output("log-store", "data", allow_duplicate=True),
        Output("timing-store", "data", allow_duplicate=True),
        Output("last-step-timestamp", "data", allow_duplicate=True),
        Output("step-details-store", "data", allow_duplicate=True),
        Output("progress-store", "data", allow_duplicate=True),
        Input("tick", "n_intervals"),
        Input("step-btn", "n_clicks"),
        Input("back-btn", "n_clicks"),
        State("sim-state", "data"),
        State("accident-store", "data"),
        State("history-index", "data"),
        State("log-store", "data"),
        State("timing-store", "data"),
        State("last-step-timestamp", "data"),
        State("progress-store", "data"),
        prevent_initial_call=True,
    )
    def advance_simulation(
        _, __, ___, state, accidents, history_index, log_data, timing_data, last_step_ts, progress_data
    ):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        log_data = log_data or []
        timing_data = timing_data or []
        progress_data = progress_data or {}

        step_details = {"phase": "advance_callback", "timings": [], "data_sizes": {}}

        def record_timing(label: str, start_time: float):
            elapsed = (time.perf_counter() - start_time) * 1000
            step_details["timings"].append({"label": label, "ms": elapsed})
            return time.perf_counter()

        callback_start = time.perf_counter()
        this_step_start = time.time()

        real_elapsed_ms = None
        if last_step_ts is not None:
            real_elapsed_ms = (this_step_start - last_step_ts) * 1000

        t0 = time.perf_counter()
        step_details["data_sizes"]["state_in"] = len(json.dumps(state)) if state else 0
        step_details["data_sizes"]["history_in"] = 0
        step_details["data_sizes"]["timing_data_in"] = len(json.dumps(timing_data)) if timing_data else 0
        step_details["data_sizes"]["log_data_in"] = len(json.dumps(log_data)) if log_data else 0
        t0 = record_timing("measure_input_sizes", t0)

        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            state = serialize_sim(simulation)
        history_index = 0 if history_index is None else history_index

        if trigger == "back-btn":
            back_state, back_accidents, new_idx = server_history.go_back()
            if back_state is not None:
                log_data.append(
                    {
                        "type": "step",
                        "timestamp": time.time(),
                        "message": f"Stepped back to step {back_state.get('step_index', 0)}",
                    }
                )
                return (
                    back_state,
                    back_accidents,
                    new_idx,
                    log_data,
                    timing_data,
                    this_step_start,
                    step_details,
                    progress_data,
                )
            return (
                state,
                accidents,
                history_index,
                log_data,
                timing_data,
                last_step_ts,
                step_details,
                progress_data,
            )

        step_timing = {"step": 0, "tasks": {}, "sim_breakdown": {}, "real_elapsed_ms": real_elapsed_ms}
        wall_clock_start = time.time()
        total_start = time.perf_counter()

        try:
            deserialize_start = time.perf_counter()
            simulation = deserialize_sim(state)
            step_timing["tasks"]["deserialize"] = (time.perf_counter() - deserialize_start) * 1000
            step_timing["step"] = simulation.step_index + 1

            sim_step_start = time.perf_counter()
            result = simulation.step()
            step_timing["tasks"]["simulation_step"] = (time.perf_counter() - sim_step_start) * 1000

            if result.timing:
                step_timing["sim_breakdown"] = {
                    "agent_movement": result.timing.agent_movement_ms,
                    "lane_assignment": result.timing.lane_assignment_ms,
                    "occupancy_calc": result.timing.occupancy_calc_ms,
                    "unilateral_accidents": result.timing.unilateral_accidents_ms,
                    "multi_agent_accidents": result.timing.multi_agent_accidents_ms,
                    "event_logging": result.timing.event_logging_ms,
                    "sim_total": result.timing.total_step_ms,
                }

            accident_start = time.perf_counter()
            accidents = [
                {
                    "step": accident.step,
                    "location": accident.location,
                    "severity": accident.severity,
                    "total_claim": accident.total_claim,
                    "participants": accident.participants,
                }
                for accident in result.accidents
            ]
            step_timing["tasks"]["process_accidents"] = (time.perf_counter() - accident_start) * 1000

            serialize_start = time.perf_counter()
            new_state = serialize_sim(simulation)
            step_timing["tasks"]["serialize"] = (time.perf_counter() - serialize_start) * 1000

            step_timing["tasks"]["total_perf"] = (time.perf_counter() - total_start) * 1000
            step_timing["wall_clock_ms"] = (time.time() - wall_clock_start) * 1000
            step_timing["timestamp"] = time.time()

            timing_data.append(step_timing)
            if len(timing_data) > 30:
                timing_data = timing_data[-30:]

            active_count = sum(1 for a in simulation.agents.values() if not a.is_idle)
            real_time_str = f"REAL={real_elapsed_ms:.0f}ms" if real_elapsed_ms is not None else "REAL=N/A"
            log_entry = {
                "type": "step",
                "timestamp": time.time(),
                "step": simulation.step_index,
                "message": f"Step {simulation.step_index}: {real_time_str} (callback={step_timing['tasks']['total_perf']:.1f}ms)",
                "details": {
                    "active_agents": active_count,
                    "total_agents": len(simulation.agents),
                    "accidents_this_step": len(accidents),
                    "real_elapsed_ms": real_elapsed_ms,
                    "callback_ms": step_timing["tasks"]["total_perf"],
                    "sim_logic_ms": step_timing["tasks"]["simulation_step"],
                    "serialize_ms": step_timing["tasks"]["serialize"],
                },
            }
            log_data.append(log_entry)

            for accident in accidents:
                log_data.append(
                    {
                        "type": "accident",
                        "timestamp": time.time(),
                        "step": accident["step"],
                        "message": (
                            f"Accident at location {accident['location']}: "
                            f"severity={accident['severity']}, claim=${accident['total_claim']:.2f}"
                        ),
                    }
                )

            if len(log_data) > 100:
                log_data = log_data[-100:]

            new_history_index = server_history.append(new_state, accidents)
            progress_data = result.progress or {"step": simulation.step_index, "phases": []}
            progress_data["real_elapsed_ms"] = real_elapsed_ms
            progress_data["callback_ms"] = step_timing["tasks"]["total_perf"]
            progress_data["timestamp"] = time.time()

            t0 = time.perf_counter()
            step_details["data_sizes"]["state_out"] = len(json.dumps(new_state)) if new_state else 0
            step_details["data_sizes"]["history_out"] = 0
            step_details["data_sizes"]["timing_data_out"] = len(json.dumps(timing_data)) if timing_data else 0
            step_details["data_sizes"]["log_data_out"] = len(json.dumps(log_data)) if log_data else 0
            step_details["timings"].append(
                {"label": "measure_output_sizes", "ms": (time.perf_counter() - t0) * 1000}
            )

            step_details["step"] = simulation.step_index
            step_details["real_elapsed_ms"] = real_elapsed_ms
            step_details["callback_total_ms"] = (time.perf_counter() - callback_start) * 1000
            step_details["history_length"] = server_history.length

            return (
                new_state,
                accidents,
                new_history_index,
                log_data,
                timing_data,
                this_step_start,
                step_details,
                progress_data,
            )

        except Exception as e:
            elapsed = (time.time() - wall_clock_start) * 1000
            error_entry = {
                "type": "error",
                "timestamp": time.time(),
                "message": f"Error during simulation step (after {elapsed:.1f}ms): {str(e)}",
                "traceback": traceback.format_exc(),
            }
            log_data.append(error_entry)
            step_details["error"] = str(e)
            return (
                state,
                accidents,
                history_index,
                log_data,
                timing_data,
                this_step_start,
                step_details,
                progress_data,
            )
