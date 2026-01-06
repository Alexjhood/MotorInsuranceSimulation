from __future__ import annotations

from typing import Callable, Iterable, Mapping

from dash import html


def build_summary_content(summary: dict) -> html.Div:
    overview_stats = [
        ("Steps", f"{summary.get('steps', 0):,}"),
        ("Active agents", f"{summary.get('active_agents', 0):,}"),
        ("Total accidents", f"{summary.get('total_accidents', 0):,}"),
        ("Total distance", f"{summary.get('total_distance', 0):.1f}"),
        ("Journeys started", f"{summary.get('total_journeys_started', 0):,}"),
        ("Journeys completed", f"{summary.get('total_journeys_completed', 0):,}"),
        ("Avg journey length", f"{summary.get('avg_journey_length', 0):.2f}"),
        ("Total claims", f"${summary.get('total_claims', 0):,.2f}"),
    ]

    journey_stats = [
        ("Avg journey length", f"{summary.get('avg_journey_length', 0):.2f}"),
        ("Median journey length", f"{summary.get('median_journey_length', 0):.2f}"),
        ("Shortest journey", f"{summary.get('min_journey_length', 0):.2f}"),
        ("Longest journey", f"{summary.get('max_journey_length', 0):.2f}"),
        ("Total journey distance", f"{summary.get('total_journey_distance', 0):.2f}"),
        ("Avg distance per step", f"{summary.get('avg_distance_per_step', 0):.2f}"),
    ]

    traffic_stats = [
        ("Total node visits", f"{summary.get('total_node_visits', 0):,}"),
        ("Average visits per node", f"{summary.get('avg_node_visits', 0):.2f}"),
        ("Active nodes", f"{summary.get('active_nodes', 0):,}"),
    ]

    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "16px"},
        children=[
            html.Div(
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                    "gap": "8px 16px",
                },
                children=[_stat_card(label, value) for label, value in overview_stats],
            ),
            html.Details(
                open=True,
                children=[
                    html.Summary("Journeys & movement"),
                    _stat_table(journey_stats),
                ],
            ),
            html.Details(
                open=True,
                children=[
                    html.Summary("Traffic intensity"),
                    _stat_table(traffic_stats),
                    _counter_table(
                        "Top traffic nodes",
                        summary.get("top_traffic_nodes", []),
                        empty_label="No traffic recorded yet.",
                        key_label="Node",
                    ),
                    _counter_table(
                        "Traffic by location kind",
                        summary.get("traffic_by_node_kind", {}),
                        empty_label="No traffic recorded yet.",
                    ),
                ],
            ),
            html.Details(
                open=True,
                children=[
                    html.Summary("Accident overview"),
                    _counter_table(
                        "Accidents by severity",
                        summary.get("severity_counts", {}),
                        empty_label="No accidents recorded yet.",
                    ),
                    _counter_table(
                        "Accident types",
                        summary.get("accident_type_counts", {}),
                        empty_label="No accidents recorded yet.",
                    ),
                    _counter_table(
                        "Claims by severity",
                        summary.get("claims_by_severity", {}),
                        empty_label="No claims recorded yet.",
                        formatter=_format_currency,
                    ),
                ],
            ),
            html.Details(
                open=False,
                children=[
                    html.Summary("Accident participants"),
                    _counter_table(
                        "Participants by driver risk",
                        summary.get("driver_risk_counts", {}),
                        empty_label="No participant data recorded yet.",
                    ),
                    _counter_table(
                        "Participants by vehicle class",
                        summary.get("vehicle_class_counts", {}),
                        empty_label="No participant data recorded yet.",
                    ),
                    _counter_table(
                        "Participant types",
                        summary.get("participant_type_counts", {}),
                        empty_label="No participant data recorded yet.",
                    ),
                ],
            ),
            html.Details(
                open=False,
                children=[
                    html.Summary("Accident locations"),
                    _counter_table(
                        "Accidents by location kind",
                        summary.get("location_kind_counts", {}),
                        empty_label="No location data recorded yet.",
                    ),
                    _counter_table(
                        "Accidents by road type",
                        summary.get("road_type_counts", {}),
                        empty_label="No location data recorded yet.",
                    ),
                    _counter_table(
                        "Top accident hotspots",
                        summary.get("top_hotspots", []),
                        empty_label="No hotspots recorded yet.",
                        key_label="Node",
                    ),
                ],
            ),
        ],
    )


def _stat_card(label: str, value: str) -> html.Div:
    return html.Div(
        style={
            "border": "1px solid #e0e0e0",
            "borderRadius": "6px",
            "padding": "8px 10px",
            "backgroundColor": "#fafafa",
        },
        children=[
            html.Div(label, style={"fontSize": "12px", "color": "#666"}),
            html.Div(value, style={"fontSize": "18px", "fontWeight": "bold"}),
        ],
    )


def _stat_table(items: Iterable[tuple[str, str]]) -> html.Table:
    return html.Table(
        style={"width": "100%", "borderCollapse": "collapse", "marginTop": "8px"},
        children=[
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(
                                label,
                                style={"padding": "4px 8px", "borderBottom": "1px solid #eee", "color": "#555"},
                            ),
                            html.Td(
                                value,
                                style={
                                    "padding": "4px 8px",
                                    "borderBottom": "1px solid #eee",
                                    "fontWeight": "bold",
                                },
                            ),
                        ]
                    )
                    for label, value in items
                ]
            )
        ],
    )


def _counter_table(
    title: str,
    counter: Mapping | list[tuple],
    empty_label: str,
    formatter: Callable | None = None,
    key_label: str = "Category",
) -> html.Div:
    rows = []
    if isinstance(counter, list):
        rows = counter
    else:
        rows = sorted(counter.items(), key=lambda item: item[1], reverse=True)

    if not rows:
        return html.Div([html.H5(title), html.Div(empty_label, style={"color": "#777"})])

    fmt = formatter or (lambda value: f"{value:,}")
    return html.Div(
        style={"marginTop": "8px"},
        children=[
            html.H5(title, style={"marginBottom": "4px"}),
            html.Table(
                style={"width": "100%", "borderCollapse": "collapse"},
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(
                                    key_label,
                                    style={
                                        "textAlign": "left",
                                        "padding": "4px 8px",
                                        "borderBottom": "1px solid #ddd",
                                    },
                                ),
                                html.Th(
                                    "Count",
                                    style={
                                        "textAlign": "left",
                                        "padding": "4px 8px",
                                        "borderBottom": "1px solid #ddd",
                                    },
                                ),
                            ]
                        )
                    ),
                    html.Tbody(
                        [
                            html.Tr(
                                [
                                    html.Td(
                                        str(label),
                                        style={"padding": "4px 8px", "borderBottom": "1px solid #eee"},
                                    ),
                                    html.Td(
                                        fmt(value),
                                        style={
                                            "padding": "4px 8px",
                                            "borderBottom": "1px solid #eee",
                                            "fontWeight": "bold",
                                        },
                                    ),
                                ]
                            )
                            for label, value in rows
                        ]
                    ),
                ],
            ),
        ],
    )


def _format_currency(value: float | int) -> str:
    return f"${value:,.2f}"
