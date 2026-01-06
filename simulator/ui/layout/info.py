from __future__ import annotations

from dash import html


def build_info_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "12px"},
        children=[
            html.H4("Selected Agent"),
            html.Div(id="agent-detail"),
            html.H4("Accident Details"),
            html.Div(id="accident-detail", children="Click an accident to see details."),
        ],
    )
