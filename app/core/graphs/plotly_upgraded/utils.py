"""Utilities for robust Plotly graph generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go

from .constants import COLOR_PALETTE, DEFAULT_LAYOUT, GRAPH_TYPE_ALIASES


@dataclass(frozen=True)
class ColumnProfile:
    numerical: list[str]
    categorical: list[str]
    datetime: list[str]


def normalize_graph_type(graph_type: str) -> str:
    normalized = (graph_type or "").strip().lower()
    return GRAPH_TYPE_ALIASES.get(normalized, normalized)


def ensure_columns_exist(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in dataframe: {missing}")


def infer_column_profile(df: pd.DataFrame) -> ColumnProfile:
    numerical = df.select_dtypes(include=["number"]).columns.tolist()
    datetime_cols = df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns.tolist()

    categorical: list[str] = []
    for col in df.columns:
        if col in numerical or col in datetime_cols:
            continue
        series = df[col]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            parsed = pd.to_datetime(series, errors="coerce")
            # Only classify as datetime if conversion quality is reasonably good.
            if parsed.notna().mean() >= 0.8:
                datetime_cols.append(col)
            else:
                categorical.append(col)
        elif pd.api.types.is_categorical_dtype(series):
            categorical.append(col)

    return ColumnProfile(numerical=numerical, categorical=categorical, datetime=datetime_cols)


def safe_datetime_conversion(df: pd.DataFrame, datetime_columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in datetime_columns:
        out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def truncate_labels(values: Iterable[object], max_len: int) -> list[object]:
    result: list[object] = []
    for value in values:
        if isinstance(value, str) and len(value) > max_len:
            result.append(value[:max_len])
        else:
            result.append(value)
    return result


def get_bargap(num_unique: int, orientation: str = "v") -> float | None:
    if orientation == "v":
        if num_unique < 3:
            return 0.8
        if num_unique < 5:
            return 0.6
        if num_unique < 10:
            return 0.5
        if num_unique <= 15:
            return 0.2
        return None

    if num_unique < 3:
        return 0.6
    if num_unique < 5:
        return 0.5
    return None


def get_dticks(df: pd.DataFrame, date_col: str) -> str:
    unique_count = df[date_col].dropna().nunique()
    lower_name = date_col.lower()

    if "quarter" in lower_name:
        return "M3"
    if "month" in lower_name:
        if unique_count <= 20:
            return "M2"
        if unique_count <= 40:
            return "M3"
        return "M6"
    if "date" in lower_name or "day" in lower_name:
        if unique_count <= 20:
            return "M1"
        if unique_count <= 40:
            return "M2"
        return "M3"
    return "M6"


def apply_standard_layout(fig: go.Figure, title: str | None = None) -> go.Figure:
    fig.update_layout(**DEFAULT_LAYOUT)
    if title:
        fig.update_layout(
            title={
                "text": title,
                "x": 0,
                "y": 0.96,
                "xanchor": "left",
                "font": {"color": "#1E78B4", "size": 14},
            }
        )

    fig.update_xaxes(tickfont={"size": 12})
    fig.update_yaxes(tickfont={"size": 12})
    return fig


def build_hover_template(columns: list[str], value_token: str) -> str:
    header = f"{value_token}<br>"
    tail_parts = [f"{col}: %{{customdata[{idx}]}}" for idx, col in enumerate(columns)]
    return header + "<br>".join(tail_parts) + "<extra></extra>"


def select_palette(index: int) -> str:
    return COLOR_PALETTE[index % len(COLOR_PALETTE)]
