"""Reusable Plotly trace factory.

Factory pattern: centralize trace construction to enforce consistency and reduce
duplication across graph composers.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go


@dataclass(frozen=True)
class CartesianSpec:
    x: pd.Series
    y: pd.Series
    name: str
    color: str
    texttemplate: str
    textposition: str = "auto"
    orientation: str = "v"


class TraceFactory:
    """Builds plotly traces from normalized specifications."""

    @staticmethod
    def bar(spec: CartesianSpec) -> go.Bar:
        kwargs: dict = {
            "x": spec.x,
            "y": spec.y,
            "name": spec.name,
            "marker_color": spec.color,
            "text": spec.y if spec.orientation == "v" else spec.x,
            "texttemplate": spec.texttemplate,
            "textposition": spec.textposition,
        }
        if spec.orientation == "h":
            kwargs["x"] = spec.y
            kwargs["y"] = spec.x
            kwargs["orientation"] = "h"

        return go.Bar(**kwargs)

    @staticmethod
    def line(spec: CartesianSpec, shape: str = "spline", mode: str = "lines+markers") -> go.Scatter:
        return go.Scatter(
            x=spec.x,
            y=spec.y,
            mode=mode,
            name=spec.name,
            line={"shape": shape, "color": spec.color},
        )

    @staticmethod
    def area(spec: CartesianSpec, shape: str = "spline") -> go.Scatter:
        return go.Scatter(
            x=spec.x,
            y=spec.y,
            mode="lines+markers",
            name=spec.name,
            line={"shape": shape, "color": spec.color},
            fill="tonexty",
        )

    @staticmethod
    def scatter(spec: CartesianSpec) -> go.Scatter:
        return go.Scatter(
            x=spec.x,
            y=spec.y,
            mode="markers",
            name=spec.name,
            marker={"color": spec.color, "size": 8},
        )

    @staticmethod
    def pie(labels: pd.Series, values: pd.Series, colors: list[str], hole: float = 0.0) -> go.Pie:
        return go.Pie(
            labels=labels,
            values=values,
            hole=hole,
            marker_colors=colors,
            textinfo="label+percent",
            textposition="outside",
            hovertemplate="%{label}<br>Value: %{value}<br>Percent: %{percent}<extra></extra>",
        )

    @staticmethod
    def funnel(labels: pd.Series, values: pd.Series, colors: list[str]) -> go.Funnel:
        return go.Funnel(
            y=labels,
            x=values,
            textposition="inside",
            textinfo="value+percent previous",
            marker={"color": colors},
            hovertemplate="%{y}<br>Value: %{x}<extra></extra>",
        )

    @staticmethod
    def waterfall(labels: pd.Series, values: pd.Series, increasing: str, decreasing: str, total: str) -> go.Waterfall:
        measures = ["relative"] * max(len(values) - 1, 0) + ["total"]
        return go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            connector={"line": {"color": "#7A7A7A"}},
            increasing={"marker": {"color": increasing}},
            decreasing={"marker": {"color": decreasing}},
            totals={"marker": {"color": total}},
            text=values,
            texttemplate="%{text:.2s}",
        )
