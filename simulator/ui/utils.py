from __future__ import annotations

import math


def log_to_linear(log_val: float, min_val: float, max_val: float) -> float:
    """Convert log scale slider value to linear probability."""
    if log_val <= 0:
        return min_val
    log_min = math.log10(min_val) if min_val > 0 else -4
    log_max = math.log10(max_val)
    linear_log = log_min + log_val * (log_max - log_min)
    return 10 ** linear_log


def linear_to_log(linear_val: float, min_val: float, max_val: float) -> float:
    """Convert linear probability to log scale slider value."""
    if linear_val <= min_val:
        return 0.0
    if linear_val >= max_val:
        return 1.0
    log_min = math.log10(min_val) if min_val > 0 else -4
    log_max = math.log10(max_val)
    linear_log = math.log10(linear_val)
    return (linear_log - log_min) / (log_max - log_min)


def format_probability_tooltip(log_val: float, min_val: float, max_val: float) -> str:
    """Format a log scale slider value as a probability percentage for tooltip."""
    prob = log_to_linear(log_val, min_val, max_val)
    pct = prob * 100
    if pct >= 10:
        return f"{pct:.1f}%"
    if pct >= 1:
        return f"{pct:.2f}%"
    if pct >= 0.1:
        return f"{pct:.2f}%"
    return f"{pct:.3f}%"
