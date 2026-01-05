from __future__ import annotations

from dataclasses import asdict
import json
from typing import List

import dash
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go

from simulator.config import DriverConfig, MapConfig, SimulationConfig
from simulator.engine.simulation import Simulation
from simulator.reporting.summary import summarize_run


def build_map_figure(simulation: Simulation, accidents: List[dict]) -> go.Figure:
    map_data = simulation.map_data
    edge_styles = {
        "single_lane": {"color": "#c0c4cc", "width": 1.5},
        "two_lane": {"color": "#9aa0a6", "width": 2.5},
        "highway": {"color": "#5f6368", "width": 3.5},
    }
    edge_coords = {key: {"x": [], "y": []} for key in edge_styles}
    cycle_x: list[float] = []
    cycle_y: list[float] = []
    for edge in map_data.edges:
        start = map_data.nodes[edge.start]
        end = map_data.nodes[edge.end]
        coords = edge_coords.get(edge.road_type, edge_coords["single_lane"])
        coords["x"] += [start.x, end.x, None]
        coords["y"] += [start.y, end.y, None]
        if edge.has_cycle_lane:
            cycle_x += [start.x, end.x, None]
            cycle_y += [start.y, end.y, None]

    nodes_by_kind: dict[str, list[tuple[int, int]]] = {}
    for node in map_data.nodes.values():
        nodes_by_kind.setdefault(node.kind, []).append((node.x, node.y))

    agent_x = []
    agent_y = []
    for agent in simulation.agents.values():
        node = map_data.nodes[agent.current_node]
        agent_x.append(node.x)
        agent_y.append(node.y)

    accident_x = []
    accident_y = []
    for accident in accidents:
        node = map_data.nodes[accident["location"]]
        accident_x.append(node.x)
        accident_y.append(node.y)

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
    if cycle_x:
        fig.add_trace(
            go.Scatter(
                x=cycle_x,
                y=cycle_y,
                mode="lines",
                line=dict(color="#2ca02c", width=1.2, dash="dot"),
                name="cycle lanes",
                hoverinfo="skip",
            )
        )

    node_styles = {
        "junction": {"color": "#c2c5cc", "size": 5, "symbol": "circle"},
        "roundabout": {"color": "#8d99ae", "size": 10, "symbol": "circle-open"},
        "residence": {"color": "#1f77b4", "size": 10, "symbol": "square"},
        "work": {"color": "#9467bd", "size": 10, "symbol": "diamond"},
        "commerce": {"color": "#ff7f0e", "size": 10, "symbol": "star"},
        "leisure": {"color": "#e377c2", "size": 10, "symbol": "hexagon"},
        "crossing": {"color": "#f1c40f", "size": 9, "symbol": "square-open"},
        "cyclist": {"color": "#2ca02c", "size": 9, "symbol": "triangle-up"},
    }
    for kind, points in nodes_by_kind.items():
        style = node_styles.get(kind, node_styles["junction"])
        fig.add_trace(
            go.Scatter(
                x=[point[0] for point in points],
                y=[point[1] for point in points],
                mode="markers",
                marker=dict(size=style["size"], color=style["color"], symbol=style["symbol"]),
                name=kind.replace("_", " "),
            )
        )

    fig.add_trace(
        go.Scatter(
            x=agent_x,
            y=agent_y,
            mode="markers",
            marker=dict(size=11, color="#1f77b4", line=dict(width=1, color="#0b3d91")),
            name="agents",
        )
    )
    if accident_x:
        fig.add_trace(
            go.Scatter(
                x=accident_x,
                y=accident_y,
                mode="markers",
                marker=dict(size=14, color="#d62728", symbol="x"),
                name="accidents",
            )
        )
    fig.update_layout(
        height=600,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def create_app() -> Dash:
    app = Dash(__name__)
    app.title = "Motor Insurance Simulation"

    app.layout = html.Div(
        style={"fontFamily": "Arial", "display": "flex", "gap": "24px"},
        children=[
            html.Div(
                style={"width": "320px"},
                children=[
                    html.H2("Simulation Control"),
                    html.Label("Seed"),
                    dcc.Input(id="seed-input", type="number", value=42),
                    html.Label("Agents"),
                    dcc.Slider(id="agent-count", min=5, max=60, step=1, value=20),
                    html.Label("Map Size"),
                    dcc.Dropdown(
                        id="map-size",
                        options=[
                            {"label": "Small (12x8)", "value": "small"},
                            {"label": "Medium (20x14)", "value": "medium"},
                            {"label": "Large (28x20)", "value": "large"},
                        ],
                        value="medium",
                    ),
                    html.Div(style={"height": "10px"}),
                    html.Button("Start", id="start-btn"),
                    html.Button("Pause", id="pause-btn", style={"marginLeft": "8px"}),
                    html.Button("Step", id="step-btn", style={"marginLeft": "8px"}),
                    html.Button("Reset", id="reset-btn", style={"marginLeft": "8px"}),
                    html.H4("Summary"),
                    html.Pre(id="summary-output", style={"whiteSpace": "pre-wrap"}),
                ],
            ),
            html.Div(
                style={"flex": "1"},
                children=[
                    dcc.Graph(id="sim-graph"),
                    dcc.Interval(id="tick", interval=600, n_intervals=0, disabled=True),
                    dcc.Store(id="sim-state"),
                    dcc.Store(id="accident-store", data=[]),
                ],
            ),
        ],
    )

    @app.callback(
        Output("sim-state", "data"),
        Output("accident-store", "data"),
        Output("tick", "disabled"),
        Input("start-btn", "n_clicks"),
        Input("pause-btn", "n_clicks"),
        Input("reset-btn", "n_clicks"),
        State("seed-input", "value"),
        State("agent-count", "value"),
        State("map-size", "value"),
        State("sim-state", "data"),
        prevent_initial_call=True,
    )
    def control_simulation(start, pause, reset, seed, agent_count, map_size, state):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if trigger == "pause-btn":
            return state, dash.no_update, True
        if trigger == "reset-btn" or state is None:
            config = _config_from_inputs(seed, agent_count, map_size)
            sim = Simulation(config)
            return _serialize_sim(sim), [], True
        if trigger == "start-btn":
            return state, dash.no_update, False
        return state, dash.no_update, False

    @app.callback(
        Output("sim-graph", "figure"),
        Output("accident-store", "data", allow_duplicate=True),
        Output("summary-output", "children"),
        Output("sim-state", "data", allow_duplicate=True),
        Input("tick", "n_intervals"),
        Input("step-btn", "n_clicks"),
        State("sim-state", "data"),
        State("accident-store", "data"),
        prevent_initial_call=True,
    )
    def advance_simulation(_, __, state, accidents):
        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            state = _serialize_sim(simulation)
        simulation = _deserialize_sim(state)
        result = simulation.step()
        accidents = (accidents or []) + [
            {
                "step": accident.step,
                "location": accident.location,
                "severity": accident.severity,
                "total_claim": accident.total_claim,
            }
            for accident in result.accidents
        ]
        summary = summarize_run(simulation)
        figure = build_map_figure(simulation, accidents[-20:])
        return figure, accidents, json.dumps(summary, indent=2), _serialize_sim(simulation)

    return app


def _config_from_inputs(seed: int, agent_count: int, map_size: str) -> SimulationConfig:
    size_map = {
        "small": (12, 8),
        "medium": (20, 14),
        "large": (28, 20),
    }
    width, height = size_map.get(map_size, (20, 14))
    map_config = MapConfig(width=width, height=height)
    driver_config = DriverConfig(count=agent_count)
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
    for agent in state["agents"]:
        sim_agent = simulation.agents[agent["agent_id"]]
        sim_agent.current_node = agent["current_node"]
        sim_agent.route = agent["route"]
        sim_agent.route_index = agent["route_index"]
    return simulation


if __name__ == "__main__":
    app = create_app()
    app.run_server(debug=True)
