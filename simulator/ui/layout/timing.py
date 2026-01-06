from __future__ import annotations

from dash import html


def build_timing_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[
            html.H4("Step Performance"),
            html.Div(
                style={"display": "flex", "gap": "8px", "marginBottom": "8px"},
                children=[
                    html.Button("Clear Timing Data", id="clear-timing-btn"),
                ],
            ),
            html.Div(
                id="timing-summary",
                style={"marginBottom": "12px"},
                children=[],
            ),
            html.H4("Recent Steps"),
            html.Div(
                id="timing-output",
                style={
                    "height": "350px",
                    "overflowY": "auto",
                    "border": "1px solid #ccc",
                    "padding": "8px",
                    "fontFamily": "monospace",
                    "fontSize": "12px",
                    "backgroundColor": "#f8f9fa",
                },
                children=[],
            ),
        ],
    )
