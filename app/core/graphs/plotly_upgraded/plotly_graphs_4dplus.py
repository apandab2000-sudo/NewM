"""4D+ graph builders for richer multi-column contexts."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .utils import ensure_columns_exist, get_bargap, get_dticks, select_palette, truncate_labels


def get_4d_vertical_bar_chart(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str] | None = None,
    datetime_columns: list[str] | None = None,
    barmode: str = "group",
) -> go.Figure:
    categorical_columns = categorical_columns or []
    datetime_columns = datetime_columns or []

    if not numerical_columns:
        raise ValueError("4D vertical bar chart requires at least one numerical column")

    if categorical_columns:
        axis_col = categorical_columns[0]
    elif datetime_columns:
        axis_col = datetime_columns[0]
    else:
        raise ValueError("4D vertical bar chart requires one categorical or datetime column")

    ensure_columns_exist(df, [axis_col] + numerical_columns)

    safe_df = df[[axis_col] + numerical_columns].copy()
    if datetime_columns and axis_col == datetime_columns[0]:
        safe_df[axis_col] = pd.to_datetime(safe_df[axis_col], errors="coerce")

    fig = go.Figure()
    for i, n_col in enumerate(numerical_columns):
        fig.add_trace(
            go.Bar(
                x=safe_df[axis_col],
                y=safe_df[n_col],
                name=n_col,
                offsetgroup=i + 1,
                marker_color=select_palette(i),
                text=safe_df[n_col],
                texttemplate="%{text:.2s}",
            )
        )

    if categorical_columns:
        fig.update_xaxes(
            title=axis_col,
            linewidth=1.2,
            tickvals=list(range(safe_df.shape[0])),
            ticktext=truncate_labels(safe_df[axis_col].tolist(), 20),
        )
    else:
        d_ticks = get_dticks(safe_df, axis_col)
        fig.update_xaxes(
            title=axis_col,
            linewidth=1.2,
            tick0=safe_df[axis_col].min(),
            tickformat="%b %Y",
            dtick=d_ticks,
        )

    num_unique = safe_df.shape[0] if barmode == "stack" else safe_df.shape[0] * len(numerical_columns)
    fig.update_yaxes(title=" and ".join(numerical_columns), showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_layout(barmode=barmode, bargap=get_bargap(num_unique))
    return fig


def get_4d_multiple_lines(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str],
    datetime_columns: list[str],
    draw_area: bool = False,
) -> go.Figure:
    if not numerical_columns or not categorical_columns or not datetime_columns:
        raise ValueError("4D multiple lines requires one numerical, one categorical and one datetime column")

    n_col = numerical_columns[0]
    c_col = categorical_columns[0]
    d_col = datetime_columns[0]
    ensure_columns_exist(df, [n_col, c_col, d_col])

    safe_df = df[[n_col, c_col, d_col]].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col, c_col])

    fig = go.Figure()
    for i, group in enumerate(safe_df[c_col].unique()):
        temp = safe_df[safe_df[c_col] == group]
        fig.add_trace(
            go.Scatter(
                x=temp[d_col],
                y=temp[n_col],
                line={"shape": "spline", "color": select_palette(i)},
                mode="lines+markers",
                name=str(group),
                fill="tonexty" if draw_area else None,
            )
        )

    d_ticks = get_dticks(safe_df, d_col)
    fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    return fig


def get_4d_multiple_lines_multiple_num(df: pd.DataFrame, numerical_columns: list[str], datetime_columns: list[str]) -> go.Figure:
    if not numerical_columns or not datetime_columns:
        raise ValueError("Multi-line chart requires numerical columns and one datetime column")

    d_col = datetime_columns[0]
    ensure_columns_exist(df, [d_col] + numerical_columns)

    safe_df = df[[d_col] + numerical_columns].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col])

    fig = go.Figure()
    for i, n_col in enumerate(numerical_columns):
        fig.add_trace(
            go.Scatter(
                x=safe_df[d_col],
                y=safe_df[n_col],
                name=n_col,
                mode="lines+markers",
                line={"shape": "spline", "color": select_palette(i)},
            )
        )

    d_ticks = get_dticks(safe_df, d_col)
    fig.update_yaxes(title=" and ".join(numerical_columns), showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    return fig


def get_4d_cat_bars(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str],
    barmode: str = "group",
    orientation: str = "v",
) -> go.Figure:
    if not numerical_columns or len(categorical_columns) < 2:
        raise ValueError("4D category bars require one numerical and two categorical columns")

    n_col = numerical_columns[0]
    c1, c2 = categorical_columns[:2]
    ensure_columns_exist(df, [n_col, c1, c2])

    safe_df = df[[n_col, c1, c2]].copy()
    primary, secondary = (c1, c2) if safe_df[c1].nunique() >= safe_df[c2].nunique() else (c2, c1)
    totals = safe_df.groupby(primary)[n_col].sum()
    ascending = orientation == "h"
    category_order = totals.sort_values(ascending=ascending).index.tolist() if (barmode == "stack" or orientation == "h") else safe_df[primary].dropna().unique().tolist()

    fig = go.Figure()
    for i, sec in enumerate(safe_df[secondary].dropna().unique()):
        temp = safe_df[safe_df[secondary] == sec].set_index(primary).reindex(category_order).reset_index()
        if orientation == "v":
            fig.add_trace(
                go.Bar(
                    x=temp[primary],
                    y=temp[n_col],
                    name=str(sec),
                    marker_color=select_palette(i),
                    text=temp[n_col],
                    texttemplate="%{text:.2s}",
                    **({"offsetgroup": i + 1} if barmode != "stack" else {}),
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    y=temp[primary],
                    x=temp[n_col],
                    name=str(sec),
                    marker_color=select_palette(i),
                    text=temp[n_col],
                    texttemplate="%{text:.2s}",
                    orientation="h",
                    **({"offsetgroup": i + 1} if barmode != "stack" else {}),
                )
            )

    if orientation == "v":
        fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_xaxes(title=primary, linewidth=1.2, tickvals=list(range(len(category_order))), ticktext=truncate_labels(category_order, 20))
    else:
        fig.update_xaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_yaxes(title=primary, linewidth=1.2, ticklabelstandoff=10, tickvals=list(range(len(category_order))), ticktext=truncate_labels(category_order, 30))

    fig.update_layout(barmode=barmode, bargap=get_bargap(len(category_order), orientation=orientation))
    return fig


def get_4d_bar_and_line_chart(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str] | None = None,
    datetime_columns: list[str] | None = None,
) -> go.Figure:
    categorical_columns = categorical_columns or []
    datetime_columns = datetime_columns or []

    if len(numerical_columns) < 2:
        raise ValueError("4D bar and line chart requires at least two numerical columns")

    if categorical_columns:
        axis_col = categorical_columns[0]
    elif datetime_columns:
        axis_col = datetime_columns[0]
    else:
        raise ValueError("4D bar and line chart requires one categorical or datetime column")

    ensure_columns_exist(df, [axis_col] + numerical_columns)

    safe_df = df[[axis_col] + numerical_columns].copy()
    if datetime_columns and axis_col == datetime_columns[0]:
        safe_df[axis_col] = pd.to_datetime(safe_df[axis_col], errors="coerce")

    fig = go.Figure()
    for i, col in enumerate(numerical_columns):
        if i % 2 == 0:
            fig.add_trace(
                go.Bar(
                    x=safe_df[axis_col],
                    y=safe_df[col],
                    name=col,
                    marker_color=select_palette(i),
                    text=safe_df[col],
                    texttemplate="%{text:.2s}",
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=safe_df[axis_col],
                    y=safe_df[col],
                    name=col,
                    mode="lines+markers",
                    line={"shape": "spline", "color": select_palette(i)},
                )
            )

    if datetime_columns and axis_col == datetime_columns[0]:
        d_ticks = get_dticks(safe_df, axis_col)
        fig.update_xaxes(title=axis_col, linewidth=1.2, tick0=safe_df[axis_col].min(), tickformat="%b %Y", dtick=d_ticks)
    else:
        fig.update_xaxes(title=axis_col, linewidth=1.2, tickvals=list(range(safe_df.shape[0])), ticktext=truncate_labels(safe_df[axis_col].tolist(), 20))

    fig.update_yaxes(title=" and ".join(numerical_columns), showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_layout(bargap=get_bargap(safe_df[axis_col].nunique()))
    return fig


def get_treemap_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if not numerical_columns or len(categorical_columns) < 2:
        raise ValueError("Treemap requires one numerical and at least two categorical columns")
    ensure_columns_exist(df, [numerical_columns[0]] + categorical_columns[:2])

    n_col = numerical_columns[0]
    path = categorical_columns[:2]
    return px.treemap(df, path=path, values=n_col, color=path[0], color_discrete_sequence=[select_palette(i) for i in range(10)])


def get_sunburst_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if not numerical_columns or len(categorical_columns) < 2:
        raise ValueError("Sunburst requires one numerical and at least two categorical columns")
    ensure_columns_exist(df, [numerical_columns[0]] + categorical_columns[:2])

    n_col = numerical_columns[0]
    path = categorical_columns[:2]
    fig = px.sunburst(df, path=path, values=n_col, color_discrete_sequence=[select_palette(i) for i in range(10)])
    fig.update_traces(insidetextorientation="auto")
    return fig
