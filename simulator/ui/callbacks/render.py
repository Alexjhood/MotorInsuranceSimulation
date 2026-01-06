from __future__ import annotations

import logging
import time

import dash
from dash.dependencies import Input, Output, State

from simulator.config import SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.reporting.summary import summarize_run
from simulator.ui.plotting import _build_placeholder_figure, build_map_figure, build_summary_map_figure
from simulator.ui.progress_utils import normalize_progress
from simulator.ui.serialization import deserialize_sim
from simulator.ui.sim_cache import render_gate, simulation_cache
from simulator.ui.summary_view import build_summary_content

logger = logging.getLogger(__name__)


def register_render_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("sim-graph", "figure"),
        Output("summary-content", "children"),
        Output("timing-store", "data", allow_duplicate=True),
        Output("progress-store", "data", allow_duplicate=True),
        Input("sim-state", "data"),
        Input("accident-store", "data"),
        Input("selected-agent", "data"),
        Input("label-options", "value"),
        Input("control-tabs", "value"),
        Input("view-store", "data"),
        Input("visualization-toggle", "value"),
        Input("agent-size-slider", "value"),
        Input("other-size-slider", "value"),
        State("timing-store", "data"),
        State("progress-store", "data"),
        prevent_initial_call=True,
    )
    def render_simulation(
        state,
        accidents,
        selected_agent,
        label_options,
        control_tab,
        view_store,
        viz_toggle,
        agent_size,
        other_size,
        timing_data,
        progress_data,
    ):
        render_start = time.perf_counter()
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        should_update_progress = trigger in {"sim-state", "accident-store"}
        timing_data = timing_data or []
        progress_data = progress_data or {}
        show_visualization = viz_toggle and "show_viz" in viz_toggle

        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            summary = summarize_run(simulation)
            summary_content = build_summary_content(summary)
            if show_visualization:
                if control_tab == "summary-tab":
                    figure = build_summary_map_figure(
                        simulation,
                        [accident.__dict__ for accident in simulation.accidents],
                    )
                else:
                    figure = build_map_figure(
                        simulation,
                        accidents or [],
                        selected_agent,
                        label_options,
                        agent_size_mult=agent_size or 1.0,
                        other_size_mult=other_size or 1.0,
                    )
            else:
                figure = _build_placeholder_figure("Visualization disabled - simulation running in background")
            progress_update = progress_data if should_update_progress else dash.no_update
            return figure, summary_content, timing_data, progress_update

        t0 = time.perf_counter()
        # Try to use cached simulation to avoid expensive deserialization
        cached_sim = simulation_cache.get()
        if cached_sim is not None and simulation_cache.is_valid_for(state):
            simulation = cached_sim
            deser_time = (time.perf_counter() - t0) * 1000
            logger.debug(f"[RENDER] Using cached simulation (step={simulation.step_index}) in {deser_time:.1f}ms")
        else:
            simulation = deserialize_sim(state)
            deser_time = (time.perf_counter() - t0) * 1000
            logger.debug(f"[RENDER] Full deserialization in {deser_time:.1f}ms")

        t0 = time.perf_counter()
        summary = summarize_run(simulation)
        summary_time = (time.perf_counter() - t0) * 1000
        summary_content = build_summary_content(summary)

        if not show_visualization:
            total_render = (time.perf_counter() - render_start) * 1000
            figure = _build_placeholder_figure(
                "Visualization disabled\n\n"
                f"Step: {simulation.step_index}\n"
                f"Active agents: {sum(1 for a in simulation.agents.values() if not a.is_idle)}/{len(simulation.agents)}\n"
                f"Total accidents: {len(simulation.accidents)}\n\n"
                f"Render callback: {total_render:.0f}ms (deser: {deser_time:.0f}ms, summary: {summary_time:.0f}ms)"
            )
            if timing_data:
                timing_data[-1]["render_breakdown"] = {
                    "deserialize": deser_time,
                    "summarize": summary_time,
                    "total": total_render,
                    "build_figure": 0,
                }
            progress_update = dash.no_update
            if should_update_progress:
                progress_update = _update_progress_with_render(
                    progress_data,
                    timing_data,
                    deser_time,
                    summary_time,
                    0,
                    total_render,
                )
            # Signal render complete to allow next advance
            render_gate.render_completed(simulation.step_index)
            logger.info(f"[RENDER] Step {simulation.step_index} rendered in {total_render:.1f}ms (viz disabled)")
            return figure, summary_content, timing_data, progress_update

        view_bounds = None
        if view_store:
            view_bounds = (
                view_store["x"][0],
                view_store["x"][1],
                view_store["y"][0],
                view_store["y"][1],
            )

        t0 = time.perf_counter()
        if control_tab == "summary-tab":
            figure = build_summary_map_figure(
                simulation,
                [accident.__dict__ for accident in simulation.accidents],
                view_bounds=view_bounds,
            )
        else:
            figure = build_map_figure(
                simulation,
                accidents or [],
                selected_agent,
                label_options,
                view_bounds=view_bounds,
                agent_size_mult=agent_size or 1.0,
                other_size_mult=other_size or 1.0,
            )
        figure_time = (time.perf_counter() - t0) * 1000
        total_render = (time.perf_counter() - render_start) * 1000

        if timing_data:
            timing_data[-1]["render_breakdown"] = {
                "deserialize": deser_time,
                "summarize": summary_time,
                "build_figure": figure_time,
                "total": total_render,
            }

        progress_update = dash.no_update
        if should_update_progress:
            progress_update = _update_progress_with_render(
                progress_data,
                timing_data,
                deser_time,
                summary_time,
                figure_time,
                total_render,
            )

        # Signal render complete to allow next advance
        render_gate.render_completed(simulation.step_index)
        logger.info(f"[RENDER] Step {simulation.step_index} rendered in {total_render:.1f}ms")
        return figure, summary_content, timing_data, progress_update


def _update_progress_with_render(
    progress_data: dict,
    timing_data: list,
    deser_time: float,
    summary_time: float,
    figure_time: float,
    total_render: float,
) -> dict:
    progress_data = normalize_progress(progress_data or {})
    phases = progress_data.get("phases", [])
    phases = [phase for phase in phases if phase.get("category") not in {"render", "outside"}]

    render_subtotal = deser_time + summary_time + figure_time
    render_overhead = max(total_render - render_subtotal, 0)
    outside_ms = None
    last_timing = timing_data[-1] if timing_data else {}
    advance_total = last_timing.get("tasks", {}).get("total_perf", 0)
    real_elapsed_ms = last_timing.get("real_elapsed_ms")
    if real_elapsed_ms is not None:
        outside_ms = max(real_elapsed_ms - (advance_total + total_render), 0)

    render_phases = [
        {
            "name": "Render: deserialize state",
            "total": 1,
            "completed": 1,
            "duration_ms": deser_time,
            "progress_pct": 100,
            "category": "render",
            "state": "complete",
        },
        {
            "name": "Render: summarize",
            "total": 1,
            "completed": 1,
            "duration_ms": summary_time,
            "progress_pct": 100,
            "category": "render",
            "state": "complete",
        },
        {
            "name": "Render: build figure",
            "total": 1,
            "completed": 1,
            "duration_ms": figure_time,
            "progress_pct": 100,
            "category": "render",
            "state": "complete",
        },
        {
            "name": "Render: overhead",
            "total": 1,
            "completed": 1,
            "duration_ms": render_overhead,
            "progress_pct": 100,
            "category": "render",
            "state": "complete",
        },
        {
            "name": "Outside (network/browser)",
            "total": 1,
            "completed": 1,
            "duration_ms": outside_ms or 0,
            "progress_pct": 100,
            "category": "outside",
            "state": "complete",
            "summary": {
                "real_elapsed_ms": f"{real_elapsed_ms:.0f}" if real_elapsed_ms is not None else "n/a",
                "callback_total_ms": f"{advance_total + total_render:.0f}",
            },
        },
    ]

    progress_data["phases"] = phases + render_phases
    progress_data["render_ms"] = total_render
    progress_data["callback_total_ms"] = advance_total + total_render
    if outside_ms is not None:
        progress_data["outside_ms"] = outside_ms
    return progress_data
