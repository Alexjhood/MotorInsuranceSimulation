from __future__ import annotations

import dash
from dash import html
from dash.dependencies import Input, Output


def register_timing_summary_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("timing-output", "children"),
        Output("timing-summary", "children"),
        Input("timing-store", "data"),
    )
    def render_timing_output(timing_data):
        if not timing_data:
            return (
                html.Div("No timing data yet. Run the simulation to see performance metrics.", style={"color": "#666"}),
                html.Div("No summary available.", style={"color": "#666"}),
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

        real_elapsed_times = [t.get("real_elapsed_ms") for t in timing_data if t.get("real_elapsed_ms") is not None]
        callback_times = [t["tasks"].get("total_perf", t["tasks"].get("total", 0)) for t in timing_data]
        sim_times = [t["tasks"].get("simulation_step", 0) for t in timing_data]
        serialize_times = [t["tasks"].get("serialize", 0) for t in timing_data]
        deserialize_times = [t["tasks"].get("deserialize", 0) for t in timing_data]

        render_times = []
        for t in timing_data:
            real = t.get("real_elapsed_ms")
            callback = t["tasks"].get("total_perf", t["tasks"].get("total", 0))
            if real is not None and callback:
                render_times.append(max(0, real - callback))

        sim_breakdown_keys = [
            "agent_movement",
            "lane_assignment",
            "occupancy_calc",
            "unilateral_accidents",
            "multi_agent_accidents",
            "event_logging",
        ]
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
        section_style = {
            "padding": "3px 6px",
            "fontSize": "11px",
            "fontWeight": "bold",
            "backgroundColor": "#e9ecef",
        }

        summary = html.Div(
            [
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th(
                                        "Metric",
                                        style={"textAlign": "left", "padding": "3px 6px", "fontSize": "11px"},
                                    ),
                                    html.Th("Avg", style=header_style),
                                    html.Th("Min", style=header_style),
                                    html.Th("Max", style=header_style),
                                ]
                            )
                        ),
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td(
                                            "⏱️ REAL TIME (step-to-step)",
                                            colSpan=4,
                                            style={**section_style, "backgroundColor": "#dc3545", "color": "white"},
                                        )
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("Total Real Elapsed", style={**label_style, "fontWeight": "bold"}),
                                        html.Td(
                                            f"{real_stats['avg']:.0f}ms",
                                            style={**cell_style, "fontWeight": "bold", "color": "#dc3545"},
                                        ),
                                        html.Td(f"{real_stats['min']:.0f}ms", style=cell_style),
                                        html.Td(
                                            f"{real_stats['max']:.0f}ms",
                                            style={**cell_style, "fontWeight": "bold", "color": "#dc3545"},
                                        ),
                                    ],
                                    style={"backgroundColor": "#f8d7da"},
                                ),
                                html.Tr(
                                    [
                                        html.Td("  → Callback Time", style=label_style),
                                        html.Td(f"{callback_stats['avg']:.1f}ms", style=cell_style),
                                        html.Td(f"{callback_stats['min']:.1f}ms", style=cell_style),
                                        html.Td(f"{callback_stats['max']:.1f}ms", style=cell_style),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("  → Render/UI Time", style={**label_style, "fontStyle": "italic"}),
                                        html.Td(f"{render_stats['avg']:.0f}ms", style={**cell_style, "color": "#856404"}),
                                        html.Td(f"{render_stats['min']:.0f}ms", style=cell_style),
                                        html.Td(f"{render_stats['max']:.0f}ms", style={**cell_style, "color": "#856404"}),
                                    ],
                                    style={"backgroundColor": "#fff3cd"},
                                ),
                                html.Tr([html.Td("STATE MANAGEMENT", colSpan=4, style=section_style)]),
                                html.Tr(
                                    [
                                        html.Td("  Deserialize State", style=label_style),
                                        html.Td(f"{deserialize_stats['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{deserialize_stats['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{deserialize_stats['max']:.2f}ms", style=cell_style),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("  Serialize State", style=label_style),
                                        html.Td(f"{serialize_stats['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{serialize_stats['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{serialize_stats['max']:.2f}ms", style=cell_style),
                                    ]
                                ),
                                html.Tr([html.Td("SIMULATION BREAKDOWN", colSpan=4, style=section_style)]),
                                html.Tr(
                                    [
                                        html.Td("  Simulation Total", style=label_style),
                                        html.Td(f"{sim_stats['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{sim_stats['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{sim_stats['max']:.2f}ms", style=cell_style),
                                    ],
                                    style={"backgroundColor": "#d4edda"},
                                ),
                                html.Tr(
                                    [
                                        html.Td("    Agent Movement", style=label_style),
                                        html.Td(f"{breakdown_stats['agent_movement']['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['agent_movement']['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['agent_movement']['max']:.2f}ms", style=cell_style),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("    Lane Assignment", style=label_style),
                                        html.Td(f"{breakdown_stats['lane_assignment']['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['lane_assignment']['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['lane_assignment']['max']:.2f}ms", style=cell_style),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("    Occupancy Calc", style=label_style),
                                        html.Td(f"{breakdown_stats['occupancy_calc']['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['occupancy_calc']['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['occupancy_calc']['max']:.2f}ms", style=cell_style),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("    Unilateral Accidents", style=label_style),
                                        html.Td(
                                            f"{breakdown_stats['unilateral_accidents']['avg']:.2f}ms",
                                            style=cell_style,
                                        ),
                                        html.Td(
                                            f"{breakdown_stats['unilateral_accidents']['min']:.2f}ms",
                                            style=cell_style,
                                        ),
                                        html.Td(
                                            f"{breakdown_stats['unilateral_accidents']['max']:.2f}ms",
                                            style=cell_style,
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("    Multi-Agent Accidents", style=label_style),
                                        html.Td(
                                            f"{breakdown_stats['multi_agent_accidents']['avg']:.2f}ms",
                                            style=cell_style,
                                        ),
                                        html.Td(
                                            f"{breakdown_stats['multi_agent_accidents']['min']:.2f}ms",
                                            style=cell_style,
                                        ),
                                        html.Td(
                                            f"{breakdown_stats['multi_agent_accidents']['max']:.2f}ms",
                                            style=cell_style,
                                        ),
                                    ]
                                ),
                                html.Tr(
                                    [
                                        html.Td("    Event Logging", style=label_style),
                                        html.Td(f"{breakdown_stats['event_logging']['avg']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['event_logging']['min']:.2f}ms", style=cell_style),
                                        html.Td(f"{breakdown_stats['event_logging']['max']:.2f}ms", style=cell_style),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    style={"borderCollapse": "collapse", "width": "100%", "border": "1px solid #dee2e6"},
                ),
                html.Div(
                    f"Based on {len(timing_data)} steps ({len(real_elapsed_times)} with real timing)",
                    style={"color": "#666", "fontSize": "11px", "marginTop": "4px"},
                ),
                html.Div(
                    "REAL TIME = actual wall-clock time from step N start to step N+1 start. "
                    "Render/UI Time = time spent outside Python callback (Plotly rendering, network, browser).",
                    style={"color": "#856404", "fontSize": "10px", "marginTop": "4px", "fontStyle": "italic"},
                ),
            ]
        )

        timing_elements = []
        for entry in reversed(timing_data[-15:]):
            step = entry.get("step", 0)
            tasks = entry.get("tasks", {})
            render_breakdown = entry.get("render_breakdown", {})
            real_ms = entry.get("real_elapsed_ms")
            advance_callback_ms = tasks.get("total_perf", tasks.get("total", 0))
            render_callback_ms = render_breakdown.get("total", 0)

            total_callback_ms = advance_callback_ms + render_callback_ms
            outside_ms = max(0, real_ms - total_callback_ms) if real_ms is not None else None

            is_slow = real_ms is not None and real_ms > 1000

            if real_ms is not None:
                if real_ms >= 1000:
                    real_str = f"REAL: {real_ms/1000:.1f}s"
                else:
                    real_str = f"REAL: {real_ms:.0f}ms"
            else:
                real_str = "REAL: N/A"

            outside_str = f"outside: {outside_ms:.0f}ms" if outside_ms is not None else "outside: N/A"
            high_level = f"advance: {advance_callback_ms:.1f}ms | render: {render_callback_ms:.0f}ms | {outside_str}"

            advance_detail = (
                "  └ advance: deser="
                f"{tasks.get('deserialize', 0):.1f} | sim={tasks.get('simulation_step', 0):.1f} | "
                f"ser={tasks.get('serialize', 0):.1f}"
            )

            if render_breakdown:
                render_detail = (
                    "  └ render: deser="
                    f"{render_breakdown.get('deserialize', 0):.0f} | summary="
                    f"{render_breakdown.get('summarize', 0):.0f} | figure="
                    f"{render_breakdown.get('build_figure', 0):.0f}"
                )
            else:
                render_detail = ""

            bg_color = "#f8d7da" if is_slow else "transparent"

            entry_div = html.Div(
                style={
                    "borderBottom": "1px solid #ddd",
                    "padding": "6px 4px",
                    "backgroundColor": bg_color,
                },
                children=[
                    html.Div(
                        [
                            html.Span(f"Step {step}: ", style={"fontWeight": "bold"}),
                            html.Span(
                                real_str,
                                style={
                                    "color": "#dc3545" if is_slow else "#28a745",
                                    "fontWeight": "bold",
                                    "fontSize": "13px",
                                },
                            ),
                        ]
                    ),
                    html.Div(high_level, style={"color": "#495057", "fontSize": "11px", "marginLeft": "12px"}),
                    html.Div(advance_detail, style={"color": "#6c757d", "fontSize": "10px", "marginLeft": "12px"}),
                    html.Div(render_detail, style={"color": "#6c757d", "fontSize": "10px", "marginLeft": "12px"})
                    if render_detail
                    else None,
                ],
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
