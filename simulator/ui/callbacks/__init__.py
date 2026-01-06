from simulator.ui.callbacks.advance import register_advance_callbacks
from simulator.ui.callbacks.control import register_control_callbacks
from simulator.ui.callbacks.logging import register_logging_callbacks
from simulator.ui.callbacks.probability import register_probability_callbacks
from simulator.ui.callbacks.render import register_render_callbacks
from simulator.ui.callbacks.selection import register_selection_callbacks
from simulator.ui.callbacks.timing_details import register_timing_details_callbacks
from simulator.ui.callbacks.timing_summary import register_timing_summary_callbacks
from simulator.ui.callbacks.view import register_view_callbacks


def register_callbacks(app) -> None:
    register_control_callbacks(app)
    register_advance_callbacks(app)
    register_render_callbacks(app)
    register_selection_callbacks(app)
    register_view_callbacks(app)
    register_probability_callbacks(app)
    register_logging_callbacks(app)
    register_timing_summary_callbacks(app)
    register_timing_details_callbacks(app)
