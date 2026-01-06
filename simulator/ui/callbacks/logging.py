from __future__ import annotations

import time

import dash
from dash import html
from dash.dependencies import Input, Output


def register_logging_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("log-output", "children"),
        Input("log-store", "data"),
        Input("log-filter", "value"),
    )
    def render_log_output(log_data, log_filter):
        if not log_data:
            return html.Div("No log entries yet. Start the simulation to see logs.", style={"color": "#666"})

        log_filter = log_filter or []
        filtered_logs = [entry for entry in log_data if entry.get("type") in log_filter]

        if not filtered_logs:
            return html.Div("No matching log entries for selected filters.", style={"color": "#666"})

        log_elements = []
        for entry in reversed(filtered_logs[-100:]):
            timestamp = time.strftime("%H:%M:%S", time.localtime(entry.get("timestamp", 0)))
            entry_type = entry.get("type", "info")
            message = entry.get("message", "")

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
                ],
            )

            if entry.get("details"):
                details = entry["details"]
                detail_text = " | ".join(f"{k}: {v}" for k, v in details.items())
                entry_div.children.append(
                    html.Div(detail_text, style={"color": "#666", "fontSize": "11px", "marginLeft": "20px"})
                )

            if entry.get("traceback"):
                entry_div.children.append(
                    html.Pre(
                        entry["traceback"],
                        style={
                            "color": "#d62728",
                            "fontSize": "10px",
                            "marginLeft": "20px",
                            "whiteSpace": "pre-wrap",
                        },
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
