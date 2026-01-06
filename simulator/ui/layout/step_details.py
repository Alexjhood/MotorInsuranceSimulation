from __future__ import annotations

from dash import html


def build_step_details_tab() -> html.Div:
    return html.Div(
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
