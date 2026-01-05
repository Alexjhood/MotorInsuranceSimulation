from __future__ import annotations

from dataclasses import asdict
import json
import math
from typing import List

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
) -> go.Figure:
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
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.hypot(dx, dy) or 1.0
        perp_x = -dy / length
        perp_y = dx / length
        lane_offsets = _lane_offsets(edge.lanes)
        for offset in lane_offsets:
            coords["x"] += [start.x + perp_x * offset, end.x + perp_x * offset, None]
            coords["y"] += [start.y + perp_y * offset, end.y + perp_y * offset, None]
        coords["x"] += [start.x, end.x, None]
        coords["y"] += [start.y, end.y, None]
        if edge.has_cycle_lane:
            cycle_x += [start.x, end.x, None]
            cycle_y += [start.y, end.y, None]

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
    nodes_by_kind: dict[str, list[tuple[int, int]]] = {}
    for node in map_data.nodes.values():
        nodes_by_kind.setdefault(node.kind, []).append((node.x, node.y))

    agent_x = []
    agent_y = []
    agent_angles = []
    agent_labels = []
    agent_customdata = []
    for agent in simulation.agents.values():
        node = map_data.nodes[agent.current_node]
        previous = map_data.nodes[agent.previous_node]
        agent_x.append(node.x)
        agent_y.append(node.y)
        agent_angles.append(_agent_heading(previous, node))
        agent_labels.append(str(agent.agent_id))
        agent_customdata.append({"type": "agent", "agent_id": agent.agent_id})

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
        "residence": {"color": "#1f77b4", "size": 12, "symbol": "square"},
        "work": {"color": "#9467bd", "size": 12, "symbol": "diamond"},
        "commerce": {"color": "#ff7f0e", "size": 12, "symbol": "star"},
        "leisure": {"color": "#e377c2", "size": 12, "symbol": "hexagon"},
        "crossing": {"color": "#f1c40f", "size": 9, "symbol": "square-open"},
        "cyclist": {"color": "#2ca02c", "size": 9, "symbol": "triangle-up"},
    }
    poi_styles = {
        "residence": {"color": "#1f77b4", "size": 10, "symbol": "square"},
        "work": {"color": "#9467bd", "size": 10, "symbol": "diamond"},
        "commerce": {"color": "#ff7f0e", "size": 10, "symbol": "star"},
        "leisure": {"color": "#e377c2", "size": 10, "symbol": "hexagon"},
        "crossing": {"color": "#f1c40f", "size": 9, "symbol": "square-open"},
        "cyclist": {"color": "#2ca02c", "size": 9, "symbol": "triangle-up"},
    }
    poi_labels = {"residence": "🏠", "work": "🏢", "commerce": "🛍️", "leisure": "🎯"}
    for kind, points in nodes_by_kind.items():
        style = node_styles.get(kind, node_styles["junction"])
        fig.add_trace(
            go.Scatter(
                x=[point[0] for point in points],
                y=[point[1] for point in points],
                mode="markers",
                marker=dict(size=style["size"], color=style["color"], symbol=style["symbol"]),
                text=[poi_labels.get(kind, "") for _ in points],
                textposition="top center",
                name=kind.replace("_", " "),
            )
        )

    fig.add_trace(
        go.Scatter(
            x=agent_x,
            y=agent_y,
            mode="markers",
            marker=dict(
                size=12,
                color="#1f77b4",
                line=dict(width=1, color="#0b3d91"),
                symbol="triangle-up",
                angle=agent_angles,
            ),
            text=agent_labels,
            textposition="top center",
            customdata=agent_customdata,
            name="agents",
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
        dragmode="pan",
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
                    html.Label("Playback Speed (steps/sec)"),
                    dcc.Slider(
                        id="speed-control",
                        min=0.5,
                        max=5,
                        step=0.5,
                        value=1,
                        marks={0.5: "0.5x", 1: "1x", 2: "2x", 3: "3x", 4: "4x", 5: "5x"},
                    ),
                    html.Div(style={"height": "10px"}),
                    html.Button("Start", id="start-btn"),
                    html.Button("Pause", id="pause-btn", style={"marginLeft": "8px"}),
                    html.Button("Back", id="back-btn", style={"marginLeft": "8px"}),
                    html.Button("Step", id="step-btn", style={"marginLeft": "8px"}),
                    html.Button("Reset", id="reset-btn", style={"marginLeft": "8px"}),
                    html.H4("Summary"),
                    html.Pre(id="summary-output", style={"whiteSpace": "pre-wrap"}),
                    html.H4("Selected Agent"),
                    html.Div(id="agent-detail"),
                ],
            ),
            html.Div(
                style={"flex": "1"},
                children=[
                    dcc.Graph(id="sim-graph", config={"scrollZoom": True, "displayModeBar": True}),
                    dcc.Interval(id="tick", interval=600, n_intervals=0, disabled=True),
                    dcc.Store(id="sim-state"),
                    dcc.Store(id="accident-store", data=[]),
                    dcc.Store(id="selected-agent"),
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
        State("seed-input", "value"),
        State("agent-count", "value"),
        State("map-size", "value"),
        State("sim-state", "data"),
        prevent_initial_call=True,
    )
    def control_simulation(start, pause, reset, seed, agent_count, map_size, state):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if state is None:
            config = _config_from_inputs(seed, agent_count, map_size)
            sim = Simulation(config)
            new_state = _serialize_sim(sim)
            history = [{"state": new_state, "accidents": []}]
            disabled = False if trigger == "start-btn" else True
            return new_state, [], history, 0, disabled
        if trigger == "pause-btn":
            return state, dash.no_update, dash.no_update, dash.no_update, True
        if trigger == "reset-btn":
            config = _config_from_inputs(seed, agent_count, map_size)
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
        accidents = (accidents or []) + [
            {
                "step": accident.step,
                "location": accident.location,
                "severity": accident.severity,
                "total_claim": accident.total_claim,
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
    )
    def render_simulation(state, accidents, selected_agent):
        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            summary = summarize_run(simulation)
            figure = build_map_figure(simulation, accidents or [], selected_agent)
            return figure, json.dumps(summary, indent=2)
        simulation = _deserialize_sim(state)
        summary = summarize_run(simulation)
        figure = build_map_figure(simulation, (accidents or [])[-20:], selected_agent)
        return figure, json.dumps(summary, indent=2)

    @app.callback(
        Output("selected-agent", "data"),
        Output("agent-detail", "children"),
        Input("sim-graph", "clickData"),
        State("sim-state", "data"),
    )
    def select_agent(click_data, state):
        if not click_data or state is None:
            return None, "Click a vehicle to see its route and details."
        point = click_data.get("points", [{}])[0]
        custom = point.get("customdata") or {}
        if custom.get("type") != "agent":
            return None, "Click a vehicle to see its route and details."
        agent_id = custom.get("agent_id")
        simulation = _deserialize_sim(state)
        agent = simulation.agents.get(agent_id)
        if agent is None:
            return None, "Agent not found."
        detail = html.Ul(
            [
                html.Li(f"Agent #{agent.agent_id}"),
                html.Li(f"Risk profile: {agent.driver.risk_level}"),
                html.Li(f"Vehicle: {agent.vehicle.class_name}"),
                html.Li(f"Home node: {agent.home_node}"),
                html.Li(f"Work node: {agent.work_node}"),
                html.Li(f"Destination: {agent.destination_node}"),
            ]
        )
        return agent_id, detail

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
                "destination_node": agent.destination_node,
                "previous_node": agent.previous_node,
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
    return simulation


def _lane_offsets(lanes: int) -> List[float]:
    if lanes <= 1:
        return [0.0]
    if lanes == 2:
        return [-0.08, 0.08]
    return [-0.12, 0.0, 0.12]


def _agent_heading(start, end) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    angle = math.degrees(math.atan2(dy, dx))
    return angle - 90.0


if __name__ == "__main__":
    app = create_app()
    app.run_server(debug=True)
