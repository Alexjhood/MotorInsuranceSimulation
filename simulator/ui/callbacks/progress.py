from __future__ import annotations

import dash
from dash import html
from dash.dependencies import Input, Output, State

from simulator.ui.live_progress import live_progress_store
from simulator.ui.progress_utils import normalize_progress


def register_progress_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("live-progress-store", "data"),
        Input("progress-poll-interval", "n_intervals"),
        State("live-progress-store", "data"),
        prevent_initial_call=True,
    )
    def poll_live_progress(n_intervals, current_data):
        """Poll the server-side live progress store for updates."""
        current_version = (current_data or {}).get("_version", 0)
        progress, new_version = live_progress_store.get_if_changed(current_version)
        
        if progress is None:
            # No change, return no_update to avoid unnecessary re-renders
            return dash.no_update
        
        # Add version for change detection
        progress["_version"] = new_version
        return progress

    @app.callback(
        Output("progress-output", "children"),
        Input("progress-store", "data"),
        Input("live-progress-store", "data"),
    )
    def render_progress(progress_data, live_data):
        # Use live data if simulation is currently running, otherwise use completed progress
        if live_data and live_data.get("status") == "running":
            # Merge live data into progress format for display
            display_data = {
                "step": live_data.get("step", "?"),
                "status": live_data.get("status", "running"),
                "current_phase": live_data.get("current_phase", ""),
                "phases": live_data.get("phases", []),
                "stats": live_data.get("stats", {}),
                "total_ms": live_data.get("total_ms", 0),
                "is_live": True,  # Flag to indicate this is live data
            }
            if live_data.get("error"):
                display_data["error"] = live_data["error"]
        elif progress_data:
            display_data = normalize_progress(progress_data)
            display_data["is_live"] = False
        else:
            return html.Div("No step progress yet. Run a simulation step to populate this view.", style={"color": "#666"})
        
        progress_data = display_data

        def format_summary(summary: dict) -> str:
            parts = []
            for key, value in summary.items():
                if isinstance(value, dict):
                    inner = ", ".join(f"{k}={v}" for k, v in value.items())
                    parts.append(f"{key}: {inner}")
                else:
                    parts.append(f"{key}: {value}")
            return " | ".join(parts)

        def build_progress_bar(pct: float, state: str) -> html.Div:
            pct = max(0, min(pct, 100))
            if state == "pending":
                color = "#dee2e6"
            elif state == "running":
                color = "#17a2b8"
            elif state == "error":
                color = "#dc3545"
            else:
                color = "#28a745" if pct >= 100 else "#17a2b8"
            return html.Div(
                style={"height": "8px", "backgroundColor": "#e9ecef", "borderRadius": "4px", "overflow": "hidden"},
                children=[
                    html.Div(
                        style={
                            "width": f"{pct:.1f}%",
                            "height": "100%",
                            "backgroundColor": color,
                            "transition": "width 0.2s ease",
                        }
                    )
                ],
            )

        elements = []
        if progress_data.get("error"):
            elements.append(
                html.Div(
                    [
                        html.Div("Simulation step error", style={"fontWeight": "bold", "marginBottom": "4px"}),
                        html.Div(progress_data.get("error"), style={"fontFamily": "monospace", "fontSize": "11px"}),
                    ],
                    style={
                        "padding": "8px",
                        "backgroundColor": "#f8d7da",
                        "border": "1px solid #f5c6cb",
                        "borderRadius": "4px",
                        "marginBottom": "8px",
                    },
                )
            )

        stats = progress_data.get("stats", {})
        stats_text = ""
        if stats:
            stats_text = f"Agents {stats.get('agents', 0)} | Nodes {stats.get('nodes', 0)} | Edges {stats.get('edges', 0)}"
        phase_text = progress_data.get("current_phase")
        sim_total_ms = progress_data.get("sim_total_ms")
        total_ms = progress_data.get("total_ms", 0)
        callback_total_ms = progress_data.get("callback_total_ms")
        render_ms = progress_data.get("render_ms")
        outside_ms = progress_data.get("outside_ms")
        wall_clock_ms = callback_total_ms if callback_total_ms is not None else total_ms
        is_live = progress_data.get("is_live", False)
        
        # Build header row with step info and optional LIVE indicator
        header_row_children = [
            html.Span(f"Step {progress_data.get('step', '?')}", style={"fontWeight": "bold"}),
        ]
        if is_live:
            header_row_children.append(
                html.Span(
                    " 🔴 LIVE",
                    style={
                        "color": "#dc3545",
                        "fontWeight": "bold",
                        "marginLeft": "8px",
                        "animation": "pulse 1.5s infinite",
                    },
                )
            )
        else:
            header_row_children.append(
                html.Span(
                    f" | wall-clock {wall_clock_ms:.1f}ms"
                    + (f" (sim {sim_total_ms:.1f}ms)" if sim_total_ms is not None else ""),
                    style={"color": "#495057", "marginLeft": "6px"},
                )
            )
        
        # Build timing info row (only show for completed steps)
        timing_row = None
        if not is_live:
            timing_row = html.Div(
                f"Real elapsed {progress_data.get('real_elapsed_ms', 0) or 0:.0f}ms "
                f"(advance {progress_data.get('callback_ms', 0) or 0:.1f}ms"
                + (f", render {render_ms:.1f}ms" if render_ms is not None else "")
                + (f", outside {outside_ms:.1f}ms" if outside_ms is not None else "")
                + ")",
                style={"color": "#6c757d", "fontSize": "11px"},
            )
        
        header_bg = "#fff3cd" if is_live else "#e9ecef"  # Yellow tint for live
        header_border = "#ffc107" if is_live else "#ced4da"
        
        header = html.Div(
            [
                html.Div(header_row_children),
                html.Div(
                    f"Current phase: {phase_text}" if phase_text else "Current phase: -",
                    style={"color": "#6c757d", "fontSize": "11px"},
                ),
                html.Div(
                    stats_text,
                    style={"color": "#6c757d", "fontSize": "11px"},
                )
                if stats_text
                else None,
                timing_row,
            ],
            style={
                "padding": "8px",
                "backgroundColor": header_bg,
                "border": f"1px solid {header_border}",
                "borderRadius": "4px",
                "marginBottom": "8px",
            },
        )
        elements.append(header)

        for phase in progress_data.get("phases", []):
            pct = phase.get("progress_pct", 0)
            completed = phase.get("completed", 0)
            total = phase.get("total", 0)
            duration_ms = phase.get("duration_ms", 0)
            state = phase.get("state", "complete")
            summary_text = format_summary(phase.get("summary", {})) if phase.get("summary") else ""
            if state == "complete":
                status_label = f"{completed}/{total} done" if total else "done"
            else:
                status_label = state

            summary_row = html.Summary(
                [
                    html.Div(
                        [
                            html.Span(phase.get("name", "Task"), style={"fontWeight": "bold"}),
                            html.Span(
                                f" • {status_label}",
                                style={"color": "#6c757d", "marginLeft": "6px"},
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span(f"{duration_ms:.1f}ms", style={"fontSize": "11px", "color": "#495057"}),
                        ],
                        style={"textAlign": "right"},
                    ),
                    build_progress_bar(pct, state),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "1fr auto",
                    "alignItems": "center",
                    "gap": "8px",
                    "cursor": "pointer",
                },
            )
            phase_body = html.Div(
                [
                    html.Div(summary_text, style={"color": "#6c757d", "fontSize": "11px", "marginTop": "4px"})
                    if summary_text
                    else None,
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(item.get("label", "item"), style={"fontWeight": "bold"}),
                                    html.Span(
                                        f" [{item.get('status', '')}]",
                                        style={"color": "#6c757d", "marginLeft": "4px"},
                                    ),
                                    html.Div(
                                        " | ".join(f"{k}={v}" for k, v in (item.get("meta") or {}).items()),
                                        style={"color": "#6c757d", "fontSize": "11px", "marginLeft": "12px"},
                                    )
                                    if item.get("meta")
                                    else None,
                                ],
                                style={
                                    "borderBottom": "1px solid #eee",
                                    "padding": "4px 0",
                                },
                            )
                            for item in (phase.get("items") or [])[:50]
                        ]
                    ),
                    html.Div(
                        f"... {phase.get('truncated')} more entries not shown",
                        style={"color": "#6c757d", "fontSize": "10px", "fontStyle": "italic"},
                    )
                    if phase.get("truncated")
                    else None,
                ]
            )
            phase_block = html.Details(
                open=False,
                children=[summary_row, phase_body],
                style={
                    "padding": "8px",
                    "backgroundColor": "white",
                    "border": "1px solid #dee2e6",
                    "borderRadius": "4px",
                    "marginBottom": "8px",
                    "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
                },
            )
            elements.append(phase_block)

        return elements
