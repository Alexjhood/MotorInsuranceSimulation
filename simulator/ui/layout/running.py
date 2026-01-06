from __future__ import annotations

from dash import dcc, html


def build_running_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[
            html.Label("View Controls"),
            html.Div(
                style={
                    "display": "flex",
                    "gap": "16px",
                    "alignItems": "center",
                    "flexWrap": "wrap",
                },
                children=[
                    html.Div(
                        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                        children=[
                            html.Button("＋", id="zoom-in-btn", title="Zoom in"),
                            html.Button("－", id="zoom-out-btn", title="Zoom out"),
                        ],
                    ),
                    html.Div(
                        style={
                            "display": "flex",
                            "flexDirection": "column",
                            "alignItems": "center",
                            "gap": "6px",
                        },
                        children=[
                            html.Button("⬆️", id="pan-up-btn", title="Pan up"),
                            html.Div(
                                style={"display": "flex", "gap": "6px"},
                                children=[
                                    html.Button("⬅️", id="pan-left-btn", title="Pan left"),
                                    html.Button("↺", id="reset-view-btn", title="Reset view"),
                                    html.Button("➡️", id="pan-right-btn", title="Pan right"),
                                ],
                            ),
                            html.Button("⬇️", id="pan-down-btn", title="Pan down"),
                        ],
                    ),
                ],
            ),
            html.Hr(),
            html.Label("Element Size Controls"),
            html.Div(
                style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                children=[
                    html.Label("Agents / Cyclists Size", style={"fontSize": "12px"}),
                    dcc.Slider(
                        id="agent-size-slider",
                        min=0.5,
                        max=3.0,
                        step=0.25,
                        value=1.0,
                        marks={0.5: "0.5x", 1: "1x", 2: "2x", 3: "3x"},
                    ),
                    html.Label("Other Elements Size (nodes, accidents)", style={"fontSize": "12px"}),
                    dcc.Slider(
                        id="other-size-slider",
                        min=0.5,
                        max=3.0,
                        step=0.25,
                        value=1.0,
                        marks={0.5: "0.5x", 1: "1x", 2: "2x", 3: "3x"},
                    ),
                ],
            ),
            html.Label("Playback Speed (steps/sec)"),
            dcc.Slider(
                id="speed-control",
                min=0.5,
                max=5,
                step=0.5,
                value=1,
                marks={0.5: "0.5x", 1: "1x", 2: "2x", 3: "3x", 4: "4x", 5: "5x"},
            ),
            html.Div(style={"height": "8px"}),
            html.Div(
                children=[
                    html.Button("Start", id="start-btn"),
                    html.Button("Pause", id="pause-btn", style={"marginLeft": "8px"}),
                    html.Button("Back", id="back-btn", style={"marginLeft": "8px"}),
                    html.Button("Step", id="step-btn", style={"marginLeft": "8px"}),
                    html.Button("Reset", id="reset-btn", style={"marginLeft": "8px"}),
                ]
            ),
            html.Label("Labels"),
            dcc.Checklist(
                id="label-options",
                options=[
                    {"label": "Agent IDs", "value": "agents"},
                    {"label": "Destination IDs", "value": "destinations"},
                    {"label": "POI Icons", "value": "pois"},
                    {"label": "Accident Labels", "value": "accidents"},
                ],
                value=["agents"],
                labelStyle={"display": "block"},
            ),
            html.Hr(),
            html.Label("Display Options"),
            dcc.Checklist(
                id="visualization-toggle",
                options=[
                    {"label": "Show Map Visualization", "value": "show_viz"},
                ],
                value=["show_viz"],
            ),
            html.Hr(),
            html.H4("Selection Details"),
            html.Div(
                id="running-selection-detail",
                children="Click an agent or accident for details.",
            ),
        ],
    )
