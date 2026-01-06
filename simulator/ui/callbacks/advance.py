from __future__ import annotations

import json
import logging
import threading
import time
import traceback

import dash
from dash.dependencies import Input, Output, State

from simulator.config import SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.ui.history import server_history
from simulator.ui.live_progress import live_progress_store
from simulator.ui.progress_utils import build_phase_template, normalize_progress, update_phase
from simulator.ui.serialization import deserialize_sim, serialize_sim
from simulator.ui.sim_cache import render_gate, simulation_cache

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Lock to prevent concurrent advance callbacks
_advance_lock = threading.Lock()
_advance_in_progress = False


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
        global _advance_in_progress
        
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        log_data = log_data or []
        timing_data = timing_data or []
        progress_data = progress_data or {}
        
        # Prevent concurrent callbacks - if one is already running, skip this one
        with _advance_lock:
            if _advance_in_progress and trigger == "tick":
                logger.debug(f"[ADVANCE] Skipping tick - another callback is in progress")
                raise dash.exceptions.PreventUpdate()
            _advance_in_progress = True
        
        # Wait for render to complete before starting next step
        if trigger == "tick" and not render_gate.can_advance():
            with _advance_lock:
                _advance_in_progress = False
            raise dash.exceptions.PreventUpdate()
        
        try:
            return _do_advance_simulation(
                trigger, state, accidents, history_index, log_data, timing_data, last_step_ts, progress_data
            )
        finally:
            with _advance_lock:
                _advance_in_progress = False

    def _do_advance_simulation(
        trigger, state, accidents, history_index, log_data, timing_data, last_step_ts, progress_data
    ):
        step_details = {"phase": "advance_callback", "timings": [], "data_sizes": {}, "data_size_errors": {}}

        def record_timing(label: str, start_time: float):
            elapsed = (time.perf_counter() - start_time) * 1000
            step_details["timings"].append({"label": label, "ms": elapsed})
            return time.perf_counter()

        def estimate_state_counts(payload: dict | None) -> dict:
            if not payload:
                return {}
            map_data = payload.get("map_data", {})
            return {
                "nodes": len(map_data.get("nodes", {})),
                "edges": len(map_data.get("edges", [])),
                "agents": len(payload.get("agents", [])),
            }

        def safe_json_size(payload, label: str) -> int | None:
            if payload is None:
                return 0
            if isinstance(payload, dict) and "map_data" in payload:
                counts = estimate_state_counts(payload)
                if counts and (
                    counts.get("nodes", 0) > 20000
                    or counts.get("edges", 0) > 40000
                    or counts.get("agents", 0) > 20000
                ):
                    step_details["data_size_errors"][label] = (
                        "Skipped size measurement "
                        f"(nodes={counts.get('nodes')}, edges={counts.get('edges')}, agents={counts.get('agents')})"
                    )
                    return None
            try:
                return len(json.dumps(payload))
            except Exception as exc:
                step_details["data_size_errors"][label] = str(exc)
                return None

        callback_start = time.perf_counter()
        this_step_start = time.time()

        real_elapsed_ms = None
        if last_step_ts is not None:
            real_elapsed_ms = (this_step_start - last_step_ts) * 1000

        t0 = time.perf_counter()
        step_details["data_sizes"]["state_in"] = safe_json_size(state, "state_in")
        step_details["data_sizes"]["history_in"] = 0
        step_details["data_sizes"]["timing_data_in"] = safe_json_size(timing_data, "timing_data_in")
        step_details["data_sizes"]["log_data_in"] = safe_json_size(log_data, "log_data_in")
        state_counts_in = estimate_state_counts(state)
        if state_counts_in:
            step_details["state_counts"] = {"input": state_counts_in}
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

        logger.info(f"[ADVANCE] Starting advance_simulation callback, trigger={trigger}")
        step_timing = {"step": 0, "tasks": {}, "sim_breakdown": {}, "real_elapsed_ms": real_elapsed_ms}
        wall_clock_start = time.time()
        total_start = time.perf_counter()
        progress_snapshot = {
            "step": (state.get("step_index", 0) + 1) if isinstance(state, dict) else "?",
            "phases": build_phase_template(),
            "status": "running",
            "current_phase": "Deserialize state",
        }
        if state_counts_in:
            progress_snapshot["stats"] = state_counts_in
        update_phase(progress_snapshot["phases"], "Deserialize state", state="running", progress_pct=0)
        step_started = False
        after_step = False

        simulation = None
        try:
            logger.info(f"[ADVANCE] Starting deserialization, state_counts={state_counts_in}")
            deserialize_start = time.perf_counter()
            
            # Try to use cached simulation to avoid expensive map regeneration
            cached_sim = simulation_cache.get()
            if cached_sim is not None and simulation_cache.is_valid_for(state):
                simulation = cached_sim
                deser_time = (time.perf_counter() - deserialize_start) * 1000
                logger.info(f"[ADVANCE] Using CACHED simulation (step={simulation.step_index}) in {deser_time:.1f}ms")
            else:
                # Cache miss - need full deserialization
                simulation = deserialize_sim(state)
                simulation_cache.set(simulation)
                deser_time = (time.perf_counter() - deserialize_start) * 1000
                logger.info(f"[ADVANCE] Full deserialization in {deser_time:.1f}ms, agents={len(simulation.agents)}, nodes={len(simulation.map_data.nodes)}")
            
            step_timing["tasks"]["deserialize"] = deser_time
            step_timing["step"] = simulation.step_index + 1
            progress_snapshot["step"] = simulation.step_index + 1
            progress_snapshot["current_phase"] = "Simulation step (overall)"
            update_phase(
                progress_snapshot["phases"],
                "Deserialize state",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["deserialize"],
                progress_pct=100,
            )
            update_phase(progress_snapshot["phases"], "Simulation step (overall)", state="running", progress_pct=0)

            sim_step_start = time.perf_counter()
            step_started = True
            
            # Initialize live progress store for real-time updates
            logger.info(f"[ADVANCE] Initializing live progress store for step {simulation.step_index + 1}")
            live_progress_store.start_step(
                step=simulation.step_index + 1,
                stats={
                    "agents": len(simulation.agents),
                    "nodes": len(simulation.map_data.nodes),
                    "edges": len(simulation.map_data.edges),
                }
            )
            
            # Progress callback for real-time updates during simulation
            last_log_time = [time.perf_counter()]  # Use list to allow mutation in closure
            def on_progress(phase_name: str, completed: int, total: int) -> None:
                live_progress_store.update_phase(phase_name, completed=completed, total=total)
                # Log progress every 2 seconds to avoid spam
                now = time.perf_counter()
                if now - last_log_time[0] > 2.0:
                    pct = (completed / total * 100) if total > 0 else 0
                    logger.info(f"[ADVANCE] Progress: {phase_name} {completed}/{total} ({pct:.1f}%)")
                    last_log_time[0] = now
            
            logger.info(f"[ADVANCE] Starting simulation.step() for step {simulation.step_index + 1}")
            result = simulation.step(progress_callback=on_progress)
            
            sim_step_ms = (time.perf_counter() - sim_step_start) * 1000
            logger.info(f"[ADVANCE] simulation.step() completed in {sim_step_ms:.1f}ms, accidents={len(result.accidents)}")
            
            # Mark step complete in live progress store
            live_progress_store.complete_step(
                total_ms=sim_step_ms,
                accident_count=len(result.accidents)
            )
            step_timing["tasks"]["simulation_step"] = sim_step_ms
            after_step = True
            progress_snapshot["current_phase"] = "Process accidents"
            update_phase(
                progress_snapshot["phases"],
                "Simulation step (overall)",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["simulation_step"],
                progress_pct=100,
            )
            update_phase(progress_snapshot["phases"], "Process accidents", state="running", progress_pct=0)

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
            update_phase(
                progress_snapshot["phases"],
                "Process accidents",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["process_accidents"],
                progress_pct=100,
            )

            serialize_start = time.perf_counter()
            progress_snapshot["current_phase"] = "Serialize state"
            update_phase(progress_snapshot["phases"], "Serialize state", state="running", progress_pct=0)
            logger.info(f"[ADVANCE] Starting serialization")
            new_state = serialize_sim(simulation)
            serialize_ms = (time.perf_counter() - serialize_start) * 1000
            step_timing["tasks"]["serialize"] = serialize_ms
            logger.info(f"[ADVANCE] Serialization complete in {serialize_ms:.1f}ms")
            
            # Update cache with the advanced simulation
            simulation_cache.set(simulation)
            
            # Signal that this step is pending render
            render_gate.step_completed(simulation.step_index)
            
            update_phase(
                progress_snapshot["phases"],
                "Serialize state",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["serialize"],
                progress_pct=100,
            )

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
            progress_data = normalize_progress(result.progress or {"step": simulation.step_index, "phases": []})
            if not progress_data.get("stats"):
                progress_data["stats"] = {
                    "agents": len(simulation.agents),
                    "nodes": len(simulation.map_data.nodes),
                    "edges": len(simulation.map_data.edges),
                }
            if progress_data.get("total_ms") is not None:
                progress_data["sim_total_ms"] = progress_data.get("total_ms")
            progress_data["total_ms"] = step_timing["tasks"]["total_perf"]
            other_task_total = (
                step_timing["tasks"]["deserialize"]
                + step_timing["tasks"]["simulation_step"]
                + step_timing["tasks"]["process_accidents"]
                + step_timing["tasks"]["serialize"]
            )
            finalize_ms = max(step_timing["tasks"]["total_perf"] - other_task_total, 0)
            update_phase(
                progress_data["phases"],
                "Deserialize state",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["deserialize"],
                progress_pct=100,
            )
            update_phase(
                progress_data["phases"],
                "Simulation step (overall)",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["simulation_step"],
                progress_pct=100,
            )
            update_phase(
                progress_data["phases"],
                "Process accidents",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["process_accidents"],
                progress_pct=100,
                summary={"accidents_processed": len(accidents)},
            )
            update_phase(
                progress_data["phases"],
                "Serialize state",
                state="complete",
                total=1,
                completed=1,
                duration_ms=step_timing["tasks"]["serialize"],
                progress_pct=100,
            )
            update_phase(
                progress_data["phases"],
                "Finalize + history update",
                state="complete",
                total=1,
                completed=1,
                duration_ms=finalize_ms,
                progress_pct=100,
            )
            progress_data["real_elapsed_ms"] = real_elapsed_ms
            progress_data["callback_ms"] = step_timing["tasks"]["total_perf"]
            progress_data["timestamp"] = time.time()
            progress_data["current_phase"] = "completed"
            progress_data["status"] = "complete"

            t0 = time.perf_counter()
            step_details["data_sizes"]["state_out"] = safe_json_size(new_state, "state_out")
            step_details["data_sizes"]["history_out"] = 0
            step_details["data_sizes"]["timing_data_out"] = safe_json_size(timing_data, "timing_data_out")
            step_details["data_sizes"]["log_data_out"] = safe_json_size(log_data, "log_data_out")
            state_counts_out = estimate_state_counts(new_state)
            if state_counts_out:
                step_details.setdefault("state_counts", {})["output"] = state_counts_out
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
            if simulation and step_started and not after_step and getattr(simulation, "last_progress", None):
                progress_data = simulation.last_progress or progress_data
            else:
                progress_data = progress_snapshot or progress_data
            progress_data = progress_data or {"step": step_timing.get("step", "?"), "phases": []}
            progress_data["status"] = "error"
            progress_data["error"] = str(e)
            progress_data["timestamp"] = time.time()
            current_phase = progress_data.get("current_phase")
            if current_phase:
                update_phase(progress_data.get("phases", []), current_phase, state="error")
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
