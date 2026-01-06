from __future__ import annotations

import dash
from dash.dependencies import Input, Output

from simulator.ui.utils import format_probability_tooltip, linear_to_log


def register_probability_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("journey-start-prob-display", "children"),
        Input("journey-start-prob", "value"),
    )
    def update_journey_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.05, 0.0001, 1.0)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 1.0)}"

    @app.callback(
        Output("cyclist-journey-start-prob-display", "children"),
        Input("cyclist-journey-start-prob", "value"),
    )
    def update_cyclist_journey_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.01, 0.0001, 1.0)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 1.0)}"

    @app.callback(
        Output("unilateral-prob-display", "children"),
        Input("unilateral-prob", "value"),
    )
    def update_unilateral_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.01, 0.0001, 0.1)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 0.1)}"

    @app.callback(
        Output("vehicle-encounter-prob-display", "children"),
        Input("vehicle-encounter-prob", "value"),
    )
    def update_vehicle_encounter_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.03, 0.0001, 0.1)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 0.1)}"

    @app.callback(
        Output("cyclist-encounter-prob-display", "children"),
        Input("cyclist-encounter-prob", "value"),
    )
    def update_cyclist_encounter_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.03, 0.0001, 0.1)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 0.1)}"
