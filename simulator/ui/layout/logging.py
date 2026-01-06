from __future__ import annotations

from dash import dcc, html

from simulator.ui.layout.progress import build_progress_tab
from simulator.ui.layout.step_details import build_step_details_tab
from simulator.ui.layout.timing import build_timing_tab


def build_logging_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[
            dcc.Tabs(
                id="log-tabs",
                value="log-subtab",
                style={"borderBottom": "1px solid #dee2e6"},
                children=[
                    dcc.Tab(
                        label="📋 Log",
                        value="log-subtab",
                        children=[_build_log_panel()],
                    ),
                    dcc.Tab(
                        label="🚦 Progress",
                        value="progress-subtab",
                        children=[build_progress_tab()],
                    ),
                    dcc.Tab(
                        label="⏱️ Time",
                        value="timing-subtab",
                        children=[build_timing_tab()],
                    ),
                    dcc.Tab(
                        label="📊 Steps",
                        value="steps-subtab",
                        children=[build_step_details_tab()],
                    ),
                ],
            )
        ],
    )


def _build_log_panel() -> html.Div:
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
