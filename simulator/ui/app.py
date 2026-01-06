from __future__ import annotations

from dataclasses import asdict
import json
import math
import random
import time
import traceback
import uuid
from typing import List, Tuple, Dict, Any

import dash
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go

from simulator.accidents.model import AccidentEvent
from simulator.config import AccidentConfig, DriverConfig, MapConfig, SimulationConfig
from simulator.engine.simulation import Simulation, StepTiming
from simulator.reporting.summary import summarize_run


# Server-side storage for history (avoids sending large data to browser)
# This dramatically reduces browser<->server data transfer
class ServerSideHistory:
    """Server-side storage for simulation history to avoid browser memory issues."""
    
    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._history: List[Dict] = []  # List of {"state": ..., "accidents": ...}
        self._index: int = 0
    
    def append(self, state: Dict, accidents: List) -> int:
        """Append a new history entry, returns new index."""
        # Truncate forward history if we're not at the end
        if self._index < len(self._history) - 1:
            self._history = self._history[:self._index + 1]
        
        self._history.append({"state": state, "accidents": accidents})
        
        # Limit size
        if len(self._history) > self.max_entries:
            self._history = self._history[-self.max_entries:]
        
        self._index = len(self._history) - 1
        return self._index
    
    def go_back(self) -> Tuple[Dict, List, int]:
        """Go back one step, returns (state, accidents, new_index) or None if can't go back."""
        if self._index > 0:
            self._index -= 1
            entry = self._history[self._index]
            return entry["state"], entry["accidents"], self._index
        return None, None, self._index
    
    def get_current(self) -> Tuple[Dict, List, int]:
        """Get current history entry."""
        if self._history:
            entry = self._history[self._index]
            return entry["state"], entry["accidents"], self._index
        return None, [], 0
    
    def reset(self):
        """Clear all history."""
        self._history = []
        self._index = 0
    
    @property
    def index(self) -> int:
        return self._index
    
    @property
    def length(self) -> int:
        return len(self._history)


# Global server-side history instance (for single-user mode)
# For multi-user, you'd use flask session or similar
_server_history = ServerSideHistory(max_entries=50)


def log_to_linear(log_val: float, min_val: float, max_val: float) -> float:
    """Convert log scale slider value to linear probability."""
    if log_val <= 0:
        return min_val
    # Map slider range [0, 1] to log space [log(min), log(max)]
    log_min = math.log10(min_val) if min_val > 0 else -4
    log_max = math.log10(max_val)
    linear_log = log_min + log_val * (log_max - log_min)
    return 10 ** linear_log


def linear_to_log(linear_val: float, min_val: float, max_val: float) -> float:
    """Convert linear probability to log scale slider value."""
    if linear_val <= min_val:
        return 0.0
    if linear_val >= max_val:
        return 1.0
    log_min = math.log10(min_val) if min_val > 0 else -4
    log_max = math.log10(max_val)
    linear_log = math.log10(linear_val)
    return (linear_log - log_min) / (log_max - log_min)


def format_probability_tooltip(log_val: float, min_val: float, max_val: float) -> str:
    """Format a log scale slider value as a probability percentage for tooltip."""
    prob = log_to_linear(log_val, min_val, max_val)
    pct = prob * 100
    if pct >= 10:
        return f"{pct:.1f}%"
    elif pct >= 1:
        return f"{pct:.2f}%"
    elif pct >= 0.1:
        return f"{pct:.2f}%"
    else:
        return f"{pct:.3f}%"


def build_map_figure(
    simulation: Simulation,
    accidents: List[dict],
    selected_agent: int | None = None,
    label_options: List[str] | None = None,
    view_bounds: tuple[float, float, float, float] | None = None,
    agent_size_mult: float = 1.0,
    other_size_mult: float = 1.0,
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
        # Only show agents that are on a journey (not idle)
        if agent.is_idle:
            continue
        
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
        # Label agents by their home address
        label = agent.home_label if show_agent_labels else ""
        custom = {
            "type": "agent",
            "agent_id": agent.agent_id,
            "agent_kind": agent.agent_type,
            "home_label": agent.home_label,
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
        # Only show destinations for agents on journeys
        if agent.is_idle:
            continue
        destination_node = map_data.nodes[agent.destination_node]
        destination_x.append(destination_node.x)
        destination_y.append(destination_node.y)
        destination_labels.append(f"{agent.home_label}->" if show_destination_labels else "")

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
                marker=dict(size=8 * other_size_mult, color="#ff6f61", symbol="circle-open"),
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
        marker = dict(size=style["size"] * other_size_mult, color=style["color"], symbol=style["symbol"])
        if style.get("line"):
            marker["line"] = {"width": style["line"]["width"] * other_size_mult, "color": style["line"]["color"]}
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
                size=10 * agent_size_mult,
                color="#d62728",
                line=dict(width=1 * agent_size_mult, color="#a92122"),
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
                    size=10 * agent_size_mult,
                    color="#2ca02c",
                    line=dict(width=1 * agent_size_mult, color="#1f7a1f"),
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
                marker=dict(size=14 * other_size_mult, color="#d62728", symbol="x"),
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


# Tab color definitions
TAB_COLORS = {
    "setup-tab": {"bg": "#e3f2fd", "border": "#1976d2", "text": "#1565c0"},
    "running-tab": {"bg": "#e8f5e9", "border": "#388e3c", "text": "#2e7d32"},
    "logging-tab": {"bg": "#fff3e0", "border": "#f57c00", "text": "#e65100"},
    "timing-tab": {"bg": "#fce4ec", "border": "#c2185b", "text": "#ad1457"},
    "step-details-tab": {"bg": "#f3e5f5", "border": "#7b1fa2", "text": "#6a1b9a"},
    "info-tab": {"bg": "#e0f7fa", "border": "#0097a7", "text": "#00838f"},
}

def get_tab_style(tab_id: str) -> dict:
    """Get base style for a tab."""
    colors = TAB_COLORS.get(tab_id, {"bg": "#f5f5f5", "border": "#9e9e9e", "text": "#616161"})
    return {
        "padding": "8px 12px",
        "backgroundColor": colors["bg"],
        "borderTop": f"3px solid {colors['border']}",
        "borderLeft": f"1px solid {colors['border']}",
        "borderRight": f"1px solid {colors['border']}",
        "borderBottom": "none",
        "borderRadius": "8px 8px 0 0",
        "color": colors["text"],
        "fontWeight": "500",
        "fontSize": "12px",
        "cursor": "pointer",
        "marginRight": "2px",
        "position": "relative",
        "zIndex": "1",
        "transition": "all 0.2s ease",
    }

def get_tab_selected_style(tab_id: str) -> dict:
    """Get selected style for a tab - dominant appearance."""
    colors = TAB_COLORS.get(tab_id, {"bg": "#f5f5f5", "border": "#9e9e9e", "text": "#616161"})
    return {
        "padding": "10px 14px",
        "backgroundColor": "white",
        "borderTop": f"4px solid {colors['border']}",
        "borderLeft": f"2px solid {colors['border']}",
        "borderRight": f"2px solid {colors['border']}",
        "borderBottom": "2px solid white",
        "borderRadius": "8px 8px 0 0",
        "color": colors["text"],
        "fontWeight": "700",
        "fontSize": "13px",
        "cursor": "pointer",
        "marginRight": "2px",
        "marginBottom": "-2px",
        "position": "relative",
        "zIndex": "10",
        "boxShadow": f"0 -3px 8px rgba(0,0,0,0.1)",
    }


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
                        style={"borderBottom": "2px solid #dee2e6", "marginBottom": "0"},
                        children=[
                            dcc.Tab(
                                label="⚙️ Setup",
                                value="setup-tab",
                                style=get_tab_style("setup-tab"),
                                selected_style=get_tab_selected_style("setup-tab"),
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
                                            html.Hr(),
                                            html.H4("Journey & Accident Settings"),
                                            html.Label("Driver Journey Start Probability (per step when idle)"),
                                            html.Div(
                                                id="journey-start-prob-display",
                                                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"}
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
                                                    1.0: "100%"
                                                }
                                            ),
                                            html.Label("Cyclist Journey Start Probability (per step when idle)"),
                                            html.Div(
                                                id="cyclist-journey-start-prob-display",
                                                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"}
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
                                                    1.0: "100%"
                                                }
                                            ),
                                            html.Label("Unilateral Accident Probability (per agent per step)"),
                                            html.Div(
                                                id="unilateral-prob-display",
                                                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"}
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
                                                    1.0: "10%"
                                                }
                                            ),
                                            html.Label("Vehicle Encounter Accident Probability"),
                                            html.Div(
                                                id="vehicle-encounter-prob-display",
                                                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"}
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
                                                    1.0: "10%"
                                                }
                                            ),
                                            html.Label("Cyclist Encounter Accident Probability"),
                                            html.Div(
                                                id="cyclist-encounter-prob-display",
                                                style={"fontSize": "12px", "color": "#666", "marginBottom": "4px"}
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
                                                    1.0: "10%"
                                                }
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
                                label="▶️ Run",
                                value="running-tab",
                                style=get_tab_style("running-tab"),
                                selected_style=get_tab_selected_style("running-tab"),
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
                                label="📋 Log",
                                value="logging-tab",
                                style=get_tab_style("logging-tab"),
                                selected_style=get_tab_selected_style("logging-tab"),
                                children=[
                                    html.Div(
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
                                ],
                            ),
                            dcc.Tab(
                                label="⏱️ Time",
                                value="timing-tab",
                                style=get_tab_style("timing-tab"),
                                selected_style=get_tab_selected_style("timing-tab"),
                                children=[
                                    html.Div(
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
                                ],
                            ),
                            dcc.Tab(
                                label="📊 Steps",
                                value="step-details-tab",
                                style=get_tab_style("step-details-tab"),
                                selected_style=get_tab_selected_style("step-details-tab"),
                                children=[
                                    html.Div(
                                        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                                        children=[
                                            html.H4("Current Step Timing Details"),
                                            html.Div(
                                                "This tab shows granular timing breakdown for the most recent step only.",
                                                style={"color": "#666", "fontSize": "11px", "marginBottom": "8px"},
                                            ),
                                            html.Div(
                                                id="step-details-output",
                                                style={
                                                    "height": "500px",
                                                    "overflowY": "auto",
                                                    "border": "1px solid #ccc",
                                                    "padding": "8px",
                                                    "fontFamily": "monospace",
                                                    "fontSize": "11px",
                                                    "backgroundColor": "#f8f9fa",
                                                },
                                                children=[],
                                            ),
                                        ],
                                    )
                                ],
                            ),
                            dcc.Tab(
                                label="ℹ️ Info",
                                value="info-tab",
                                style=get_tab_style("info-tab"),
                                selected_style=get_tab_selected_style("info-tab"),
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
                    dcc.Store(id="history-index", data=0),  # Just the index - history is server-side
                    dcc.Store(id="log-store", data=[]),
                    dcc.Store(id="timing-store", data=[]),
                    dcc.Store(id="visualization-enabled", data=True),
                    dcc.Store(id="last-step-timestamp", data=None),
                    dcc.Store(id="step-details-store", data={}),  # Detailed timing for current step only
                ],
            ),
        ],
    )

    @app.callback(
        Output("sim-state", "data"),
        Output("accident-store", "data"),
        Output("history-index", "data"),
        Output("tick", "disabled"),
        Input("start-btn", "n_clicks"),
        Input("pause-btn", "n_clicks"),
        Input("reset-btn", "n_clicks"),
        Input("setup-reset-btn", "n_clicks"),
        State("seed-input", "value"),
        State("map-scale-input", "value"),
        State("cluster-lambda", "value"),
        State("homes-lambda", "value"),
        State("other-locations-lambda", "value"),
        State("cluster-spacing", "value"),
        State("dual-road-chance", "value"),
        State("roundabout-chance", "value"),
        State("highway-roundabout-chance", "value"),
        State("major-junction-ratio", "value"),
        State("journey-start-prob", "value"),
        State("cyclist-journey-start-prob", "value"),
        State("unilateral-prob", "value"),
        State("vehicle-encounter-prob", "value"),
        State("cyclist-encounter-prob", "value"),
        State("sim-state", "data"),
        prevent_initial_call=True,
    )
    def control_simulation(
        start,
        pause,
        reset,
        setup_reset,
        seed,
        map_scale,
        cluster_lambda,
        homes_lambda,
        other_locations_lambda,
        cluster_spacing,
        dual_road_chance,
        roundabout_chance,
        highway_roundabout_chance,
        major_junction_ratio,
        journey_start_prob,
        cyclist_journey_start_prob,
        unilateral_prob,
        vehicle_encounter_prob,
        cyclist_encounter_prob,
        state,
    ):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        if state is None:
            config = _config_from_inputs(
                seed,
                map_scale,
                cluster_lambda,
                homes_lambda,
                other_locations_lambda,
                cluster_spacing,
                dual_road_chance,
                roundabout_chance,
                highway_roundabout_chance,
                major_junction_ratio,
                journey_start_prob,
                cyclist_journey_start_prob,
                unilateral_prob,
                vehicle_encounter_prob,
                cyclist_encounter_prob,
            )
            sim = Simulation(config)
            new_state = _serialize_sim(sim)
            # Store in server-side history
            _server_history.reset()
            idx = _server_history.append(new_state, [])
            disabled = False if trigger == "start-btn" else True
            return new_state, [], idx, disabled
        if trigger == "pause-btn":
            return state, dash.no_update, dash.no_update, True
        if trigger in {"reset-btn", "setup-reset-btn"}:
            config = _config_from_inputs(
                seed,
                map_scale,
                cluster_lambda,
                homes_lambda,
                other_locations_lambda,
                cluster_spacing,
                dual_road_chance,
                roundabout_chance,
                highway_roundabout_chance,
                major_junction_ratio,
                journey_start_prob,
                cyclist_journey_start_prob,
                unilateral_prob,
                vehicle_encounter_prob,
                cyclist_encounter_prob,
            )
            sim = Simulation(config)
            new_state = _serialize_sim(sim)
            # Reset server-side history
            _server_history.reset()
            idx = _server_history.append(new_state, [])
            return new_state, [], idx, True
        if trigger == "start-btn":
            return state, dash.no_update, dash.no_update, False
        return state, dash.no_update, dash.no_update, False

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
        Output("history-index", "data", allow_duplicate=True),
        Output("log-store", "data", allow_duplicate=True),
        Output("timing-store", "data", allow_duplicate=True),
        Output("last-step-timestamp", "data", allow_duplicate=True),
        Output("step-details-store", "data", allow_duplicate=True),
        Input("tick", "n_intervals"),
        Input("step-btn", "n_clicks"),
        Input("back-btn", "n_clicks"),
        State("sim-state", "data"),
        State("accident-store", "data"),
        State("history-index", "data"),
        State("log-store", "data"),
        State("timing-store", "data"),
        State("last-step-timestamp", "data"),
        prevent_initial_call=True,
    )
    def advance_simulation(_, __, ___, state, accidents, history_index, log_data, timing_data, last_step_ts):
        trigger = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        log_data = log_data or []
        timing_data = timing_data or []
        
        # Detailed step timing for granular analysis
        step_details = {"phase": "advance_callback", "timings": [], "data_sizes": {}}
        
        def record_timing(label: str, start_time: float):
            elapsed = (time.perf_counter() - start_time) * 1000
            step_details["timings"].append({"label": label, "ms": elapsed})
            return time.perf_counter()
        
        callback_start = time.perf_counter()
        
        # Record the REAL start time of this step (wall clock)
        this_step_start = time.time()
        
        # Calculate real elapsed time since last step STARTED (includes rendering time)
        real_elapsed_ms = None
        if last_step_ts is not None:
            real_elapsed_ms = (this_step_start - last_step_ts) * 1000
        
        # Track input data sizes (history is now server-side, so just track browser data)
        t0 = time.perf_counter()
        step_details["data_sizes"]["state_in"] = len(json.dumps(state)) if state else 0
        step_details["data_sizes"]["history_in"] = 0  # Server-side now
        step_details["data_sizes"]["timing_data_in"] = len(json.dumps(timing_data)) if timing_data else 0
        step_details["data_sizes"]["log_data_in"] = len(json.dumps(log_data)) if log_data else 0
        t0 = record_timing("measure_input_sizes", t0)
        
        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            state = _serialize_sim(simulation)
        history_index = 0 if history_index is None else history_index
        
        if trigger == "back-btn":
            # Use server-side history for back navigation
            back_state, back_accidents, new_idx = _server_history.go_back()
            if back_state is not None:
                log_data.append({
                    "type": "step",
                    "timestamp": time.time(),
                    "message": f"Stepped back to step {back_state.get('step_index', 0)}",
                })
                return back_state, back_accidents, new_idx, log_data, timing_data, this_step_start, step_details
            return state, accidents, history_index, log_data, timing_data, last_step_ts, step_details
        
        # Time the simulation step with wall-clock tracking
        step_timing = {"step": 0, "tasks": {}, "sim_breakdown": {}, "real_elapsed_ms": real_elapsed_ms}
        wall_clock_start = time.time()
        total_start = time.perf_counter()
        
        try:
            # Deserialize
            deserialize_start = time.perf_counter()
            simulation = _deserialize_sim(state)
            step_timing["tasks"]["deserialize"] = (time.perf_counter() - deserialize_start) * 1000
            step_timing["step"] = simulation.step_index + 1
            
            # Run simulation step (now returns detailed timing)
            sim_step_start = time.perf_counter()
            result = simulation.step()
            step_timing["tasks"]["simulation_step"] = (time.perf_counter() - sim_step_start) * 1000
            
            # Extract detailed simulation breakdown from result.timing
            if result.timing:
                step_timing["sim_breakdown"] = {
                    "agent_movement": result.timing.agent_movement_ms,
                    "lane_assignment": result.timing.lane_assignment_ms,
                    "occupancy_calc": result.timing.occupancy_calc_ms,
                    "unilateral_accidents": result.timing.unilateral_accidents_ms,
                    "multi_agent_accidents": result.timing.multi_agent_accidents_ms,
                    "event_logging": result.timing.event_logging_ms,
                    "sim_total": result.timing.total_step_ms,
                }
            
            # Process accidents
            accident_start = time.perf_counter()
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
            step_timing["tasks"]["process_accidents"] = (time.perf_counter() - accident_start) * 1000
            
            # Serialize
            serialize_start = time.perf_counter()
            new_state = _serialize_sim(simulation)
            step_timing["tasks"]["serialize"] = (time.perf_counter() - serialize_start) * 1000
            
            # Calculate totals
            step_timing["tasks"]["total_perf"] = (time.perf_counter() - total_start) * 1000
            step_timing["wall_clock_ms"] = (time.time() - wall_clock_start) * 1000
            step_timing["timestamp"] = time.time()
            
            # Add timing data (keep last 30 entries to minimize browser data)
            timing_data.append(step_timing)
            if len(timing_data) > 30:
                timing_data = timing_data[-30:]
            
            # Add log entry with real elapsed time (time since last step started)
            active_count = sum(1 for a in simulation.agents.values() if not a.is_idle)
            real_time_str = f"REAL={real_elapsed_ms:.0f}ms" if real_elapsed_ms is not None else "REAL=N/A"
            log_entry = {
                "type": "step",
                "timestamp": time.time(),
                "step": simulation.step_index,
                "message": f"Step {simulation.step_index}: {real_time_str} (callback={step_timing['tasks']['total_perf']:.1f}ms)",
                "details": {
                    "active_agents": active_count,
                    "total_agents": len(simulation.agents),
                    "accidents_this_step": len(accidents),
                    "real_elapsed_ms": real_elapsed_ms,
                    "callback_ms": step_timing['tasks']['total_perf'],
                    "sim_logic_ms": step_timing['tasks']['simulation_step'],
                    "serialize_ms": step_timing['tasks']['serialize'],
                }
            }
            log_data.append(log_entry)
            
            # Log accidents
            for accident in accidents:
                log_data.append({
                    "type": "accident",
                    "timestamp": time.time(),
                    "step": accident["step"],
                    "message": f"Accident at location {accident['location']}: severity={accident['severity']}, claim=${accident['total_claim']:.2f}",
                })
            
            # Keep log limited (reduced to minimize browser data transfer)
            if len(log_data) > 100:
                log_data = log_data[-100:]
            
            # Store in server-side history (not browser)
            new_history_index = _server_history.append(new_state, accidents)
            
            # Track output data sizes for step details (history is server-side now)
            t0 = time.perf_counter()
            step_details["data_sizes"]["state_out"] = len(json.dumps(new_state)) if new_state else 0
            step_details["data_sizes"]["history_out"] = 0  # Server-side now
            step_details["data_sizes"]["timing_data_out"] = len(json.dumps(timing_data)) if timing_data else 0
            step_details["data_sizes"]["log_data_out"] = len(json.dumps(log_data)) if log_data else 0
            step_details["timings"].append({"label": "measure_output_sizes", "ms": (time.perf_counter() - t0) * 1000})
            
            step_details["step"] = simulation.step_index
            step_details["real_elapsed_ms"] = real_elapsed_ms
            step_details["callback_total_ms"] = (time.perf_counter() - callback_start) * 1000
            step_details["history_length"] = _server_history.length  # For debugging
            
            return new_state, accidents, new_history_index, log_data, timing_data, this_step_start, step_details
            
        except Exception as e:
            # Log error with timing info
            elapsed = (time.time() - wall_clock_start) * 1000
            error_entry = {
                "type": "error",
                "timestamp": time.time(),
                "message": f"Error during simulation step (after {elapsed:.1f}ms): {str(e)}",
                "traceback": traceback.format_exc(),
            }
            log_data.append(error_entry)
            step_details["error"] = str(e)
            return state, accidents, history_index, log_data, timing_data, this_step_start, step_details

    @app.callback(
        Output("sim-graph", "figure"),
        Output("summary-output", "children"),
        Output("timing-store", "data", allow_duplicate=True),
        Input("sim-state", "data"),
        Input("accident-store", "data"),
        Input("selected-agent", "data"),
        Input("label-options", "value"),
        Input("view-store", "data"),
        Input("visualization-toggle", "value"),
        Input("agent-size-slider", "value"),
        Input("other-size-slider", "value"),
        State("timing-store", "data"),
        prevent_initial_call=True,
    )
    def render_simulation(state, accidents, selected_agent, label_options, view_store, viz_toggle, agent_size, other_size, timing_data):
        render_start = time.perf_counter()
        timing_data = timing_data or []
        show_visualization = viz_toggle and "show_viz" in viz_toggle
        
        if state is None:
            config = SimulationConfig()
            simulation = Simulation(config)
            summary = summarize_run(simulation)
            if show_visualization:
                figure = build_map_figure(simulation, accidents or [], selected_agent, label_options, agent_size_mult=agent_size or 1.0, other_size_mult=other_size or 1.0)
            else:
                figure = _build_placeholder_figure("Visualization disabled - simulation running in background")
            return figure, json.dumps(summary, indent=2), timing_data
        
        # Time deserialization (this is the suspected bottleneck)
        t0 = time.perf_counter()
        simulation = _deserialize_sim(state)
        deser_time = (time.perf_counter() - t0) * 1000
        
        # Time summary generation
        t0 = time.perf_counter()
        summary = summarize_run(simulation)
        summary_time = (time.perf_counter() - t0) * 1000
        
        if not show_visualization:
            # Return a minimal placeholder figure with timing info
            total_render = (time.perf_counter() - render_start) * 1000
            figure = _build_placeholder_figure(
                f"Visualization disabled\n\nStep: {simulation.step_index}\n"
                f"Active agents: {sum(1 for a in simulation.agents.values() if not a.is_idle)}/{len(simulation.agents)}\n"
                f"Total accidents: {len(simulation.accidents)}\n\n"
                f"Render callback: {total_render:.0f}ms (deser: {deser_time:.0f}ms, summary: {summary_time:.0f}ms)"
            )
            # Update last timing entry with render breakdown
            if timing_data:
                timing_data[-1]["render_breakdown"] = {
                    "deserialize": deser_time,
                    "summarize": summary_time,
                    "total": total_render,
                    "build_figure": 0,
                }
            return figure, json.dumps(summary, indent=2), timing_data
        
        view_bounds = None
        if view_store:
            view_bounds = (
                view_store["x"][0],
                view_store["x"][1],
                view_store["y"][0],
                view_store["y"][1],
            )
        
        # Time figure building
        t0 = time.perf_counter()
        figure = build_map_figure(
            simulation,
            accidents or [],
            selected_agent,
            label_options,
            view_bounds=view_bounds,
            agent_size_mult=agent_size or 1.0,
            other_size_mult=other_size or 1.0,
        )
        figure_time = (time.perf_counter() - t0) * 1000
        total_render = (time.perf_counter() - render_start) * 1000
        
        # Update last timing entry with render breakdown
        if timing_data:
            timing_data[-1]["render_breakdown"] = {
                "deserialize": deser_time,
                "summarize": summary_time,
                "build_figure": figure_time,
                "total": total_render,
            }
        
        return figure, json.dumps(summary, indent=2), timing_data

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

    @app.callback(
        Output("journey-start-prob-display", "children"),
        Input("journey-start-prob", "value"),
    )
    def update_journey_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.05, 0.0001, 1.0)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 1.0)}"

    @app.callback(
        Output("cyclist-journey-start-prob-display", "children"),
        Input("cyclist-journey-start-prob", "value"),
    )
    def update_cyclist_journey_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.01, 0.0001, 1.0)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 1.0)}"

    @app.callback(
        Output("unilateral-prob-display", "children"),
        Input("unilateral-prob", "value"),
    )
    def update_unilateral_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.01, 0.0001, 0.1)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 0.1)}"

    @app.callback(
        Output("vehicle-encounter-prob-display", "children"),
        Input("vehicle-encounter-prob", "value"),
    )
    def update_vehicle_encounter_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.03, 0.0001, 0.1)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 0.1)}"

    @app.callback(
        Output("cyclist-encounter-prob-display", "children"),
        Input("cyclist-encounter-prob", "value"),
    )
    def update_cyclist_encounter_prob_display(log_val):
        if log_val is None:
            log_val = linear_to_log(0.03, 0.0001, 0.1)
        return f"Selected: {format_probability_tooltip(log_val, 0.0001, 0.1)}"

    # Logging tab callbacks
    @app.callback(
        Output("log-output", "children"),
        Input("log-store", "data"),
        Input("log-filter", "value"),
    )
    def render_log_output(log_data, log_filter):
        if not log_data:
            return html.Div("No log entries yet. Start the simulation to see logs.", style={"color": "#666"})
        
        log_filter = log_filter or []
        filtered_logs = [
            entry for entry in log_data
            if entry.get("type") in log_filter
        ]
        
        if not filtered_logs:
            return html.Div("No matching log entries for selected filters.", style={"color": "#666"})
        
        # Render logs in reverse order (newest first)
        log_elements = []
        for entry in reversed(filtered_logs[-100:]):  # Show last 100 filtered entries
            timestamp = time.strftime("%H:%M:%S", time.localtime(entry.get("timestamp", 0)))
            entry_type = entry.get("type", "info")
            message = entry.get("message", "")
            
            # Color coding by type
            color = {"step": "#333", "error": "#d62728", "accident": "#ff7f0e"}.get(entry_type, "#333")
            bg_color = {"error": "#ffebee", "accident": "#fff3e0"}.get(entry_type, "transparent")
            
            entry_div = html.Div(
                style={
                    "borderBottom": "1px solid #eee",
                    "padding": "4px 0",
                    "color": color,
                    "backgroundColor": bg_color,
                },
                children=[
                    html.Span(f"[{timestamp}] ", style={"color": "#999"}),
                    html.Span(f"[{entry_type.upper()}] ", style={"fontWeight": "bold"}),
                    html.Span(message),
                ]
            )
            
            # Add details if present
            if entry.get("details"):
                details = entry["details"]
                detail_text = " | ".join(f"{k}: {v}" for k, v in details.items())
                entry_div.children.append(
                    html.Div(detail_text, style={"color": "#666", "fontSize": "11px", "marginLeft": "20px"})
                )
            
            # Add traceback for errors
            if entry.get("traceback"):
                entry_div.children.append(
                    html.Pre(
                        entry["traceback"],
                        style={"color": "#d62728", "fontSize": "10px", "marginLeft": "20px", "whiteSpace": "pre-wrap"}
                    )
                )
            
            log_elements.append(entry_div)
        
        return log_elements

    @app.callback(
        Output("log-store", "data", allow_duplicate=True),
        Input("clear-log-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_log(_):
        return []

    # Timing tab callbacks
    @app.callback(
        Output("timing-output", "children"),
        Output("timing-summary", "children"),
        Input("timing-store", "data"),
    )
    def render_timing_output(timing_data):
        if not timing_data:
            return (
                html.Div("No timing data yet. Run the simulation to see performance metrics.", style={"color": "#666"}),
                html.Div("No summary available.", style={"color": "#666"})
            )
        
        def calc_stats(times):
            valid = [t for t in times if t is not None and t > 0]
            if not valid:
                return {"avg": 0, "min": 0, "max": 0}
            return {
                "avg": sum(valid) / len(valid),
                "min": min(valid),
                "max": max(valid),
            }
        
        # Calculate summary statistics for high-level tasks
        # REAL elapsed time = time from one step start to next step start (includes rendering)
        real_elapsed_times = [t.get("real_elapsed_ms") for t in timing_data if t.get("real_elapsed_ms") is not None]
        callback_times = [t["tasks"].get("total_perf", t["tasks"].get("total", 0)) for t in timing_data]
        sim_times = [t["tasks"].get("simulation_step", 0) for t in timing_data]
        serialize_times = [t["tasks"].get("serialize", 0) for t in timing_data]
        deserialize_times = [t["tasks"].get("deserialize", 0) for t in timing_data]
        
        # Calculate render time = real_elapsed - callback_time (time spent outside callback)
        render_times = []
        for t in timing_data:
            real = t.get("real_elapsed_ms")
            callback = t["tasks"].get("total_perf", t["tasks"].get("total", 0))
            if real is not None and callback:
                render_times.append(max(0, real - callback))
        
        # Calculate simulation breakdown stats
        sim_breakdown_keys = ["agent_movement", "lane_assignment", "occupancy_calc", 
                             "unilateral_accidents", "multi_agent_accidents", "event_logging"]
        breakdown_stats = {}
        for key in sim_breakdown_keys:
            values = [t.get("sim_breakdown", {}).get(key, 0) for t in timing_data]
            breakdown_stats[key] = calc_stats(values)
        
        real_stats = calc_stats(real_elapsed_times)
        callback_stats = calc_stats(callback_times)
        render_stats = calc_stats(render_times)
        sim_stats = calc_stats(sim_times)
        serialize_stats = calc_stats(serialize_times)
        deserialize_stats = calc_stats(deserialize_times)
        
        cell_style = {"textAlign": "right", "padding": "3px 6px", "fontSize": "11px"}
        header_style = {"textAlign": "right", "padding": "3px 6px", "fontSize": "11px", "fontWeight": "bold"}
        label_style = {"padding": "3px 6px", "fontSize": "11px"}
        section_style = {"padding": "3px 6px", "fontSize": "11px", "fontWeight": "bold", "backgroundColor": "#e9ecef"}
        
        summary = html.Div([
            html.Table([
                html.Thead(html.Tr([
                    html.Th("Metric", style={"textAlign": "left", "padding": "3px 6px", "fontSize": "11px"}),
                    html.Th("Avg", style=header_style),
                    html.Th("Min", style=header_style),
                    html.Th("Max", style=header_style),
                ])),
                html.Tbody([
                    # Real elapsed time (most important - what user actually experiences)
                    html.Tr([html.Td("⏱️ REAL TIME (step-to-step)", colSpan=4, style={**section_style, "backgroundColor": "#dc3545", "color": "white"})]),
                    html.Tr([
                        html.Td("Total Real Elapsed", style={**label_style, "fontWeight": "bold"}),
                        html.Td(f"{real_stats['avg']:.0f}ms", style={**cell_style, "fontWeight": "bold", "color": "#dc3545"}),
                        html.Td(f"{real_stats['min']:.0f}ms", style=cell_style),
                        html.Td(f"{real_stats['max']:.0f}ms", style={**cell_style, "fontWeight": "bold", "color": "#dc3545"}),
                    ], style={"backgroundColor": "#f8d7da"}),
                    html.Tr([
                        html.Td("  → Callback Time", style=label_style),
                        html.Td(f"{callback_stats['avg']:.1f}ms", style=cell_style),
                        html.Td(f"{callback_stats['min']:.1f}ms", style=cell_style),
                        html.Td(f"{callback_stats['max']:.1f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("  → Render/UI Time", style={**label_style, "fontStyle": "italic"}),
                        html.Td(f"{render_stats['avg']:.0f}ms", style={**cell_style, "color": "#856404"}),
                        html.Td(f"{render_stats['min']:.0f}ms", style=cell_style),
                        html.Td(f"{render_stats['max']:.0f}ms", style={**cell_style, "color": "#856404"}),
                    ], style={"backgroundColor": "#fff3cd"}),
                    # UI/State tasks
                    html.Tr([html.Td("STATE MANAGEMENT", colSpan=4, style=section_style)]),
                    html.Tr([
                        html.Td("  Deserialize State", style=label_style),
                        html.Td(f"{deserialize_stats['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{deserialize_stats['min']:.2f}ms", style=cell_style),
                        html.Td(f"{deserialize_stats['max']:.2f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("  Serialize State", style=label_style),
                        html.Td(f"{serialize_stats['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{serialize_stats['min']:.2f}ms", style=cell_style),
                        html.Td(f"{serialize_stats['max']:.2f}ms", style=cell_style),
                    ]),
                    # Simulation breakdown
                    html.Tr([html.Td("SIMULATION BREAKDOWN", colSpan=4, style=section_style)]),
                    html.Tr([
                        html.Td("  Simulation Total", style=label_style),
                        html.Td(f"{sim_stats['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{sim_stats['min']:.2f}ms", style=cell_style),
                        html.Td(f"{sim_stats['max']:.2f}ms", style=cell_style),
                    ], style={"backgroundColor": "#d4edda"}),
                    html.Tr([
                        html.Td("    Agent Movement", style=label_style),
                        html.Td(f"{breakdown_stats['agent_movement']['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['agent_movement']['min']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['agent_movement']['max']:.2f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("    Lane Assignment", style=label_style),
                        html.Td(f"{breakdown_stats['lane_assignment']['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['lane_assignment']['min']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['lane_assignment']['max']:.2f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("    Occupancy Calc", style=label_style),
                        html.Td(f"{breakdown_stats['occupancy_calc']['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['occupancy_calc']['min']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['occupancy_calc']['max']:.2f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("    Unilateral Accidents", style=label_style),
                        html.Td(f"{breakdown_stats['unilateral_accidents']['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['unilateral_accidents']['min']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['unilateral_accidents']['max']:.2f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("    Multi-Agent Accidents", style=label_style),
                        html.Td(f"{breakdown_stats['multi_agent_accidents']['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['multi_agent_accidents']['min']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['multi_agent_accidents']['max']:.2f}ms", style=cell_style),
                    ]),
                    html.Tr([
                        html.Td("    Event Logging", style=label_style),
                        html.Td(f"{breakdown_stats['event_logging']['avg']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['event_logging']['min']:.2f}ms", style=cell_style),
                        html.Td(f"{breakdown_stats['event_logging']['max']:.2f}ms", style=cell_style),
                    ]),
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "border": "1px solid #dee2e6"}),
            html.Div(f"Based on {len(timing_data)} steps ({len(real_elapsed_times)} with real timing)", style={"color": "#666", "fontSize": "11px", "marginTop": "4px"}),
            html.Div(
                "REAL TIME = actual wall-clock time from step N start to step N+1 start. Render/UI Time = time spent outside Python callback (Plotly rendering, network, browser).",
                style={"color": "#856404", "fontSize": "10px", "marginTop": "4px", "fontStyle": "italic"}
            ),
        ])
        
        # Render recent timing entries with detailed breakdown
        timing_elements = []
        for entry in reversed(timing_data[-15:]):  # Show last 15 entries
            step = entry.get("step", 0)
            tasks = entry.get("tasks", {})
            sim_breakdown = entry.get("sim_breakdown", {})
            render_breakdown = entry.get("render_breakdown", {})
            real_ms = entry.get("real_elapsed_ms")
            advance_callback_ms = tasks.get("total_perf", tasks.get("total", 0))
            render_callback_ms = render_breakdown.get("total", 0)
            
            # Total callback time = advance + render callbacks
            total_callback_ms = advance_callback_ms + render_callback_ms
            
            # Time outside callbacks (network, browser, interval delay)
            outside_ms = max(0, real_ms - total_callback_ms) if real_ms is not None else None
            
            # Highlight if real elapsed is very high
            is_slow = real_ms is not None and real_ms > 1000  # > 1 second
            
            # Format real time string
            if real_ms is not None:
                if real_ms >= 1000:
                    real_str = f"REAL: {real_ms/1000:.1f}s"
                else:
                    real_str = f"REAL: {real_ms:.0f}ms"
            else:
                real_str = "REAL: N/A"
            
            # High-level breakdown
            outside_str = f"outside: {outside_ms:.0f}ms" if outside_ms is not None else "outside: N/A"
            high_level = f"advance: {advance_callback_ms:.1f}ms | render: {render_callback_ms:.0f}ms | {outside_str}"
            
            # Advance callback breakdown
            advance_detail = f"  └ advance: deser={tasks.get('deserialize', 0):.1f} | sim={tasks.get('simulation_step', 0):.1f} | ser={tasks.get('serialize', 0):.1f}"
            
            # Render callback breakdown
            if render_breakdown:
                render_detail = f"  └ render: deser={render_breakdown.get('deserialize', 0):.0f} | summary={render_breakdown.get('summarize', 0):.0f} | figure={render_breakdown.get('build_figure', 0):.0f}"
            else:
                render_detail = ""
            
            # Determine background color based on issue
            if is_slow:
                bg_color = "#f8d7da"  # Red - slow overall
            else:
                bg_color = "transparent"
            
            entry_div = html.Div(
                style={
                    "borderBottom": "1px solid #ddd",
                    "padding": "6px 4px",
                    "backgroundColor": bg_color,
                },
                children=[
                    html.Div([
                        html.Span(f"Step {step}: ", style={"fontWeight": "bold"}),
                        html.Span(real_str, style={"color": "#dc3545" if is_slow else "#28a745", "fontWeight": "bold", "fontSize": "13px"}),
                    ]),
                    html.Div(high_level, style={"color": "#495057", "fontSize": "11px", "marginLeft": "12px"}),
                    html.Div(advance_detail, style={"color": "#6c757d", "fontSize": "10px", "marginLeft": "12px"}),
                    html.Div(render_detail, style={"color": "#6c757d", "fontSize": "10px", "marginLeft": "12px"}) if render_detail else None,
                ]
            )
            timing_elements.append(entry_div)
        
        return timing_elements, summary

    @app.callback(
        Output("timing-store", "data", allow_duplicate=True),
        Input("clear-timing-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_timing(_):
        return []

    @app.callback(
        Output("step-details-output", "children"),
        Input("step-details-store", "data"),
        Input("timing-store", "data"),
    )
    def render_step_details(step_details, timing_data):
        if not step_details or not step_details.get("step"):
            return html.Div("No step data yet. Run the simulation to see detailed timing.", style={"color": "#666"})
        
        elements = []
        
        # Header with step number and real elapsed time
        real_ms = step_details.get("real_elapsed_ms")
        callback_ms = step_details.get("callback_total_ms", 0)
        real_str = f"{real_ms:.0f}ms" if real_ms is not None else "N/A"
        
        elements.append(html.Div([
            html.H5(f"Step {step_details.get('step', '?')}", style={"margin": "0 0 8px 0"}),
            html.Div([
                html.Span("REAL TIME: ", style={"fontWeight": "bold"}),
                html.Span(real_str, style={"color": "#dc3545" if real_ms and real_ms > 1000 else "#28a745", "fontWeight": "bold", "fontSize": "16px"}),
                html.Span(f" (advance callback: {callback_ms:.1f}ms)", style={"color": "#666", "marginLeft": "8px"}),
            ]),
        ], style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#e9ecef", "borderRadius": "4px"}))
        
        # Data sizes section
        data_sizes = step_details.get("data_sizes", {})
        if data_sizes:
            def format_size(bytes_count):
                if bytes_count > 1_000_000:
                    return f"{bytes_count / 1_000_000:.2f} MB"
                elif bytes_count > 1_000:
                    return f"{bytes_count / 1_000:.1f} KB"
                return f"{bytes_count} B"
            
            history_len = step_details.get("history_length", _server_history.length)
            elements.append(html.Div([
                html.H6("📦 Data Sizes (Browser ↔ Server)", style={"margin": "0 0 8px 0", "color": "#495057"}),
                html.Div(f"✅ History stored SERVER-SIDE ({history_len} entries, max 50)", 
                         style={"color": "#28a745", "fontSize": "10px", "marginBottom": "8px"}),
                html.Table([
                    html.Tr([
                        html.Td("Store", style={"fontWeight": "bold", "padding": "2px 8px"}),
                        html.Td("Input", style={"fontWeight": "bold", "padding": "2px 8px", "textAlign": "right"}),
                        html.Td("Output", style={"fontWeight": "bold", "padding": "2px 8px", "textAlign": "right"}),
                    ]),
                    html.Tr([
                        html.Td("sim-state", style={"padding": "2px 8px"}),
                        html.Td(format_size(data_sizes.get("state_in", 0)), style={"padding": "2px 8px", "textAlign": "right"}),
                        html.Td(format_size(data_sizes.get("state_out", 0)), style={"padding": "2px 8px", "textAlign": "right"}),
                    ]),
                    html.Tr([
                        html.Td("timing-store", style={"padding": "2px 8px"}),
                        html.Td(format_size(data_sizes.get("timing_data_in", 0)), style={"padding": "2px 8px", "textAlign": "right"}),
                        html.Td(format_size(data_sizes.get("timing_data_out", 0)), style={"padding": "2px 8px", "textAlign": "right"}),
                    ]),
                    html.Tr([
                        html.Td("log-store", style={"padding": "2px 8px"}),
                        html.Td(format_size(data_sizes.get("log_data_in", 0)), style={"padding": "2px 8px", "textAlign": "right"}),
                        html.Td(format_size(data_sizes.get("log_data_out", 0)), style={"padding": "2px 8px", "textAlign": "right"}),
                    ]),
                ], style={"fontSize": "11px", "borderCollapse": "collapse", "width": "100%"}),
            ], style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#d4edda", "borderRadius": "4px"}))
            
            # Total data transferred
            total_out = sum([
                data_sizes.get("state_out", 0),
                data_sizes.get("history_out", 0),
                data_sizes.get("timing_data_out", 0),
                data_sizes.get("log_data_out", 0),
            ])
            elements.append(html.Div([
                html.Span("⚠️ Total data to browser: ", style={"fontWeight": "bold"}),
                html.Span(format_size(total_out), style={"color": "#dc3545" if total_out > 5_000_000 else "#28a745", "fontWeight": "bold"}),
                html.Span(" (Large data = slow transfer + browser processing)", style={"color": "#666", "fontSize": "10px", "marginLeft": "8px"}),
            ], style={"marginBottom": "16px"}))
        
        # Callback timings
        timings = step_details.get("timings", [])
        if timings:
            elements.append(html.Div([
                html.H6("⏱️ Callback Internal Timings", style={"margin": "0 0 8px 0", "color": "#495057"}),
                html.Div([
                    html.Div(f"{t['label']}: {t['ms']:.2f}ms", style={"padding": "2px 0"})
                    for t in timings
                ]),
            ], style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#d4edda", "borderRadius": "4px"}))
        
        # Render callback breakdown from timing data
        if timing_data and len(timing_data) > 0:
            last_timing = timing_data[-1]
            render_breakdown = last_timing.get("render_breakdown", {})
            if render_breakdown:
                elements.append(html.Div([
                    html.H6("🎨 Render Callback Breakdown", style={"margin": "0 0 8px 0", "color": "#495057"}),
                    html.Div([
                        html.Div(f"Deserialize: {render_breakdown.get('deserialize', 0):.1f}ms"),
                        html.Div(f"Summarize: {render_breakdown.get('summarize', 0):.1f}ms"),
                        html.Div(f"Build Figure: {render_breakdown.get('build_figure', 0):.1f}ms"),
                        html.Div(f"Total Render: {render_breakdown.get('total', 0):.1f}ms", style={"fontWeight": "bold"}),
                    ], style={"padding": "2px 0"}),
                ], style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#cce5ff", "borderRadius": "4px"}))
        
        # "Outside" time analysis
        if real_ms is not None and timing_data and len(timing_data) > 0:
            last_timing = timing_data[-1]
            advance_ms = last_timing.get("tasks", {}).get("total_perf", 0)
            render_ms_val = last_timing.get("render_breakdown", {}).get("total", 0)
            total_callbacks = advance_ms + render_ms_val
            outside_ms = max(0, real_ms - total_callbacks)
            
            elements.append(html.Div([
                html.H6("🔍 'Outside' Time Analysis", style={"margin": "0 0 8px 0", "color": "#495057"}),
                html.Div([
                    html.Div(f"Real elapsed: {real_ms:.0f}ms"),
                    html.Div(f"Advance callback: {advance_ms:.1f}ms"),
                    html.Div(f"Render callback: {render_ms_val:.1f}ms"),
                    html.Div(f"Outside (network/browser): {outside_ms:.0f}ms", style={"fontWeight": "bold", "color": "#dc3545" if outside_ms > 500 else "inherit"}),
                ]),
                html.Div([
                    html.Div("'Outside' time includes:", style={"fontWeight": "bold", "marginTop": "8px"}),
                    html.Ul([
                        html.Li("Dash framework overhead"),
                        html.Li("Network round-trip (server → browser → server)"),
                        html.Li("Browser JSON parsing/stringifying"),
                        html.Li("Plotly rendering the figure in browser"),
                        html.Li("Browser garbage collection"),
                        html.Li("Interval timer delay (~600ms)"),
                    ], style={"fontSize": "10px", "margin": "4px 0 0 16px"}),
                ], style={"fontSize": "11px", "color": "#666"}),
            ], style={"padding": "8px", "backgroundColor": "#f8d7da" if outside_ms > 1000 else "#f8f9fa", "borderRadius": "4px"}))
        
        return elements

    return app


def _config_from_inputs(
    seed: int,
    map_scale: float,
    cluster_lambda: float,
    homes_lambda: float,
    other_locations_lambda: float,
    cluster_spacing: float,
    dual_road_chance: float,
    roundabout_chance: float,
    highway_roundabout_chance: float,
    major_junction_ratio: float,
    journey_start_probability: float = 0.05,
    cyclist_journey_start_probability: float = 0.01,
    unilateral_probability: float = 0.01,
    vehicle_encounter_probability: float = 0.03,
    cyclist_encounter_probability: float = 0.03,
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
    # Convert log scale slider values to linear probabilities
    journey_start_probability = log_to_linear(journey_start_probability, 0.0001, 1.0) if journey_start_probability is not None else 0.05
    cyclist_journey_start_probability = log_to_linear(cyclist_journey_start_probability, 0.0001, 1.0) if cyclist_journey_start_probability is not None else 0.01
    unilateral_probability = log_to_linear(unilateral_probability, 0.0001, 0.1) if unilateral_probability is not None else 0.01
    vehicle_encounter_probability = log_to_linear(vehicle_encounter_probability, 0.0001, 0.1) if vehicle_encounter_probability is not None else 0.03
    cyclist_encounter_probability = log_to_linear(cyclist_encounter_probability, 0.0001, 0.1) if cyclist_encounter_probability is not None else 0.03
    
    driver_config = DriverConfig(
        journey_start_probability=journey_start_probability,
        cyclist_journey_start_probability=cyclist_journey_start_probability,
    )
    accident_config = AccidentConfig(
        unilateral_probability=unilateral_probability,
        vehicle_encounter_probability=vehicle_encounter_probability,
        cyclist_encounter_probability=cyclist_encounter_probability,
    )
    return SimulationConfig(
        seed=seed or 42,
        map_config=map_config,
        driver_config=driver_config,
        accident_config=accident_config,
    )


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
                "home_label": agent.home_label,
                "work_node": agent.work_node,
                "destination_node": agent.destination_node,
                "previous_node": agent.previous_node,
                "agent_type": agent.agent_type,
                "heading": list(agent.heading) if agent.heading else None,
                "lane_index": agent.lane_index,
                "wait_steps": agent.wait_steps,
                "is_idle": agent.is_idle,
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
        "random_state": [simulation.random.getstate()[0], list(simulation.random.getstate()[1]), simulation.random.getstate()[2]],
        "agents": agents,
        "accidents": [accident.__dict__ for accident in simulation.accidents],
    }


def _deserialize_sim(state: dict) -> Simulation:
    config_data = state["config"]
    driver_config_data = config_data["driver_config"].copy()
    # Handle legacy configs that may have old fields
    for legacy_field in ["count", "cyclist_count"]:
        if legacy_field in driver_config_data:
            del driver_config_data[legacy_field]
    accident_config_data = config_data.get("accident_config", {})
    config = SimulationConfig(
        seed=config_data["seed"],
        steps=config_data["steps"],
        map_config=MapConfig(**config_data["map_config"]),
        driver_config=DriverConfig(**driver_config_data),
        accident_config=AccidentConfig(**accident_config_data) if accident_config_data else AccidentConfig(),
        time_of_day=config_data.get("time_of_day", "day"),
        enable_parallel=config_data.get("enable_parallel", False),
        parallel_workers=config_data.get("parallel_workers", 2),
    )
    simulation = Simulation(config)
    simulation.step_index = state["step_index"]
    # Restore random state to preserve randomness across serialize/deserialize
    if "random_state" in state:
        rs = state["random_state"]
        simulation.random.setstate((rs[0], tuple(rs[1]), rs[2]))
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
        sim_agent.is_idle = agent.get("is_idle", True)
        sim_agent.home_label = agent.get("home_label", sim_agent.home_label)
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


def _build_placeholder_figure(message: str) -> go.Figure:
    """Build a minimal placeholder figure when visualization is disabled."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=16, color="#666"),
        align="center",
    )
    fig.update_layout(
        height=640,
        width=920,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="#f8f9fa",
    )
    return fig


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
