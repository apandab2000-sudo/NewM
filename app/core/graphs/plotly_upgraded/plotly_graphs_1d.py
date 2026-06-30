"""1D graph builders."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .utils import ensure_columns_exist


def get_gauge_chart(df: pd.DataFrame, numerical_columns: list[str], title: str | None = None) -> go.Figure:
    if not numerical_columns:
        raise ValueError("Gauge chart requires one numerical column")

    metric = numerical_columns[0]
    ensure_columns_exist(df, [metric])
    if df.empty:
        raise ValueError("Gauge chart requires at least one row")

    value = pd.to_numeric(df[metric], errors="coerce").dropna()
    if value.empty:
        raise ValueError(f"Column '{metric}' has no numeric values for gauge chart")

    current = float(value.iloc[0])
    fig = go.Figure(
        go.Indicator(
            mode="number",
            value=current,
            number={"font": {"size": 42}},
            title={"text": title or metric, "font": {"size": 18}},
        )
    )
    return fig
