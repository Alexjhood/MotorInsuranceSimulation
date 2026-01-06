from __future__ import annotations

import random

import dash
from dash.dependencies import Input, Output, State

from simulator.engine.simulation import Simulation
from simulator.ui.history import server_history
from simulator.ui.serialization import config_from_inputs, serialize_sim


def register_control_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("sim-state", "data"),
        Output("accident-store", "data"),
        Output("history-index", "data"),
        Output("tick", "disabled"),
        Input("start-btn", "n_clicks"),
        Input("pause-btn", "n_clicks"),
        Input("reset-btn", "n_clicks"),
        Input("setup-reset-btn", "n_clicks"),
        State("seed-input", "value"),
        State("map-scale-input", "value"),
        State("cluster-lambda", "value"),
        State("homes-lambda", "value"),
        State("other-locations-lambda", "value"),
        State("cluster-spacing", "value"),
        State("dual-road-chance", "value"),
        State("roundabout-chance", "value"),
        State("highway-roundabout-chance", "value"),
        State("major-junction-ratio", "value"),
        State("journey-start-prob", "value"),
        State("cyclist-journey-start-prob", "value"),
        State("unilateral-prob", "value"),
        State("vehicle-encounter-prob", "value"),
        State("cyclist-encounter-prob", "value"),
        State("sim-state", "data"),
        prevent_initial_call=True,
    )
    def control_simulation(
        start,
        pause,
        reset,
        setup_reset,
        seed,
        map_scale,
        cluster_lambda,
        homes_lambda,
        other_locations_lambda,
        cluster_spacing,
        dual_road_chance,
        roundabout_chance,
        highway_roundabout_chance,
        major_junction_ratio,
        journey_start_prob,
        cyclist_journey_start_prob,
        unilateral_prob,
        vehicle_encounter_prob,
        cyclist_encounter_prob,
        state,
    ):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if state is None:
            config = config_from_inputs(
                seed,
                map_scale,
                cluster_lambda,
                homes_lambda,
                other_locations_lambda,
                cluster_spacing,
                dual_road_chance,
                roundabout_chance,
                highway_roundabout_chance,
                major_junction_ratio,
                journey_start_prob,
                cyclist_journey_start_prob,
                unilateral_prob,
                vehicle_encounter_prob,
                cyclist_encounter_prob,
            )
            sim = Simulation(config)
            new_state = serialize_sim(sim)
            server_history.reset()
            idx = server_history.append(new_state, [])
            disabled = False if trigger == "start-btn" else True
            return new_state, [], idx, disabled
        if trigger == "pause-btn":
            return state, dash.no_update, dash.no_update, True
        if trigger in {"reset-btn", "setup-reset-btn"}:
            config = config_from_inputs(
                seed,
                map_scale,
                cluster_lambda,
                homes_lambda,
                other_locations_lambda,
                cluster_spacing,
                dual_road_chance,
                roundabout_chance,
                highway_roundabout_chance,
                major_junction_ratio,
                journey_start_prob,
                cyclist_journey_start_prob,
                unilateral_prob,
                vehicle_encounter_prob,
                cyclist_encounter_prob,
            )
            sim = Simulation(config)
            new_state = serialize_sim(sim)
            server_history.reset()
            idx = server_history.append(new_state, [])
            return new_state, [], idx, True
        if trigger == "start-btn":
            return state, dash.no_update, dash.no_update, False
        return state, dash.no_update, dash.no_update, False

    @app.callback(
        Output("tick", "interval"),
        Input("speed-control", "value"),
    )
    def update_tick_interval(speed: float) -> int:
        return max(int(1000 / max(speed or 1, 0.5)), 100)

    @app.callback(
        Output("tick", "disabled", allow_duplicate=True),
        Input("control-tabs", "value"),
        prevent_initial_call=True,
    )
    def pause_on_summary(tab_value: str):
        if tab_value == "summary-tab":
            return True
        return dash.no_update

    @app.callback(
        Output("seed-input", "value"),
        Input("seed-random-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def randomize_seed(_):
        return random.randint(1, 9999)
