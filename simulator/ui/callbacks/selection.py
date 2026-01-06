from __future__ import annotations

import dash
from dash import html
from dash.dependencies import Input, Output, State

from simulator.ui.serialization import deserialize_sim


def register_selection_callbacks(app: dash.Dash) -> None:
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
        simulation = deserialize_sim(state)
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
            simulation = deserialize_sim(state)
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
