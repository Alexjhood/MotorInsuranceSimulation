from __future__ import annotations

import time

import dash
from dash.dependencies import Input, Output, State

from simulator.config import SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.reporting.summary import summarize_run
from simulator.ui.plotting import _build_placeholder_figure, build_map_figure, build_summary_map_figure
from simulator.ui.serialization import deserialize_sim
from simulator.ui.summary_view import build_summary_content


def register_render_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("sim-graph", "figure"),
        Output("summary-content", "children"),
        Output("timing-store", "data", allow_duplicate=True),
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
    ):
        render_start = time.perf_counter()
        timing_data = timing_data or []
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
            return figure, summary_content, timing_data

        t0 = time.perf_counter()
        simulation = deserialize_sim(state)
        deser_time = (time.perf_counter() - t0) * 1000

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
            return figure, summary_content, timing_data

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

        return figure, summary_content, timing_data
