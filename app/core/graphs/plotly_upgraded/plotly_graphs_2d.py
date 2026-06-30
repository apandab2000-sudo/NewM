"""2D graph builders with validation and safe defaults."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .utils import (
    build_hover_template,
    ensure_columns_exist,
    get_bargap,
    get_dticks,
    select_palette,
    truncate_labels,
)


def get_2d_scatter_plot(df: pd.DataFrame, numerical_columns: list[str]) -> go.Figure:
    if len(numerical_columns) < 2:
        raise ValueError("Scatter plot requires two numerical columns")

    x_col, y_col = numerical_columns[:2]
    ensure_columns_exist(df, [x_col, y_col])

    fig = go.Figure(
        data=go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="markers",
            marker={"color": select_palette(0), "size": 8},
            customdata=df[[x_col, y_col]],
            hovertemplate=build_hover_template([x_col, y_col], value_token=""),
            name=".",
        )
    )
    fig.update_xaxes(title=x_col, linewidth=1.2, showgrid=False)
    fig.update_yaxes(title=y_col, linewidth=1.2, showline=False, showgrid=True)
    return fig


def get_2d_bar_chart(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str] | None = None,
    datetime_columns: list[str] | None = None,
    orientation: str = "v",
) -> go.Figure:
    categorical_columns = categorical_columns or []
    datetime_columns = datetime_columns or []

    if not numerical_columns:
        raise ValueError("Bar chart requires one numerical column")

    y_col = numerical_columns[0]
    if categorical_columns:
        x_col = categorical_columns[0]
    elif datetime_columns:
        x_col = datetime_columns[0]
    else:
        raise ValueError("Bar chart requires one categorical or datetime column")

    ensure_columns_exist(df, [x_col, y_col])

    safe_df = df[[x_col, y_col]].copy()
    if orientation == "h":
        safe_df = safe_df.sort_values(y_col, ascending=True)

    tooltip = [x_col, y_col]
    fig = go.Figure()

    if orientation == "v":
        fig.add_trace(
            go.Bar(
                x=safe_df[x_col],
                y=safe_df[y_col],
                marker_color=select_palette(0),
                texttemplate="%{y:.2s}",
                text=safe_df[y_col],
                customdata=safe_df[tooltip],
                hovertemplate=build_hover_template(tooltip, value_token="%{y}"),
                name=".",
            )
        )

        if categorical_columns:
            labels = safe_df[x_col].tolist()
            fig.update_xaxes(
                title=x_col,
                linewidth=1.2,
                tickvals=list(range(safe_df.shape[0])),
                ticktext=truncate_labels(labels, 20),
            )
        else:
            safe_df[x_col] = pd.to_datetime(safe_df[x_col], errors="coerce")
            d_ticks = get_dticks(safe_df, x_col)
            fig.update_xaxes(
                title=x_col,
                linewidth=1.2,
                showgrid=False,
                tick0=safe_df[x_col].min(),
                tickformat="%b %Y",
                dtick=d_ticks,
            )

        fig.update_yaxes(title=y_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    else:
        fig.add_trace(
            go.Bar(
                y=safe_df[x_col],
                x=safe_df[y_col],
                marker_color=select_palette(0),
                texttemplate="%{x:.2s}",
                text=safe_df[y_col],
                customdata=safe_df[tooltip],
                hovertemplate=build_hover_template(tooltip, value_token="%{x}"),
                orientation="h",
                name=".",
            )
        )
        labels = safe_df[x_col].tolist()
        fig.update_yaxes(
            title=x_col,
            linewidth=1.2,
            ticklabelstandoff=10,
            tickvals=list(range(safe_df.shape[0])),
            ticktext=truncate_labels(labels, 30),
        )
        fig.update_xaxes(title=y_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)

    fig.update_layout(bargap=get_bargap(safe_df.shape[0], orientation=orientation))
    return fig


def get_2d_line_chart(
    df: pd.DataFrame,
    numerical_columns: list[str],
    datetime_columns: list[str],
    draw_area: bool = False,
) -> go.Figure:
    if not numerical_columns or not datetime_columns:
        raise ValueError("Line chart requires one numerical and one datetime column")

    y_col = numerical_columns[0]
    x_col = datetime_columns[0]
    ensure_columns_exist(df, [x_col, y_col])

    safe_df = df[[x_col, y_col]].copy()
    safe_df[x_col] = pd.to_datetime(safe_df[x_col], errors="coerce")
    safe_df = safe_df.dropna(subset=[x_col])

    tooltip = [x_col, y_col]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=safe_df[x_col],
            y=safe_df[y_col],
            mode="lines+markers+text",
            texttemplate="%{y:.2s}",
            textposition="top center",
            customdata=safe_df[tooltip],
            hovertemplate=build_hover_template(tooltip, value_token="%{y}"),
            line={"color": select_palette(0), "shape": "spline"},
            marker={"color": select_palette(2)},
            fill="tonexty" if draw_area else None,
            name=".",
        )
    )

    d_ticks = get_dticks(safe_df, x_col)
    fig.update_yaxes(title=y_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(
        title=x_col,
        linewidth=1.2,
        showgrid=False,
        tick0=safe_df[x_col].min(),
        tickformat="%b %Y",
        dtick=d_ticks,
    )
    return fig


def get_2d_pie_chart(
    df: pd.DataFrame,
    numerical_columns: list[str],
    categorical_columns: list[str],
    hole: float = 0.0,
) -> go.Figure:
    if not numerical_columns or not categorical_columns:
        raise ValueError("Pie/Donut chart requires one categorical and one numerical column")

    val_col = numerical_columns[0]
    label_col = categorical_columns[0]
    ensure_columns_exist(df, [label_col, val_col])

    safe_df = df[[label_col, val_col]].dropna(subset=[label_col]).copy()
    fig = go.Figure(
        go.Pie(
            labels=safe_df[label_col],
            values=safe_df[val_col],
            hole=hole,
            marker_colors=[select_palette(i) for i in range(max(3, safe_df.shape[0]))],
            textinfo="label+percent",
            textposition="outside",
            hovertemplate="%{label}<br>Value: %{value}<br>Percent: %{percent}<extra></extra>",
        )
    )
    return fig


def get_funnel_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if not numerical_columns or not categorical_columns:
        raise ValueError("Funnel chart requires one categorical and one numerical column")

    val_col = numerical_columns[0]
    stage_col = categorical_columns[0]
    ensure_columns_exist(df, [stage_col, val_col])

    safe_df = df[[stage_col, val_col]].copy()
    fig = go.Figure(
        go.Funnel(
            y=safe_df[stage_col],
            x=safe_df[val_col],
            textposition="inside",
            textinfo="value+percent previous",
            marker={"color": [select_palette(i) for i in range(safe_df.shape[0])]},
            hovertemplate="%{y}<br>Value: %{x}<extra></extra>",
        )
    )
    return fig


def get_waterfall_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if not numerical_columns or not categorical_columns:
        raise ValueError("Waterfall chart requires one categorical and one numerical column")

    val_col = numerical_columns[0]
    label_col = categorical_columns[0]
    ensure_columns_exist(df, [label_col, val_col])

    safe_df = df[[label_col, val_col]].copy()
    measures = ["relative"] * max(safe_df.shape[0] - 1, 0) + ["total"]

    fig = go.Figure(
        go.Waterfall(
            x=safe_df[label_col],
            y=safe_df[val_col],
            measure=measures,
            connector={"line": {"color": "#7A7A7A"}},
            increasing={"marker": {"color": select_palette(6)}},
            decreasing={"marker": {"color": select_palette(11)}},
            totals={"marker": {"color": select_palette(0)}},
            text=safe_df[val_col],
            texttemplate="%{text:.2s}",
        )
    )
    return fig


def get_pareto_chart(df: pd.DataFrame, numerical_columns: list[str], categorical_columns: list[str]) -> go.Figure:
    if not numerical_columns or not categorical_columns:
        raise ValueError("Pareto chart requires one categorical and one numerical column")

    n_col = numerical_columns[0]
    c_col = categorical_columns[0]
    ensure_columns_exist(df, [c_col, n_col])

    safe_df = df[[c_col, n_col]].copy().sort_values(n_col, ascending=False)
    safe_df["cum_sum"] = safe_df[n_col].cumsum()
    total = safe_df[n_col].sum()
    safe_df["cumulative_percentage"] = (safe_df["cum_sum"] / total * 100).round(2) if total else 0
    average = round(float(safe_df[n_col].mean()), 2) if not safe_df.empty else 0

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=safe_df[c_col],
            y=safe_df[n_col],
            marker_color=select_palette(0),
            text=safe_df[n_col],
            texttemplate="%{text:.2s}",
            name=n_col,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=safe_df[c_col],
            y=safe_df["cumulative_percentage"],
            mode="lines+markers",
            line={"shape": "spline", "color": select_palette(2)},
            name="Cumulative Percentage",
            hovertemplate="%{x}<br>Cumulative %: %{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_hline(
        y=average,
        annotation_text=f"Avg({n_col}) = {average}",
        line_dash="dash",
        line_color="#666666",
        line_width=1,
        annotation_position="right top",
    )

    fig.update_yaxes(title=n_col, secondary_y=False, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_yaxes(title="Cumulative Percentage", secondary_y=True)
    fig.update_xaxes(title=c_col, linewidth=1.2)
    fig.update_layout(bargap=get_bargap(safe_df.shape[0]))
    return fig
