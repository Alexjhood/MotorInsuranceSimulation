from __future__ import annotations

import math
from typing import List, Tuple

import plotly.graph_objects as go

from simulator.engine.simulation import Simulation


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
