from __future__ import annotations

from dash import html


def build_progress_tab() -> html.Div:
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[
            html.H4("Current Step Progress"),
            html.Div(
                "Shows how the in-flight simulation step is progressing through each sub-task.",
                style={"color": "#666", "fontSize": "11px", "marginBottom": "4px"},
            ),
            html.Div(
                id="progress-output",
                style={
                    "height": "500px",
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
