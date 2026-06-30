"""3D graph builders (3 columns in dataframe context)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .utils import (
    build_hover_template,
    ensure_columns_exist,
    get_bargap,
    get_dticks,
    select_palette,
    truncate_labels,
)


def get_3d_vertical_bar_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2 or not categorical_columns:
        raise ValueError("3D vertical bar chart requires two numerical and one categorical column")

    n1, n2 = numerical_columns[:2]
    cat = categorical_columns[0]
    ensure_columns_exist(df, [cat, n1, n2])

    safe_df = df[[cat, n1, n2]].copy()
    tooltip = [cat, n1, n2]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=safe_df[cat],
            y=safe_df[n1],
            offsetgroup=1,
            name=n1,
            marker_color=select_palette(0),
            text=safe_df[n1],
            texttemplate="%{text:.2s}",
            customdata=safe_df[tooltip],
            hovertemplate=build_hover_template(tooltip, value_token="%{y}"),
        )
    )
    fig.add_trace(
        go.Bar(
            x=safe_df[cat],
            y=safe_df[n2],
            offsetgroup=2,
            name=n2,
            marker_color=select_palette(1),
            text=safe_df[n2],
            texttemplate="%{text:.2s}",
            customdata=safe_df[tooltip],
            hovertemplate=build_hover_template(tooltip, value_token="%{y}"),
        )
    )

    fig.update_yaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(
        title=cat,
        linewidth=1.2,
        tickvals=list(range(safe_df.shape[0])),
        ticktext=truncate_labels(safe_df[cat].tolist(), 20),
    )
    fig.update_layout(bargap=get_bargap(safe_df.shape[0]))
    return fig


def get_3d_bar_and_line_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2 or not categorical_columns:
        raise ValueError("Bar+Line chart requires two numerical and one categorical column")

    n1, n2 = numerical_columns[:2]
    cat = categorical_columns[0]
    ensure_columns_exist(df, [cat, n1, n2])

    safe_df = df[[cat, n1, n2]].copy()
    tooltip = [cat, n1, n2]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=safe_df[cat],
            y=safe_df[n1],
            name=n1,
            marker_color=select_palette(0),
            text=safe_df[n1],
            texttemplate="%{text:.2s}",
            customdata=safe_df[tooltip],
            hovertemplate=build_hover_template(tooltip, value_token="%{y}"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=safe_df[cat],
            y=safe_df[n2],
            mode="lines+markers",
            line={"shape": "spline", "color": select_palette(1)},
            name=n2,
            customdata=safe_df[tooltip],
            hovertemplate=build_hover_template(tooltip, value_token="%{y}"),
        )
    )

    fig.update_yaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(
        title=cat,
        linewidth=1.2,
        tickvals=list(range(safe_df.shape[0])),
        ticktext=truncate_labels(safe_df[cat].tolist(), 20),
    )
    fig.update_layout(bargap=get_bargap(safe_df.shape[0]))
    return fig


def get_3d_horizontal_bar_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2 or not categorical_columns:
        raise ValueError("Horizontal grouped bar chart requires two numerical and one categorical column")

    n1, n2 = numerical_columns[:2]
    cat = categorical_columns[0]
    ensure_columns_exist(df, [cat, n1, n2])

    safe_df = df[[cat, n1, n2]].copy()
    safe_df["dummy"] = safe_df[[n1, n2]].sum(axis=1)
    safe_df = safe_df.sort_values("dummy", ascending=True).drop(columns=["dummy"])

    tooltip = [cat, n1, n2]
    fig = go.Figure()
    for i, col in enumerate([n1, n2]):
        fig.add_trace(
            go.Bar(
                y=safe_df[cat],
                x=safe_df[col],
                offsetgroup=i + 1,
                name=col,
                marker_color=select_palette(i),
                text=safe_df[col],
                texttemplate="%{text:.2s}",
                customdata=safe_df[tooltip],
                hovertemplate=build_hover_template(tooltip, value_token="%{x}"),
                orientation="h",
            )
        )

    fig.update_xaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_yaxes(title=cat, linewidth=1.2, ticklabelstandoff=10)
    fig.update_layout(bargap=get_bargap(safe_df.shape[0], orientation="h"))
    return fig


def get_3d_vertical_bar_chart_date(df: pd.DataFrame, numerical_columns: list[str], datetime_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2 or not datetime_columns:
        raise ValueError("Date vertical bar chart requires two numerical and one datetime column")

    n1, n2 = numerical_columns[:2]
    d_col = datetime_columns[0]
    ensure_columns_exist(df, [d_col, n1, n2])

    safe_df = df[[d_col, n1, n2]].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col])

    fig = go.Figure()
    for i, col in enumerate([n1, n2]):
        fig.add_trace(
            go.Bar(
                x=safe_df[d_col],
                y=safe_df[col],
                offsetgroup=i + 1,
                name=col,
                marker_color=select_palette(i),
                text=safe_df[col],
                texttemplate="%{text:.2s}",
            )
        )

    d_ticks = get_dticks(safe_df, d_col)
    fig.update_yaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    fig.update_layout(bargap=get_bargap(safe_df.shape[0]))
    return fig


def get_3d_bar_and_line_chart_date(df: pd.DataFrame, numerical_columns: list[str], datetime_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2 or not datetime_columns:
        raise ValueError("Date combo chart requires two numerical and one datetime column")

    n1, n2 = numerical_columns[:2]
    d_col = datetime_columns[0]
    ensure_columns_exist(df, [d_col, n1, n2])

    safe_df = df[[d_col, n1, n2]].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col])

    fig = go.Figure()
    fig.add_trace(go.Bar(x=safe_df[d_col], y=safe_df[n1], name=n1, marker_color=select_palette(0)))
    fig.add_trace(
        go.Scatter(
            x=safe_df[d_col],
            y=safe_df[n2],
            mode="lines+markers",
            line={"shape": "spline", "color": select_palette(1)},
            name=n2,
        )
    )

    d_ticks = get_dticks(safe_df, d_col)
    fig.update_yaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    fig.update_layout(bargap=get_bargap(safe_df.shape[0]))
    return fig


def get_3d_linechart(df: pd.DataFrame, numerical_columns: list[str], datetime_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2 or not datetime_columns:
        raise ValueError("3D line chart requires two numerical and one datetime column")

    n1, n2 = numerical_columns[:2]
    d_col = datetime_columns[0]
    ensure_columns_exist(df, [d_col, n1, n2])

    safe_df = df[[d_col, n1, n2]].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col])

    fig = go.Figure()
    for i, col in enumerate([n1, n2]):
        fig.add_trace(
            go.Scatter(
                x=safe_df[d_col],
                y=safe_df[col],
                mode="lines+markers",
                line={"shape": "spline", "color": select_palette(i)},
                name=col,
            )
        )

    d_ticks = get_dticks(safe_df, d_col)
    fig.update_yaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    return fig


def get_3d_multiple_lines(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str],
    datetime_columns: list[str],
    draw_area: bool = False,
) -> go.Figure:
    if not numerical_columns or not categorical_columns or not datetime_columns:
        raise ValueError("Multiple lines chart requires one numerical, one categorical and one datetime column")

    n_col = numerical_columns[0]
    c_col = categorical_columns[0]
    d_col = datetime_columns[0]
    ensure_columns_exist(df, [n_col, c_col, d_col])

    safe_df = df[[d_col, c_col, n_col]].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col, c_col])

    fig = go.Figure()
    for i, group in enumerate(safe_df[c_col].dropna().unique()):
        temp = safe_df[safe_df[c_col] == group]
        fig.add_trace(
            go.Scatter(
                x=temp[d_col],
                y=temp[n_col],
                mode="lines+markers",
                line={"shape": "spline", "color": select_palette(i)},
                name=str(group),
                fill="tonexty" if draw_area else None,
            )
        )

    d_ticks = get_dticks(safe_df, d_col)
    fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    return fig


def get_3d_multiple_bars(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str],
    datetime_columns: list[str],
    barmode: str = "group",
) -> go.Figure:
    if not numerical_columns or not categorical_columns or not datetime_columns:
        raise ValueError("Multiple bars chart requires one numerical, one categorical and one datetime column")

    n_col = numerical_columns[0]
    c_col = categorical_columns[0]
    d_col = datetime_columns[0]
    ensure_columns_exist(df, [n_col, c_col, d_col])

    safe_df = df[[d_col, c_col, n_col]].copy()
    safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[d_col, c_col])

    fig = go.Figure()
    for i, group in enumerate(safe_df[c_col].dropna().unique()):
        temp = safe_df[safe_df[c_col] == group]
        fig.add_trace(
            go.Bar(
                x=temp[d_col],
                y=temp[n_col],
                offsetgroup=i + 1,
                name=str(group),
                marker_color=select_palette(i),
                text=temp[n_col],
                texttemplate="%{text:.2s}",
            )
        )

    d_ticks = get_dticks(safe_df, d_col)
    if barmode == "stack":
        num_unique = safe_df[d_col].nunique()
    else:
        num_unique = safe_df.shape[0]

    fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    fig.update_layout(barmode=barmode, bargap=get_bargap(num_unique))
    return fig


def get_3d_cat_bars(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str],
    barmode: str = "group",
    orientation: str = "v",
) -> go.Figure:
    if not numerical_columns or len(categorical_columns) < 2:
        raise ValueError("Category bars require one numerical and two categorical columns")

    n_col = numerical_columns[0]
    c1, c2 = categorical_columns[:2]
    ensure_columns_exist(df, [n_col, c1, c2])

    safe_df = df[[c1, c2, n_col]].copy()
    primary, secondary = (c1, c2) if safe_df[c1].nunique() >= safe_df[c2].nunique() else (c2, c1)

    totals = safe_df.groupby(primary)[n_col].sum()
    if barmode == "stack" or orientation == "h":
        ascending = orientation == "h"
        category_order = totals.sort_values(ascending=ascending).index.tolist()
    else:
        category_order = safe_df[primary].dropna().unique().tolist()

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

    fig.update_layout(bargap=get_bargap(len(category_order), orientation=orientation), barmode=barmode)
    return fig


def get_3d_treemap(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if not numerical_columns or len(categorical_columns) < 2:
        raise ValueError("Treemap requires one numerical and two categorical columns")

    n_col = numerical_columns[0]
    c1, c2 = categorical_columns[:2]
    ensure_columns_exist(df, [n_col, c1, c2])

    path = [c1, c2] if df[c1].nunique() < df[c2].nunique() else [c2, c1]
    return px.treemap(df, path=path, values=n_col, color=path[0], color_discrete_sequence=[select_palette(i) for i in range(8)])
