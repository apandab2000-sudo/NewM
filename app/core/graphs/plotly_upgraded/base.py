"""Upgraded Plotly dispatcher with scalable architecture.

Design patterns used:
- Strategy: per graph-type behavior encapsulation
- Factory: reusable trace creation abstraction
- Facade: generate_graphs as a stable integration entrypoint
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from .architecture import GraphContext
from .composers import PlotlyFigureComposer
from .strategies import StrategyRegistry
from .utils import apply_standard_layout, infer_column_profile, normalize_graph_type, safe_datetime_conversion

class GraphItem:
    __slots__ = ("type", "graph")

    def __init__(self, type: str, graph: go.Figure | str):
        self.type = type
        self.graph = graph


def _safe_execute(strategy_name: str, build_fn) -> GraphItem | None:
    try:
        fig = build_fn()
        if fig is not None:
            return GraphItem(type=strategy_name, graph=fig)
    except Exception:
        # Individual graph failures are non-fatal by design.
        return None
    return None


def _prepare_df(df: pd.DataFrame, categorical_columns: list[str], datetime_columns: list[str]) -> pd.DataFrame:
    safe_df = df.copy()
    if datetime_columns:
        safe_df = safe_datetime_conversion(safe_df, datetime_columns)
    subset = categorical_columns + datetime_columns
    if subset:
        safe_df = safe_df.dropna(subset=subset)
    return safe_df.replace({pd.NA: None})


def _default_graph_plan(
    numerical_columns: list[str],
    categorical_columns: list[str],
    datetime_columns: list[str],
    total_columns: int,
) -> list[str]:
    if total_columns <= 1 and len(numerical_columns) == 1:
        return ["gauge"]

    if total_columns == 2:
        if len(numerical_columns) == 2:
            return ["scatter"]
        if len(numerical_columns) == 1 and len(categorical_columns) == 1:
            return ["bar", "horizontal_bar", "pie", "donut", "pareto", "funnel", "waterfall"]
        if len(numerical_columns) == 1 and len(datetime_columns) == 1:
            return ["line", "bar", "area"]

    if total_columns == 3:
        if len(numerical_columns) == 2 and len(categorical_columns) == 1:
            return ["grouped_bar", "combo_bar_line", "horizontal_bar"]
        if len(numerical_columns) == 2 and len(datetime_columns) == 1:
            return ["combo_bar_line", "line", "grouped_bar"]
        if len(numerical_columns) == 1 and len(categorical_columns) == 1 and len(datetime_columns) == 1:
            return ["line", "grouped_bar", "stacked_bar", "area"]
        if len(numerical_columns) == 1 and len(categorical_columns) == 2:
            return ["grouped_bar", "stacked_bar", "horizontal_bar", "treemap", "sunburst"]

    if total_columns >= 4:
        return ["grouped_bar", "stacked_bar", "line", "combo_bar_line", "treemap", "sunburst"]

    return []


def _build_items(context: GraphContext, graph_types: list[str]) -> list[GraphItem]:
    composer = PlotlyFigureComposer()
    registry = StrategyRegistry()

    items: list[GraphItem] = []
    for gtype in graph_types:
        normalized = normalize_graph_type(gtype)
        strategy = registry.resolve(normalized)
        result = _safe_execute(normalized, lambda s=strategy: s.build(context, composer))
        if result:
            items.append(result)
    return items


def generate_graphs(
    df: pd.DataFrame,
    requested_graph_types: list[str] | None = None,
    graph_title: str | None = None,
    python: bool = False,
) -> list[dict[str, Any]]:
    """Generate graph outputs using Strategy + Factory architecture.

    Args:
        df: Source dataframe.
        requested_graph_types: Optional graph types to generate. If omitted,
            a default plan is inferred from column profile.
        graph_title: Optional title for all returned charts.
        python: When True, returns Figure objects; otherwise returns JSON.

    Returns:
        List of graph metadata dicts with keys: type, graph, graph_id.
    """
    if df is None or df.empty:
        return []

    profile = infer_column_profile(df)
    safe_df = _prepare_df(df, profile.categorical, profile.datetime)
    if safe_df.empty:
        return []

    graph_types = requested_graph_types or _default_graph_plan(
        profile.numerical,
        profile.categorical,
        profile.datetime,
        total_columns=safe_df.shape[1],
    )

    context = GraphContext(df=safe_df, profile=profile)
    items = _build_items(context, graph_types)

    output: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        fig = apply_standard_layout(item.graph, title=graph_title)
        output.append(
            {
                "type": item.type,
                "graph": fig if python else fig.to_json(),
                "graph_id": idx,
            }
        )
    return output
