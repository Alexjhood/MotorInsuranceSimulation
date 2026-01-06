from __future__ import annotations

from dash import html


def build_summary_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "12px"},
        children=[
            html.H4("Simulation Summary"),
            html.Div(
                "Selecting Summary pauses the simulation and rolls up metrics for the run so far.",
                style={"color": "#666", "fontSize": "12px"},
            ),
            html.Div(id="summary-content"),
        ],
    )
