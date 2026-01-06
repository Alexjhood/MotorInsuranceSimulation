from __future__ import annotations

import dash
from dash.dependencies import Input, Output, State

from simulator.config import SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.ui.plotting import _map_bounds
from simulator.ui.serialization import deserialize_sim


def register_view_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("view-store", "data"),
        Input("zoom-in-btn", "n_clicks"),
        Input("zoom-out-btn", "n_clicks"),
        Input("pan-left-btn", "n_clicks"),
        Input("pan-right-btn", "n_clicks"),
        Input("pan-up-btn", "n_clicks"),
        Input("pan-down-btn", "n_clicks"),
        Input("reset-view-btn", "n_clicks"),
        State("view-store", "data"),
        State("sim-state", "data"),
        prevent_initial_call=True,
    )
    def update_view(
        zoom_in,
        zoom_out,
        pan_left,
        pan_right,
        pan_up,
        pan_down,
        reset_view,
        view_store,
        state,
    ):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if state is None:
            simulation = Simulation(SimulationConfig())
            bounds = _map_bounds(simulation.map_data)
        else:
            simulation = deserialize_sim(state)
            bounds = _map_bounds(simulation.map_data)
        if not view_store:
            min_x, max_x, min_y, max_y = bounds
            view_store = {"x": [min_x, max_x], "y": [min_y, max_y]}
        if trigger == "reset-view-btn":
            min_x, max_x, min_y, max_y = bounds
            return {"x": [min_x, max_x], "y": [min_y, max_y]}
        min_x, max_x = view_store["x"]
        min_y, max_y = view_store["y"]
        width = max_x - min_x
        height = max_y - min_y
        if trigger == "zoom-in-btn":
            scale = 0.8
            new_width = width * scale
            new_height = height * scale
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            min_x = center_x - new_width / 2
            max_x = center_x + new_width / 2
            min_y = center_y - new_height / 2
            max_y = center_y + new_height / 2
        elif trigger == "zoom-out-btn":
            scale = 1.25
            new_width = width * scale
            new_height = height * scale
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            min_x = center_x - new_width / 2
            max_x = center_x + new_width / 2
            min_y = center_y - new_height / 2
            max_y = center_y + new_height / 2
        elif trigger == "pan-left-btn":
            shift = width * 0.2
            min_x -= shift
            max_x -= shift
        elif trigger == "pan-right-btn":
            shift = width * 0.2
            min_x += shift
            max_x += shift
        elif trigger == "pan-up-btn":
            shift = height * 0.2
            min_y += shift
            max_y += shift
        elif trigger == "pan-down-btn":
            shift = height * 0.2
            min_y -= shift
            max_y -= shift
        return {"x": [min_x, max_x], "y": [min_y, max_y]}
