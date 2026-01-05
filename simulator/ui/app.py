from __future__ import annotations

from dataclasses import asdict
import json
import math
import random
from typing import List, Tuple

import dash
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go

from simulator.accidents.model import AccidentEvent
from simulator.config import DriverConfig, MapConfig, SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.reporting.summary import summarize_run


def build_map_figure(
    simulation: Simulation,
    accidents: List[dict],
    selected_agent: int | None = None,
    label_options: List[str] | None = None,
    view_bounds: tuple[float, float, float, float] | None = None,
) -> go.Figure:
    map_data = simulation.map_data
    edge_lookup = {(edge.start, edge.end): edge for edge in map_data.edges}
    edge_styles = {
        "single_lane": {"color": "#c0c4cc", "width": 1.4},
        "dual_carriageway": {"color": "#9aa0a6", "width": 2.2},
        "highway": {"color": "#5f6368", "width": 2.6},
    }
    edge_coords = {key: {"x": [], "y": []} for key in edge_styles}
    for edge in map_data.edges:
        start = map_data.nodes[edge.start]
        end = map_data.nodes[edge.end]
        coords = edge_coords.get(edge.road_type, edge_coords["single_lane"])
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.hypot(dx, dy) or 1.0
        perp_x = -dy / length
        perp_y = dx / length
        lane_offsets = _lane_offsets(edge.lanes)
        for offset in lane_offsets:
            coords["x"] += [start.x + perp_x * offset, end.x + perp_x * offset, None]
            coords["y"] += [start.y + perp_y * offset, end.y + perp_y * offset, None]
        if edge.lanes <= 1:
            coords["x"] += [start.x, end.x, None]
            coords["y"] += [start.y, end.y, None]

    nodes_by_kind: dict[str, list[tuple[float, float]]] = {}
    poi_offset = {
        "residence": (-0.3, 0.35),
        "work": (0.3, 0.35),
        "commerce": (0.35, -0.3),
        "leisure": (-0.35, -0.3),
    }
    for node in map_data.nodes.values():
        x, y = node.x, node.y
        if node.kind in poi_offset:
            dx, dy = poi_offset[node.kind]
            x += dx
            y += dy
        nodes_by_kind.setdefault(node.kind, []).append((x, y))

    label_options = set(label_options or [])
    show_agent_labels = "agents" in label_options
    show_destination_labels = "destinations" in label_options
    show_poi_labels = "pois" in label_options
    show_accident_labels = "accidents" in label_options

    agent_x = []
    agent_y = []
    agent_angles = []
    agent_labels = []
    agent_customdata = []
    cyclist_x = []
    cyclist_y = []
    cyclist_angles = []
    cyclist_labels = []
    cyclist_customdata = []
    for agent in simulation.agents.values():
        node = map_data.nodes[agent.current_node]
        offset_x, offset_y, angle = _agent_position_offset(
            map_data,
            edge_lookup,
            agent.previous_node,
            agent.current_node,
            agent.heading,
            agent.lane_index,
        )
        x = node.x + offset_x
        y = node.y + offset_y
        label = f"A{agent.agent_id}" if show_agent_labels else ""
        custom = {
            "type": "agent",
            "agent_id": agent.agent_id,
            "agent_kind": agent.agent_type,
            "lane": agent.lane_index + 1,
        }
        if agent.agent_type == "cyclist":
            cyclist_x.append(x)
            cyclist_y.append(y)
            cyclist_angles.append(angle)
            cyclist_labels.append(label)
            cyclist_customdata.append(custom)
        else:
            agent_x.append(x)
            agent_y.append(y)
            agent_angles.append(angle)
            agent_labels.append(label)
            agent_customdata.append(custom)

    accident_x = []
    accident_y = []
    accident_customdata = []
    accident_labels = []
    destination_x = []
    destination_y = []
    destination_labels = []
    for agent in simulation.agents.values():
        destination_node = map_data.nodes[agent.destination_node]
        destination_x.append(destination_node.x)
        destination_y.append(destination_node.y)
        destination_labels.append(f"D{agent.agent_id}" if show_destination_labels else "")

    for accident in accidents:
        node = map_data.nodes[accident["location"]]
        accident_x.append(node.x)
        accident_y.append(node.y)
        accident_customdata.append({"type": "accident", **accident})
        accident_labels.append(
            f"Accident (Severity: {accident['severity']})" if show_accident_labels else ""
        )

    fig = go.Figure()
    for road_type, style in edge_styles.items():
        coords = edge_coords[road_type]
        fig.add_trace(
            go.Scatter(
                x=coords["x"],
                y=coords["y"],
                mode="lines",
                line=dict(color=style["color"], width=style["width"]),
                name=road_type.replace("_", " "),
                hoverinfo="skip",
            )
        )

    if destination_x:
        fig.add_trace(
            go.Scatter(
                x=destination_x,
                y=destination_y,
                mode="markers+text" if show_destination_labels else "markers",
                marker=dict(size=8, color="#ff6f61", symbol="circle-open"),
                text=destination_labels,
                textposition="bottom center",
                name="destinations",
                hoverinfo="skip",
            )
        )

    node_styles = {
        "major_junction": {
            "color": "#495057",
            "size": 10,
            "symbol": "circle",
            "line": {"width": 2, "color": "#343a40"},
        },
        "minor_junction": {"color": "#c2c5cc", "size": 4, "symbol": "circle"},
        "roundabout": {
            "color": "#8d99ae",
            "size": 12,
            "symbol": "circle-open-dot",
            "line": {"width": 2, "color": "#6c757d"},
        },
        "residence": {"color": "#1f77b4", "size": 8, "symbol": "square"},
        "work": {"color": "#9467bd", "size": 8, "symbol": "diamond"},
        "commerce": {"color": "#ff7f0e", "size": 8, "symbol": "star"},
        "leisure": {"color": "#e377c2", "size": 8, "symbol": "hexagon"},
        "crossing": {"color": "#f1c40f", "size": 6, "symbol": "square-open"},
        "cyclist": {"color": "#2ca02c", "size": 6, "symbol": "triangle-up"},
    }
    poi_styles = {
        "residence": {"color": "#1f77b4", "size": 6, "symbol": "square"},
        "work": {"color": "#9467bd", "size": 6, "symbol": "diamond"},
        "commerce": {"color": "#ff7f0e", "size": 6, "symbol": "star"},
        "leisure": {"color": "#e377c2", "size": 6, "symbol": "hexagon"},
        "crossing": {"color": "#f1c40f", "size": 6, "symbol": "square-open"},
        "cyclist": {"color": "#2ca02c", "size": 6, "symbol": "triangle-up"},
    }
    poi_labels = {"residence": "🏠", "work": "🏢", "commerce": "🛍️", "leisure": "🎯"}
    for kind, points in nodes_by_kind.items():
        style = node_styles.get(kind, node_styles["minor_junction"])
        mode = "markers+text" if show_poi_labels else "markers"
        marker = dict(size=style["size"], color=style["color"], symbol=style["symbol"])
        if style.get("line"):
            marker["line"] = style["line"]
        fig.add_trace(
            go.Scatter(
                x=[point[0] for point in points],
                y=[point[1] for point in points],
                mode=mode,
                marker=marker,
                text=[poi_labels.get(kind, "") if show_poi_labels else "" for _ in points],
                textposition="top center",
                name=kind.replace("_", " "),
            )
        )

    fig.add_trace(
        go.Scatter(
            x=agent_x,
            y=agent_y,
            mode="markers+text" if show_agent_labels else "markers",
            marker=dict(
                size=10,
                color="#d62728",
                line=dict(width=1, color="#a92122"),
                symbol="triangle-up",
                angle=agent_angles,
            ),
            text=agent_labels,
            textposition="top center",
            customdata=agent_customdata,
            name="agents",
            hovertemplate="Agent %{customdata[agent_id]} (lane %{customdata[lane]})<extra></extra>",
        )
    )
    if cyclist_x:
        fig.add_trace(
            go.Scatter(
                x=cyclist_x,
                y=cyclist_y,
                mode="markers+text" if show_agent_labels else "markers",
                marker=dict(
                    size=10,
                    color="#2ca02c",
                    line=dict(width=1, color="#1f7a1f"),
                    symbol="triangle-up",
                    angle=cyclist_angles,
                ),
                text=cyclist_labels,
                textposition="top center",
                customdata=cyclist_customdata,
                name="cyclists",
                hovertemplate="Cyclist %{customdata[agent_id]} (lane %{customdata[lane]})<extra></extra>",
            )
        )
    if selected_agent is not None and selected_agent in simulation.agents:
        agent = simulation.agents[selected_agent]
        route_nodes = agent.route[agent.route_index :]
        if len(route_nodes) >= 2:
            route_x = [map_data.nodes[node_id].x for node_id in route_nodes]
            route_y = [map_data.nodes[node_id].y for node_id in route_nodes]
            fig.add_trace(
                go.Scatter(
                    x=route_x,
                    y=route_y,
                    mode="lines",
                    line=dict(color="#ff6f61", width=3),
                    name="selected route",
                )
            )
    if accident_x:
        fig.add_trace(
            go.Scatter(
                x=accident_x,
                y=accident_y,
                mode="markers+text" if show_accident_labels else "markers",
                marker=dict(size=14, color="#d62728", symbol="x"),
                name="accidents",
                customdata=accident_customdata,
                text=accident_labels,
                hovertemplate="%{text}<extra></extra>",
            )
        )
    min_x, max_x, min_y, max_y = view_bounds or _map_bounds(map_data)
    fig.update_layout(
        height=640,
        width=920,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(showgrid=False, zeroline=False, range=[min_x, max_x], fixedrange=False),
        yaxis=dict(showgrid=False, zeroline=False, range=[min_y, max_y], fixedrange=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        dragmode="pan",
        uirevision="map",
    )
    return fig


def create_app() -> Dash:
    app = Dash(__name__)
    app.title = "Motor Insurance Simulation"

    app.layout = html.Div(
        style={"fontFamily": "Arial", "display": "flex", "gap": "24px"},
        children=[
            html.Div(
                style={"width": "360px", "flexShrink": "0"},
                children=[
                    html.H2("Simulation Control"),
                    dcc.Tabs(
                        id="control-tabs",
                        value="setup-tab",
                        children=[
                            dcc.Tab(
                                label="Set-up",
                                value="setup-tab",
                                children=[
                                    html.Div(
                                        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                                        children=[
                                            html.Label("Seed"),
                                            html.Div(
                                                style={
                                                    "display": "flex",
                                                    "gap": "8px",
                                                    "alignItems": "center",
                                                },
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
                                            html.Label("Driver Agents"),
                                            dcc.Input(
                                                id="agent-count",
                                                type="number",
                                                value=20,
                                                min=1,
                                                max=200,
                                                step=1,
                                            ),
                                            html.Label("Cyclists"),
                                            dcc.Input(
                                                id="cyclist-count",
                                                type="number",
                                                value=6,
                                                min=0,
                                                max=200,
                                                step=1,
                                            ),
                                            html.Label("Map Scale"),
                                            dcc.Input(
                                                id="map-scale-input",
                                                type="number",
                                                min=50,
                                                max=10000,
                                                value=100,
                                                step=50,
                                                style={"width": "100%"}
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
                                ],
                            ),
                            dcc.Tab(
                                label="Running",
                                value="running-tab",
                                children=[
                                    html.Div(
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
                                            html.H4("Selection Details"),
                                            html.Div(
                                                id="running-selection-detail",
                                                children="Click an agent or accident for details.",
                                            ),
                                        ],
                                    )
                                ],
                            ),
                            dcc.Tab(
                                label="Information",
                                value="info-tab",
                                children=[
                                    html.Div(
                                        style={"display": "flex", "flexDirection": "column", "gap": "12px"},
                                        children=[
                                            html.H4("Summary"),
                                            html.Pre(id="summary-output", style={"whiteSpace": "pre-wrap"}),
                                            html.H4("Selected Agent"),
                                            html.Div(id="agent-detail"),
                                            html.H4("Accident Details"),
                                            html.Div(id="accident-detail", children="Click an accident to see details."),
                                        ],
                                    )
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                style={"flex": "1"},
                children=[
                    dcc.Graph(
                        id="sim-graph",
                        config={"scrollZoom": True, "displayModeBar": True},
                        style={"height": "640px", "width": "920px"},
                    ),
                    dcc.Interval(id="tick", interval=600, n_intervals=0, disabled=True),
                    dcc.Store(id="sim-state"),
                    dcc.Store(id="accident-store", data=[]),
                    dcc.Store(id="selected-agent"),
                    dcc.Store(id="selected-item"),
                    dcc.Store(id="view-store"),
                    dcc.Store(id="history-store", data=[]),
                    dcc.Store(id="history-index", data=0),
                ],
            ),
        ],
    )

    @app.callback(
        Output("sim-state", "data"),
        Output("accident-store", "data"),
        Output("history-store", "data"),
        Output("history-index", "data"),
        Output("tick", "disabled"),
        Input("start-btn", "n_clicks"),
        Input("pause-btn", "n_clicks"),
        Input("reset-btn", "n_clicks"),
        Input("setup-reset-btn", "n_clicks"),
        State("seed-input", "value"),
        State("agent-count", "value"),
        State("cyclist-count", "value"),
        State("map-scale-input", "value"),
        State("cluster-lambda", "value"),
        State("homes-lambda", "value"),
        State("other-locations-lambda", "value"),
        State("cluster-spacing", "value"),
        State("dual-road-chance", "value"),
        State("roundabout-chance", "value"),
        State("highway-roundabout-chance", "value"),
        State("major-junction-ratio", "value"),
        State("sim-state", "data"),
        prevent_initial_call=True,
    )
    def control_simulation(
        start,
        pause,
        reset,
        setup_reset,
        seed,
        agent_count,
        cyclist_count,
        map_scale,
        cluster_lambda,
        homes_lambda,
        other_locations_lambda,
        cluster_spacing,
        dual_road_chance,
        roundabout_chance,
        highway_roundabout_chance,
        major_junction_ratio,
        state,
    ):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if state is None:
            config = _config_from_inputs(
                seed,
                agent_count,
                cyclist_count,
                map_scale,
                cluster_lambda,
                homes_lambda,
                other_locations_lambda,
                cluster_spacing,
                dual_road_chance,
                roundabout_chance,
                highway_roundabout_chance,
                major_junction_ratio,
            )
            sim = Simulation(config)
            new_state = _serialize_sim(sim)
            history = [{"state": new_state, "accidents": []}]
            disabled = False if trigger == "start-btn" else True
            return new_state, [], history, 0, disabled
        if trigger == "pause-btn":
            return state, dash.no_update, dash.no_update, dash.no_update, True
        if trigger in {"reset-btn", "setup-reset-btn"}:
            config = _config_from_inputs(
                seed,
                agent_count,
                cyclist_count,
                map_scale,
                cluster_lambda,
                homes_lambda,
                other_locations_lambda,
                cluster_spacing,
                dual_road_chance,
                roundabout_chance,
                highway_roundabout_chance,
                major_junction_ratio,
            )
            sim = Simulation(config)
            new_state = _serialize_sim(sim)
            history = [{"state": new_state, "accidents": []}]
            return new_state, [], history, 0, True
        if trigger == "start-btn":
            return state, dash.no_update, dash.no_update, dash.no_update, False
        return state, dash.no_update, dash.no_update, dash.no_update, False

    @app.callback(
        Output("tick", "interval"),
        Input("speed-control", "value"),
    )
    def update_tick_interval(speed: float) -> int:
        return max(int(1000 / max(speed or 1, 0.5)), 100)

    @app.callback(
        Output("seed-input", "value"),
        Input("seed-random-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def randomize_seed(_):
        return random.randint(1, 9999)

    @app.callback(
        Output("sim-state", "data", allow_duplicate=True),
        Output("accident-store", "data", allow_duplicate=True),
        Output("history-store", "data", allow_duplicate=True),
        Output("history-index", "data", allow_duplicate=True),
        Input("tick", "n_intervals"),
        Input("step-btn", "n_clicks"),
        Input("back-btn", "n_clicks"),
        State("sim-state", "data"),
        State("accident-store", "data"),
        State("history-store", "data"),
        State("history-index", "data"),
        prevent_initial_call=True,
    )
    def advance_simulation(_, __, ___, state, accidents, history, history_index):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            state = _serialize_sim(simulation)
        history = history or [{"state": state, "accidents": accidents or []}]
        history_index = 0 if history_index is None else history_index
        if trigger == "back-btn":
            if history_index > 0:
                history_index -= 1
                entry = history[history_index]
                return entry["state"], entry["accidents"], history, history_index
            return state, accidents, history, history_index
        simulation = _deserialize_sim(state)
        result = simulation.step()
        accidents = [
            {
                "step": accident.step,
                "location": accident.location,
                "severity": accident.severity,
                "total_claim": accident.total_claim,
                "participants": accident.participants,
            }
            for accident in result.accidents
        ]
        new_state = _serialize_sim(simulation)
        if history_index < len(history) - 1:
            history = history[: history_index + 1]
        history.append({"state": new_state, "accidents": accidents})
        history_index += 1
        return new_state, accidents, history, history_index

    @app.callback(
        Output("sim-graph", "figure"),
        Output("summary-output", "children"),
        Input("sim-state", "data"),
        Input("accident-store", "data"),
        Input("selected-agent", "data"),
        Input("label-options", "value"),
        Input("view-store", "data"),
    )
    def render_simulation(state, accidents, selected_agent, label_options, view_store):
        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            summary = summarize_run(simulation)
            figure = build_map_figure(simulation, accidents or [], selected_agent, label_options)
            return figure, json.dumps(summary, indent=2)
        simulation = _deserialize_sim(state)
        summary = summarize_run(simulation)
        view_bounds = None
        if view_store:
            view_bounds = (
                view_store["x"][0],
                view_store["x"][1],
                view_store["y"][0],
                view_store["y"][1],
            )
        figure = build_map_figure(
            simulation,
            accidents or [],
            selected_agent,
            label_options,
            view_bounds=view_bounds,
        )
        return figure, json.dumps(summary, indent=2)

    @app.callback(
        Output("selected-agent", "data"),
        Output("selected-item", "data"),
        Output("accident-detail", "children"),
        Input("sim-graph", "clickData"),
        State("selected-agent", "data"),
    )
    def handle_click(click_data, selected_agent):
        if not click_data:
            return dash.no_update, dash.no_update, dash.no_update
        point = click_data.get("points", [{}])[0]
        custom = point.get("customdata") or {}
        if custom.get("type") == "agent":
            return custom.get("agent_id"), {"type": "agent", "agent_id": custom.get("agent_id")}, dash.no_update
        if custom.get("type") == "accident":
            detail = html.Ul(
                [
                    html.Li(f"Step: {custom.get('step')}"),
                    html.Li(f"Location: {custom.get('location')}"),
                    html.Li(f"Severity: {custom.get('severity')}"),
                    html.Li(f"Participants: {custom.get('participants')}"),
                    html.Li(f"Total claim: {custom.get('total_claim'):.2f}"),
                ]
            )
            return dash.no_update, {"type": "accident", **custom}, detail
        return dash.no_update, dash.no_update, dash.no_update

    @app.callback(
        Output("agent-detail", "children"),
        Input("selected-agent", "data"),
        State("sim-state", "data"),
    )
    def render_agent_detail(agent_id, state):
        if agent_id is None or state is None:
            return "Click a vehicle to see its route and details."
        simulation = _deserialize_sim(state)
        agent = simulation.agents.get(agent_id)
        if agent is None:
            return "Agent not found."
        items = [
            html.Li(f"Agent #{agent.agent_id}"),
            html.Li(f"Type: {agent.agent_type}"),
            html.Li(f"Risk profile: {agent.driver.risk_level}"),
            html.Li(f"Vehicle: {agent.vehicle.class_name}"),
            html.Li(f"Home node: {agent.home_node}"),
            html.Li(f"Work node: {agent.work_node}"),
            html.Li(f"Destination: {agent.destination_node}"),
        ]
        if agent.agent_type == "cyclist":
            items.append(html.Li(f"Cyclist journey: {agent.home_node} ➜ {agent.destination_node}"))
            items.append(html.Li(f"Remaining route: {agent.route[agent.route_index:]}"))
        detail = html.Ul(items)
        return detail

    @app.callback(
        Output("running-selection-detail", "children"),
        Input("selected-item", "data"),
        State("sim-state", "data"),
    )
    def render_running_detail(selected_item, state):
        if not selected_item:
            return "Click an agent or accident for details."
        if selected_item.get("type") == "accident":
            return html.Ul(
                [
                    html.Li(f"Step: {selected_item.get('step')}"),
                    html.Li(f"Location: {selected_item.get('location')}"),
                    html.Li(f"Severity: {selected_item.get('severity')}"),
                    html.Li(f"Participants: {selected_item.get('participants')}"),
                    html.Li(f"Total claim: {selected_item.get('total_claim'):.2f}"),
                ]
            )
        if selected_item.get("type") == "agent":
            if state is None:
                return "No simulation data available."
            simulation = _deserialize_sim(state)
            agent = simulation.agents.get(selected_item.get("agent_id"))
            if agent is None:
                return "Agent not found."
            items = [
                html.Li(f"Agent #{agent.agent_id}"),
                html.Li(f"Type: {agent.agent_type}"),
                html.Li(f"Lane: {agent.lane_index + 1}"),
                html.Li(f"Destination: {agent.destination_node}"),
            ]
            if agent.agent_type == "cyclist":
                items.append(html.Li(f"Cyclist journey: {agent.home_node} ➜ {agent.destination_node}"))
            return html.Ul(items)
        return "Click an agent or accident for details."

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
            simulation = _deserialize_sim(state)
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

    return app


def _config_from_inputs(
    seed: int,
    agent_count: int,
    cyclist_count: int,
    map_scale: float,
    cluster_lambda: float,
    homes_lambda: float,
    other_locations_lambda: float,
    cluster_spacing: float,
    dual_road_chance: float,
    roundabout_chance: float,
    highway_roundabout_chance: float,
    major_junction_ratio: float,
) -> SimulationConfig:
    map_config = MapConfig(
        cluster_lambda=cluster_lambda if cluster_lambda is not None else 1.0,
        homes_per_cluster_lambda=homes_lambda if homes_lambda is not None else 4.0,
        other_locations_per_cluster_lambda=other_locations_lambda if other_locations_lambda is not None else 4.0,
        map_scale=map_scale if map_scale is not None else 100.0,
        min_cluster_spacing=cluster_spacing if cluster_spacing is not None else 40.0,
        intra_cluster_dual_road_chance=dual_road_chance if dual_road_chance is not None else 0.3,
        intra_cluster_roundabout_chance=roundabout_chance if roundabout_chance is not None else 0.15,
        highway_merge_roundabout_chance=highway_roundabout_chance if highway_roundabout_chance is not None else 0.4,
        major_junction_ratio=major_junction_ratio if major_junction_ratio is not None else 0.14,
    )
    driver_config = DriverConfig(count=agent_count or 20, cyclist_count=cyclist_count or 0)
    return SimulationConfig(seed=seed or 42, map_config=map_config, driver_config=driver_config)


def _serialize_sim(simulation: Simulation) -> dict:
    agents = []
    for agent in simulation.agents.values():
        agents.append(
            {
                "agent_id": agent.agent_id,
                "current_node": agent.current_node,
                "route": agent.route,
                "route_index": agent.route_index,
                "driver": asdict(agent.driver),
                "vehicle": asdict(agent.vehicle),
                "home_node": agent.home_node,
                "work_node": agent.work_node,
                "destination_node": agent.destination_node,
                "previous_node": agent.previous_node,
                "agent_type": agent.agent_type,
                "heading": list(agent.heading) if agent.heading else None,
                "lane_index": agent.lane_index,
                "wait_steps": agent.wait_steps,
            }
        )
    return {
        "config": asdict(simulation.config),
        "map_data": {
            "nodes": {nid: asdict(node) for nid, node in simulation.map_data.nodes.items()},
            "edges": [asdict(edge) for edge in simulation.map_data.edges],
            "adjacency": simulation.map_data.adjacency,
            "pois": simulation.map_data.pois,
        },
        "step_index": simulation.step_index,
        "agents": agents,
        "accidents": [accident.__dict__ for accident in simulation.accidents],
    }


def _deserialize_sim(state: dict) -> Simulation:
    config_data = state["config"]
    config = SimulationConfig(
        seed=config_data["seed"],
        steps=config_data["steps"],
        map_config=MapConfig(**config_data["map_config"]),
        driver_config=DriverConfig(**config_data["driver_config"]),
        time_of_day=config_data.get("time_of_day", "day"),
        enable_parallel=config_data.get("enable_parallel", False),
        parallel_workers=config_data.get("parallel_workers", 2),
    )
    simulation = Simulation(config)
    simulation.step_index = state["step_index"]
    simulation.accidents = [AccidentEvent(**accident) for accident in state.get("accidents", [])]
    for agent in state["agents"]:
        sim_agent = simulation.agents[agent["agent_id"]]
        sim_agent.current_node = agent["current_node"]
        sim_agent.route = agent["route"]
        sim_agent.route_index = agent["route_index"]
        sim_agent.destination_node = agent.get("destination_node", sim_agent.work_node)
        sim_agent.previous_node = agent.get("previous_node", sim_agent.current_node)
        sim_agent.agent_type = agent.get("agent_type", sim_agent.agent_type)
        heading = agent.get("heading")
        sim_agent.heading = tuple(heading) if heading else None
        sim_agent.lane_index = agent.get("lane_index", 0)
        sim_agent.wait_steps = agent.get("wait_steps", 0)
    return simulation


def _lane_offsets(lanes: int) -> List[float]:
    if lanes <= 1:
        return [0.0]
    if lanes == 2:
        return [-0.08, 0.08]
    if lanes == 3:
        return [-0.12, 0.0, 0.12]
    return [-0.18, -0.06, 0.06, 0.18]


def _agent_position_offset(
    map_data,
    edge_lookup,
    previous_node: int,
    current_node: int,
    heading: Tuple[int, int] | None,
    lane_index: int,
) -> Tuple[float, float, float]:
    edge = edge_lookup.get((previous_node, current_node))
    if edge is None and heading:
        edge = _edge_from_heading(map_data, edge_lookup, current_node, heading)
    if edge is None:
        angle = _heading_angle(heading) if heading else 0.0
        return 0.0, 0.0, angle
    start = map_data.nodes[edge.start]
    end = map_data.nodes[edge.end]
    dx = end.x - start.x
    dy = end.y - start.y
    length = math.hypot(dx, dy) or 1.0
    perp_x = -dy / length
    perp_y = dx / length
    offsets = _lane_offsets(edge.lanes)
    offset = offsets[min(lane_index, len(offsets) - 1)]
    angle = _heading_angle((dx, dy))
    return perp_x * offset, perp_y * offset, angle


def _edge_from_heading(map_data, edge_lookup, current_node: int, heading: Tuple[int, int]) -> "Edge | None":
    node = map_data.nodes[current_node]
    target_x = node.x + heading[0]
    target_y = node.y + heading[1]
    for edge in map_data.edges:
        if edge.start == current_node:
            neighbor = map_data.nodes[edge.end]
            if neighbor.x == target_x and neighbor.y == target_y:
                return edge
    return None


def _map_bounds(map_data) -> Tuple[float, float, float, float]:
    xs = [node.x for node in map_data.nodes.values()]
    ys = [node.y for node in map_data.nodes.values()]
    padding = 1.5
    return min(xs) - padding, max(xs) + padding, min(ys) - padding, max(ys) + padding


def _heading_angle(heading: Tuple[int, int] | None) -> float:
    if not heading:
        return 0.0
    dx, dy = heading
    angle = math.degrees(math.atan2(dy, dx))
    return angle - 90.0


def _agent_heading(start, end) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    angle = math.degrees(math.atan2(dy, dx))
    return angle - 90.0


if __name__ == "__main__":
    app = create_app()
    app.run_server(debug=True)
