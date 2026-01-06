from __future__ import annotations

from dash import dcc, html

from simulator.ui.layout.info import build_info_tab
from simulator.ui.layout.logging import build_logging_tab
from simulator.ui.layout.running import build_running_tab
from simulator.ui.layout.setup import build_setup_tab
from simulator.ui.layout.summary import build_summary_tab
from simulator.ui.layout.tabs import get_tab_selected_style, get_tab_style


def build_layout() -> html.Div:
    return html.Div(
        style={"fontFamily": "Arial", "display": "flex", "gap": "24px"},
        children=[
            html.Div(
                style={"width": "360px", "flexShrink": "0"},
                children=[
                    html.H2("Simulation Control"),
                    dcc.Tabs(
                        id="control-tabs",
                        value="setup-tab",
                        style={"borderBottom": "2px solid #dee2e6", "marginBottom": "0"},
                        children=[
                            dcc.Tab(
                                label="⚙️ Setup",
                                value="setup-tab",
                                style=get_tab_style("setup-tab"),
                                selected_style=get_tab_selected_style("setup-tab"),
                                children=[build_setup_tab()],
                            ),
                            dcc.Tab(
                                label="▶️ Run",
                                value="running-tab",
                                style=get_tab_style("running-tab"),
                                selected_style=get_tab_selected_style("running-tab"),
                                children=[build_running_tab()],
                            ),
                            dcc.Tab(
                                label="📋 Log",
                                value="logging-tab",
                                style=get_tab_style("logging-tab"),
                                selected_style=get_tab_selected_style("logging-tab"),
                                children=[build_logging_tab()],
                            ),
                            dcc.Tab(
                                label="🧾 Summary",
                                value="summary-tab",
                                style=get_tab_style("summary-tab"),
                                selected_style=get_tab_selected_style("summary-tab"),
                                children=[build_summary_tab()],
                            ),
                            dcc.Tab(
                                label="ℹ️ Info",
                                value="info-tab",
                                style=get_tab_style("info-tab"),
                                selected_style=get_tab_selected_style("info-tab"),
                                children=[build_info_tab()],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                style={"flex": "1"},
                children=[
                    dcc.Graph(
                        id="sim-graph",
                        config={"scrollZoom": True, "displayModeBar": True},
                        style={"height": "640px", "width": "920px"},
                    ),
                    dcc.Interval(id="tick", interval=600, n_intervals=0, disabled=True),
                    dcc.Store(id="sim-state"),
                    dcc.Store(id="accident-store", data=[]),
                    dcc.Store(id="selected-agent"),
                    dcc.Store(id="selected-item"),
                    dcc.Store(id="view-store"),
                    dcc.Store(id="history-index", data=0),
                    dcc.Store(id="log-store", data=[]),
                    dcc.Store(id="timing-store", data=[]),
                    dcc.Store(id="visualization-enabled", data=True),
                    dcc.Store(id="last-step-timestamp", data=None),
                    dcc.Store(id="step-details-store", data={}),
                    dcc.Store(id="progress-store", data={}),
                ],
            ),
        ],
    )
