from __future__ import annotations

from dash import dcc, html


def build_logging_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[
            html.H4("Simulation Log"),
            html.Div(
                style={"display": "flex", "gap": "8px", "marginBottom": "8px"},
                children=[
                    html.Button("Clear Log", id="clear-log-btn"),
                    dcc.Checklist(
                        id="log-filter",
                        options=[
                            {"label": "Steps", "value": "step"},
                            {"label": "Errors", "value": "error"},
                            {"label": "Accidents", "value": "accident"},
                        ],
                        value=["step", "error", "accident"],
                        inline=True,
                        labelStyle={"marginRight": "12px"},
                    ),
                ],
            ),
            html.Div(
                id="log-output",
                style={
                    "height": "400px",
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
