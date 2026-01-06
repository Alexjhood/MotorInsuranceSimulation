from __future__ import annotations

from dash import dcc, html

from simulator.ui.utils import linear_to_log


def build_setup_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[
            html.Label("Seed"),
            html.Div(
                style={"display": "flex", "gap": "8px", "alignItems": "center"},
                children=[
                    dcc.Input(
                        id="seed-input",
                        type="number",
                        value=42,
                        style={"flex": "1"},
                    ),
                    html.Button(
                        "Randomize",
                        id="seed-random-btn",
                        title="Generate a random seed",
                    ),
                ],
            ),
            html.Label("Map Scale"),
            dcc.Input(
                id="map-scale-input",
                type="number",
                min=50,
                max=10000,
                value=100,
                step=50,
                style={"width": "100%"},
            ),
            html.Label("Cluster λ (expected # of clusters)"),
            dcc.Slider(
                id="cluster-lambda",
                min=0.5,
                max=20.0,
                step=0.5,
                value=1.0,
                marks={0.5: "0.5", 5: "5", 10: "10", 15: "15", 20: "20"},
            ),
            html.Label("Homes per Cluster λ"),
            dcc.Slider(
                id="homes-lambda",
                min=1.0,
                max=100.0,
                step=0.5,
                value=4.0,
                marks={1: "1", 25: "25", 50: "50", 75: "75", 100: "100"},
            ),
            html.Label("Other Locations per Cluster λ"),
            dcc.Slider(
                id="other-locations-lambda",
                min=0.0,
                max=100.0,
                step=0.5,
                value=4.0,
                marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
            ),
            html.Label("Cluster Spacing"),
            dcc.Slider(
                id="cluster-spacing",
                min=20.0,
                max=80.0,
                step=5.0,
                value=40.0,
                marks={20: "20", 40: "40", 60: "60", 80: "80"},
            ),
            html.Label("Intra-cluster Dual Road Chance"),
            dcc.Slider(
                id="dual-road-chance",
                min=0.0,
                max=0.8,
                step=0.05,
                value=0.3,
                marks={0.0: "0%", 0.4: "40%", 0.8: "80%"},
            ),
            html.Label("Intra-cluster Roundabout Chance"),
            dcc.Slider(
                id="roundabout-chance",
                min=0.0,
                max=0.5,
                step=0.05,
                value=0.15,
                marks={0.0: "0%", 0.25: "25%", 0.5: "50%"},
            ),
            html.Label("Highway Merge Roundabout Chance"),
            dcc.Slider(
                id="highway-roundabout-chance",
                min=0.0,
                max=0.8,
                step=0.05,
                value=0.4,
                marks={0.0: "0%", 0.4: "40%", 0.8: "80%"},
            ),
            html.Label("Major Junction Proportion"),
            dcc.Slider(
                id="major-junction-ratio",
                min=0.0,
                max=0.4,
                step=0.02,
                value=0.14,
                marks={0.0: "0%", 0.2: "20%", 0.4: "40%"},
            ),
            html.Hr(),
            html.H4("Journey & Accident Settings"),
            html.Label("Driver Journey Start Probability (per step when idle)"),
            html.Div(
                id="journey-start-prob-display",
                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"},
            ),
            dcc.Slider(
                id="journey-start-prob",
                min=0.0,
                max=1.0,
                step=0.01,
                value=linear_to_log(0.05, 0.0001, 1.0),
                marks={
                    0.0: "0.01%",
                    0.25: "0.1%",
                    0.5: "1%",
                    0.75: "10%",
                    1.0: "100%",
                },
            ),
            html.Label("Cyclist Journey Start Probability (per step when idle)"),
            html.Div(
                id="cyclist-journey-start-prob-display",
                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"},
            ),
            dcc.Slider(
                id="cyclist-journey-start-prob",
                min=0.0,
                max=1.0,
                step=0.01,
                value=linear_to_log(0.01, 0.0001, 1.0),
                marks={
                    0.0: "0.01%",
                    0.25: "0.1%",
                    0.5: "1%",
                    0.75: "10%",
                    1.0: "100%",
                },
            ),
            html.Label("Unilateral Accident Probability (per agent per step)"),
            html.Div(
                id="unilateral-prob-display",
                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"},
            ),
            dcc.Slider(
                id="unilateral-prob",
                min=0.0,
                max=1.0,
                step=0.01,
                value=linear_to_log(0.01, 0.0001, 0.1),
                marks={
                    0.0: "0.01%",
                    0.33: "0.1%",
                    0.67: "1%",
                    1.0: "10%",
                },
            ),
            html.Label("Vehicle Encounter Accident Probability"),
            html.Div(
                id="vehicle-encounter-prob-display",
                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"},
            ),
            dcc.Slider(
                id="vehicle-encounter-prob",
                min=0.0,
                max=1.0,
                step=0.01,
                value=linear_to_log(0.03, 0.0001, 0.1),
                marks={
                    0.0: "0.01%",
                    0.33: "0.1%",
                    0.67: "1%",
                    1.0: "10%",
                },
            ),
            html.Label("Cyclist Encounter Accident Probability"),
            html.Div(
                id="cyclist-encounter-prob-display",
                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"},
            ),
            dcc.Slider(
                id="cyclist-encounter-prob",
                min=0.0,
                max=1.0,
                step=0.01,
                value=linear_to_log(0.03, 0.0001, 0.1),
                marks={
                    0.0: "0.01%",
                    0.33: "0.1%",
                    0.67: "1%",
                    1.0: "10%",
                },
            ),
            html.Div(
                style={"display": "flex", "justifyContent": "flex-end"},
                children=[
                    html.Button(
                        "Reset Simulation",
                        id="setup-reset-btn",
                        style={"marginTop": "6px"},
                    )
                ],
            ),
        ],
    )
