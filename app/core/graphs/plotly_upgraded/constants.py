"""Shared constants for upgraded Plotly graph generation."""

from __future__ import annotations

COLOR_PALETTE = [
    "#0D5265",
    "#32DAC8",
    "#7630EA",
    "#C140FF",
    "#FF8300",
    "#FEC901",
    "#01A982",
    "#00739D",
    "#6633BC",
    "#008567",
    "#00E8CF",
    "#C54E4B",
    "#00C8FF",
    "#FC5A5A",
    "#FFEB59",
    "#8D741C",
]

DEFAULT_LAYOUT = {
    "template": "simple_white",
    "margin": {"l": 20, "r": 20, "b": 20, "t": 40, "pad": 0},
    "height": 380,
    "font": {"family": "Open Sans, Helvetica Neue, Helvetica, Arial, sans-serif", "size": 12},
    "legend": {"orientation": "h", "y": -0.2},
    "bargroupgap": 0.2,
    "barcornerradius": "5%",
}

GRAPH_TYPE_ALIASES = {
    "bar": "bar",
    "vertical_bar": "bar",
    "horizontal_bar": "horizontal_bar",
    "grouped_bar": "grouped_bar",
    "stacked_bar": "stacked_bar",
    "line": "line",
    "area": "area",
    "scatter": "scatter",
    "pie": "pie",
    "donut": "donut",
    "treemap": "treemap",
    "sunburst": "sunburst",
    "funnel": "funnel",
    "waterfall": "waterfall",
    "combo_bar_line": "combo_bar_line",
    "pareto": "pareto",
    "gauge": "gauge",
}
