from __future__ import annotations

import dash
from dash import html
from dash.dependencies import Input, Output

from simulator.ui.history import server_history


def register_timing_details_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("step-details-output", "children"),
        Input("step-details-store", "data"),
        Input("timing-store", "data"),
    )
    def render_step_details(step_details, timing_data):
        if not step_details or not step_details.get("step"):
            return html.Div("No step data yet. Run the simulation to see detailed timing.", style={"color": "#666"})

        elements = []

        real_ms = step_details.get("real_elapsed_ms")
        callback_ms = step_details.get("callback_total_ms", 0)
        real_str = f"{real_ms:.0f}ms" if real_ms is not None else "N/A"

        elements.append(
            html.Div(
                [
                    html.H5(f"Step {step_details.get('step', '?')}", style={"margin": "0 0 8px 0"}),
                    html.Div(
                        [
                            html.Span("REAL TIME: ", style={"fontWeight": "bold"}),
                            html.Span(
                                real_str,
                                style={
                                    "color": "#dc3545" if real_ms and real_ms > 1000 else "#28a745",
                                    "fontWeight": "bold",
                                    "fontSize": "16px",
                                },
                            ),
                            html.Span(
                                f" (advance callback: {callback_ms:.1f}ms)",
                                style={"color": "#666", "marginLeft": "8px"},
                            ),
                        ]
                    ),
                ],
                style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#e9ecef", "borderRadius": "4px"},
            )
        )

        data_sizes = step_details.get("data_sizes", {})
        if data_sizes:
            def format_size(bytes_count):
                if bytes_count is None:
                    return "n/a"
                if bytes_count > 1_000_000:
                    return f"{bytes_count / 1_000_000:.2f} MB"
                if bytes_count > 1_000:
                    return f"{bytes_count / 1_000:.1f} KB"
                return f"{bytes_count} B"

            history_len = step_details.get("history_length", server_history.length)
            elements.append(
                html.Div(
                    [
                        html.H6("📦 Data Sizes (Browser ↔ Server)", style={"margin": "0 0 8px 0", "color": "#495057"}),
                        html.Div(
                            f"✅ History stored SERVER-SIDE ({history_len} entries, max 50)",
                            style={"color": "#28a745", "fontSize": "10px", "marginBottom": "8px"},
                        ),
                        html.Table(
                            [
                                html.Tr(
                                    [
                                        html.Td("Store", style={"fontWeight": "bold", "padding": "2px 8px"}),
                                        html.Td(
                                            "Input",
                                            style={"fontWeight": "bold", "padding": "2px 8px", "textAlign": "right"},
                                        ),
                                        html.Td(
                                            "Output",
                                            style={"fontWeight": "bold", "padding": "2px 8px", "textAlign": "right"},
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("sim-state", style={"padding": "2px 8px"}),
                                        html.Td(
                                            format_size(data_sizes.get("state_in", 0)),
                                            style={"padding": "2px 8px", "textAlign": "right"},
                                        ),
                                        html.Td(
                                            format_size(data_sizes.get("state_out", 0)),
                                            style={"padding": "2px 8px", "textAlign": "right"},
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("timing-store", style={"padding": "2px 8px"}),
                                        html.Td(
                                            format_size(data_sizes.get("timing_data_in", 0)),
                                            style={"padding": "2px 8px", "textAlign": "right"},
                                        ),
                                        html.Td(
                                            format_size(data_sizes.get("timing_data_out", 0)),
                                            style={"padding": "2px 8px", "textAlign": "right"},
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("log-store", style={"padding": "2px 8px"}),
                                        html.Td(
                                            format_size(data_sizes.get("log_data_in", 0)),
                                            style={"padding": "2px 8px", "textAlign": "right"},
                                        ),
                                        html.Td(
                                            format_size(data_sizes.get("log_data_out", 0)),
                                            style={"padding": "2px 8px", "textAlign": "right"},
                                        ),
                                    ]
                                ),
                            ],
                            style={"fontSize": "11px", "borderCollapse": "collapse", "width": "100%"},
                        ),
                    ],
                    style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#d4edda", "borderRadius": "4px"},
                )
            )

            total_out = sum(
                size for size in [
                    data_sizes.get("state_out"),
                    data_sizes.get("history_out"),
                    data_sizes.get("timing_data_out"),
                    data_sizes.get("log_data_out"),
                ]
                if isinstance(size, (int, float))
            )
            elements.append(
                html.Div(
                    [
                        html.Span("⚠️ Total data to browser: ", style={"fontWeight": "bold"}),
                        html.Span(
                            format_size(total_out),
                            style={"color": "#dc3545" if total_out > 5_000_000 else "#28a745", "fontWeight": "bold"},
                        ),
                        html.Span(
                            " (Large data = slow transfer + browser processing)",
                            style={"color": "#666", "fontSize": "10px", "marginLeft": "8px"},
                        ),
                    ],
                    style={"marginBottom": "16px"},
                )
            )

            data_size_errors = step_details.get("data_size_errors", {})
            if data_size_errors:
                elements.append(
                    html.Div(
                        [
                            html.H6("⚠️ Size Measurement Notes", style={"margin": "0 0 8px 0", "color": "#856404"}),
                            html.Div(
                                [html.Div(f"{k}: {v}", style={"padding": "2px 0"}) for k, v in data_size_errors.items()]
                            ),
                        ],
                        style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#fff3cd", "borderRadius": "4px"},
                    )
                )

            state_counts = step_details.get("state_counts", {})
            if state_counts:
                elements.append(
                    html.Div(
                        [
                            html.H6("📈 State Counts", style={"margin": "0 0 8px 0", "color": "#495057"}),
                            html.Div(
                                [
                                    html.Div(
                                        f"Input: nodes={state_counts.get('input', {}).get('nodes', 0)}, "
                                        f"edges={state_counts.get('input', {}).get('edges', 0)}, "
                                        f"agents={state_counts.get('input', {}).get('agents', 0)}"
                                    ),
                                    html.Div(
                                        f"Output: nodes={state_counts.get('output', {}).get('nodes', 0)}, "
                                        f"edges={state_counts.get('output', {}).get('edges', 0)}, "
                                        f"agents={state_counts.get('output', {}).get('agents', 0)}"
                                    ),
                                ],
                                style={"fontSize": "11px"},
                            ),
                        ],
                        style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#e2e3e5", "borderRadius": "4px"},
                    )
                )

        timings = step_details.get("timings", [])
        if timings:
            elements.append(
                html.Div(
                    [
                        html.H6("⏱️ Callback Internal Timings", style={"margin": "0 0 8px 0", "color": "#495057"}),
                        html.Div(
                            [html.Div(f"{t['label']}: {t['ms']:.2f}ms", style={"padding": "2px 0"}) for t in timings]
                        ),
                    ],
                    style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#d4edda", "borderRadius": "4px"},
                )
            )

        if timing_data and len(timing_data) > 0:
            last_timing = timing_data[-1]
            render_breakdown = last_timing.get("render_breakdown", {})
            if render_breakdown:
                elements.append(
                    html.Div(
                        [
                            html.H6("🎨 Render Callback Breakdown", style={"margin": "0 0 8px 0", "color": "#495057"}),
                            html.Div(
                                [
                                    html.Div(f"Deserialize: {render_breakdown.get('deserialize', 0):.1f}ms"),
                                    html.Div(f"Summarize: {render_breakdown.get('summarize', 0):.1f}ms"),
                                    html.Div(f"Build Figure: {render_breakdown.get('build_figure', 0):.1f}ms"),
                                    html.Div(
                                        f"Total Render: {render_breakdown.get('total', 0):.1f}ms",
                                        style={"fontWeight": "bold"},
                                    ),
                                ],
                                style={"padding": "2px 0"},
                            ),
                        ],
                        style={"marginBottom": "16px", "padding": "8px", "backgroundColor": "#cce5ff", "borderRadius": "4px"},
                    )
                )

        if real_ms is not None and timing_data and len(timing_data) > 0:
            last_timing = timing_data[-1]
            advance_ms = last_timing.get("tasks", {}).get("total_perf", 0)
            render_ms_val = last_timing.get("render_breakdown", {}).get("total", 0)
            total_callbacks = advance_ms + render_ms_val
            outside_ms = max(0, real_ms - total_callbacks)

            elements.append(
                html.Div(
                    [
                        html.H6("🔍 'Outside' Time Analysis", style={"margin": "0 0 8px 0", "color": "#495057"}),
                        html.Div(
                            [
                                html.Div(f"Real elapsed: {real_ms:.0f}ms"),
                                html.Div(f"Advance callback: {advance_ms:.1f}ms"),
                                html.Div(f"Render callback: {render_ms_val:.1f}ms"),
                                html.Div(
                                    f"Outside (network/browser): {outside_ms:.0f}ms",
                                    style={"fontWeight": "bold", "color": "#dc3545" if outside_ms > 500 else "inherit"},
                                ),
                            ]
                        ),
                        html.Div(
                            [
                                html.Div("'Outside' time includes:", style={"fontWeight": "bold", "marginTop": "8px"}),
                                html.Ul(
                                    [
                                        html.Li("Dash framework overhead"),
                                        html.Li("Network round-trip (server → browser → server)"),
                                        html.Li("Browser JSON parsing/stringifying"),
                                        html.Li("Plotly rendering the figure in browser"),
                                        html.Li("Browser garbage collection"),
                                        html.Li("Interval timer delay (~600ms)"),
                                    ],
                                    style={"fontSize": "10px", "margin": "4px 0 0 16px"},
                                ),
                            ],
                            style={"fontSize": "11px", "color": "#666"},
                        ),
                    ],
                    style={
                        "padding": "8px",
                        "backgroundColor": "#f8d7da" if outside_ms > 1000 else "#f8f9fa",
                        "borderRadius": "4px",
                    },
                )
            )

        return elements
