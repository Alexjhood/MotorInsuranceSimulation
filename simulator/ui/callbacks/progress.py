from __future__ import annotations

import dash
from dash import html
from dash.dependencies import Input, Output


def register_progress_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("progress-output", "children"),
        Input("progress-store", "data"),
    )
    def render_progress(progress_data):
        if not progress_data or not progress_data.get("phases"):
            return html.Div("No step progress yet. Run a simulation step to populate this view.", style={"color": "#666"})

        def format_summary(summary: dict) -> str:
            parts = []
            for key, value in summary.items():
                if isinstance(value, dict):
                    inner = ", ".join(f"{k}={v}" for k, v in value.items())
                    parts.append(f"{key}: {inner}")
                else:
                    parts.append(f"{key}: {value}")
            return " | ".join(parts)

        def build_progress_bar(pct: float) -> html.Div:
            pct = max(0, min(pct, 100))
            return html.Div(
                style={"height": "8px", "backgroundColor": "#e9ecef", "borderRadius": "4px", "overflow": "hidden"},
                children=[
                    html.Div(
                        style={
                            "width": f"{pct:.1f}%",
                            "height": "100%",
                            "backgroundColor": "#17a2b8" if pct < 100 else "#28a745",
                            "transition": "width 0.2s ease",
                        }
                    )
                ],
            )

        elements = []
        header = html.Div(
            [
                html.Div(
                    [
                        html.Span(f"Step {progress_data.get('step', '?')}", style={"fontWeight": "bold"}),
                        html.Span(
                            f" | wall-clock {progress_data.get('total_ms', 0):.1f}ms",
                            style={"color": "#495057", "marginLeft": "6px"},
                        ),
                    ]
                ),
                html.Div(
                    f"Real elapsed {progress_data.get('real_elapsed_ms', 0) or 0:.0f}ms "
                    f"(callback {progress_data.get('callback_ms', 0) or 0:.1f}ms)",
                    style={"color": "#6c757d", "fontSize": "11px"},
                ),
            ],
            style={
                "padding": "8px",
                "backgroundColor": "#e9ecef",
                "border": "1px solid #ced4da",
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
            summary_text = format_summary(phase.get("summary", {})) if phase.get("summary") else ""

            summary_row = html.Summary(
                [
                    html.Div(
                        [
                            html.Span(phase.get("name", "Task"), style={"fontWeight": "bold"}),
                            html.Span(
                                f" • {completed}/{total} done",
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
                    build_progress_bar(pct),
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
