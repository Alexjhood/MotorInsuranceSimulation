from __future__ import annotations

TAB_COLORS = {
    "setup-tab": {"bg": "#e3f2fd", "border": "#1976d2", "text": "#1565c0"},
    "running-tab": {"bg": "#e8f5e9", "border": "#388e3c", "text": "#2e7d32"},
    "logging-tab": {"bg": "#fff3e0", "border": "#f57c00", "text": "#e65100"},
    "summary-tab": {"bg": "#ede7f6", "border": "#5e35b1", "text": "#4527a0"},
    "info-tab": {"bg": "#e0f7fa", "border": "#0097a7", "text": "#00838f"},
}


def get_tab_style(tab_id: str) -> dict:
    """Get base style for a tab."""
    colors = TAB_COLORS.get(tab_id, {"bg": "#f5f5f5", "border": "#9e9e9e", "text": "#616161"})
    return {
        "padding": "8px 12px",
        "backgroundColor": colors["bg"],
        "borderTop": f"3px solid {colors['border']}",
        "borderLeft": f"1px solid {colors['border']}",
        "borderRight": f"1px solid {colors['border']}",
        "borderBottom": "none",
        "borderRadius": "8px 8px 0 0",
        "color": colors["text"],
        "fontWeight": "500",
        "fontSize": "12px",
        "cursor": "pointer",
        "marginRight": "2px",
        "position": "relative",
        "zIndex": "1",
        "transition": "all 0.2s ease",
    }


def get_tab_selected_style(tab_id: str) -> dict:
    """Get selected style for a tab - dominant appearance."""
    colors = TAB_COLORS.get(tab_id, {"bg": "#f5f5f5", "border": "#9e9e9e", "text": "#616161"})
    return {
        "padding": "10px 14px",
        "backgroundColor": "white",
        "borderTop": f"4px solid {colors['border']}",
        "borderLeft": f"2px solid {colors['border']}",
        "borderRight": f"2px solid {colors['border']}",
        "borderBottom": "2px solid white",
        "borderRadius": "8px 8px 0 0",
        "color": colors["text"],
        "fontWeight": "700",
        "fontSize": "13px",
        "cursor": "pointer",
        "marginRight": "2px",
        "marginBottom": "-2px",
        "position": "relative",
        "zIndex": "10",
        "boxShadow": "0 -3px 8px rgba(0,0,0,0.1)",
    }
