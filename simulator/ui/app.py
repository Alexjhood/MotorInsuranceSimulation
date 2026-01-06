from __future__ import annotations

from dash import Dash

from simulator.ui.callbacks import register_callbacks
from simulator.ui.layout import build_layout


def create_app() -> Dash:
    app = Dash(__name__)
    app.title = "Motor Insurance Simulation"

    app.layout = build_layout()
    register_callbacks(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
