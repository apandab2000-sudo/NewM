"""Graph composition service built on top of reusable trace factory."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .architecture import GraphContext
from .trace_factory import CartesianSpec, TraceFactory
from .utils import ensure_columns_exist, get_bargap, get_dticks, select_palette, truncate_labels


class PlotlyFigureComposer:
    """Single-responsibility chart composition service.

    This service composes complete figures by orchestrating reusable traces.
    """

    def __init__(self, trace_factory: TraceFactory | None = None) -> None:
        self.trace_factory = trace_factory or TraceFactory()

    def _resolve_axis_cols(self, context: GraphContext) -> tuple[list[str], list[str], list[str]]:
        p = context.profile
        return p.numerical, p.categorical, p.datetime

    def build_gauge(self, context: GraphContext) -> go.Figure:
        nums, _, _ = self._resolve_axis_cols(context)
        if not nums:
            raise ValueError("Gauge chart requires one numerical column")
        metric = nums[0]
        ensure_columns_exist(context.df, [metric])
        values = pd.to_numeric(context.df[metric], errors="coerce").dropna()
        if values.empty:
            raise ValueError("Gauge chart requires at least one valid numeric value")
        return go.Figure(go.Indicator(mode="number", value=float(values.iloc[0]), title={"text": metric}))

    def build_scatter(self, context: GraphContext) -> go.Figure:
        nums, _, _ = self._resolve_axis_cols(context)
        if len(nums) < 2:
            raise ValueError("Scatter chart requires two numerical columns")
        x_col, y_col = nums[:2]
        ensure_columns_exist(context.df, [x_col, y_col])
        spec = CartesianSpec(
            x=context.df[x_col],
            y=context.df[y_col],
            name=f"{y_col} vs {x_col}",
            color=select_palette(0),
            texttemplate="%{y:.2s}",
        )
        fig = go.Figure(self.trace_factory.scatter(spec))
        fig.update_xaxes(title=x_col, linewidth=1.2, showgrid=False)
        fig.update_yaxes(title=y_col, linewidth=1.2, showline=False, showgrid=True)
        return fig

    def build_bar(self, context: GraphContext) -> go.Figure:
        nums, cats, dates = self._resolve_axis_cols(context)
        if not nums:
            raise ValueError("Bar chart requires one numerical column")

        value_col = nums[0]
        if cats:
            axis_col = cats[0]
        elif dates:
            axis_col = dates[0]
        else:
            raise ValueError("Bar chart requires one categorical or datetime column")

        ensure_columns_exist(context.df, [axis_col, value_col])
        safe_df = context.df[[axis_col, value_col]].copy()
        if dates and axis_col == dates[0]:
            safe_df[axis_col] = pd.to_datetime(safe_df[axis_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[axis_col])

        spec = CartesianSpec(
            x=safe_df[axis_col],
            y=safe_df[value_col],
            name=value_col,
            color=select_palette(0),
            texttemplate="%{y:.2s}",
        )
        fig = go.Figure(self.trace_factory.bar(spec))

        if cats:
            fig.update_xaxes(
                title=axis_col,
                linewidth=1.2,
                tickvals=list(range(safe_df.shape[0])),
                ticktext=truncate_labels(safe_df[axis_col].tolist(), 20),
            )
        else:
            d_ticks = get_dticks(safe_df, axis_col)
            fig.update_xaxes(title=axis_col, linewidth=1.2, tick0=safe_df[axis_col].min(), tickformat="%b %Y", dtick=d_ticks)

        fig.update_yaxes(title=value_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_layout(bargap=get_bargap(safe_df.shape[0]))
        return fig

    def build_horizontal_bar(self, context: GraphContext) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or not cats:
            raise ValueError("Horizontal bar requires one numerical and one categorical column")
        value_col = nums[0]
        axis_col = cats[0]
        ensure_columns_exist(context.df, [axis_col, value_col])

        safe_df = context.df[[axis_col, value_col]].copy().sort_values(value_col, ascending=True)
        spec = CartesianSpec(
            x=safe_df[axis_col],
            y=safe_df[value_col],
            name=value_col,
            color=select_palette(0),
            texttemplate="%{x:.2s}",
            orientation="h",
        )
        fig = go.Figure(self.trace_factory.bar(spec))
        fig.update_yaxes(
            title=axis_col,
            linewidth=1.2,
            ticklabelstandoff=10,
            tickvals=list(range(safe_df.shape[0])),
            ticktext=truncate_labels(safe_df[axis_col].tolist(), 30),
        )
        fig.update_xaxes(title=value_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_layout(bargap=get_bargap(safe_df.shape[0], orientation="h"))
        return fig

    def build_line(self, context: GraphContext) -> go.Figure:
        nums, cats, dates = self._resolve_axis_cols(context)
        if not nums:
            raise ValueError("Line chart requires a numerical column")

        value_col = nums[0]
        fig = go.Figure()

        if dates and cats:
            d_col, c_col = dates[0], cats[0]
            ensure_columns_exist(context.df, [d_col, c_col, value_col])
            safe_df = context.df[[d_col, c_col, value_col]].copy()
            safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[d_col, c_col])
            for i, group in enumerate(safe_df[c_col].unique()):
                temp = safe_df[safe_df[c_col] == group]
                spec = CartesianSpec(temp[d_col], temp[value_col], str(group), select_palette(i), "%{y:.2s}")
                fig.add_trace(self.trace_factory.line(spec))
            d_ticks = get_dticks(safe_df, d_col)
            fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
        elif dates:
            d_col = dates[0]
            ensure_columns_exist(context.df, [d_col, value_col])
            safe_df = context.df[[d_col, value_col]].copy()
            safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[d_col])
            spec = CartesianSpec(safe_df[d_col], safe_df[value_col], value_col, select_palette(0), "%{y:.2s}")
            fig.add_trace(self.trace_factory.line(spec))
            d_ticks = get_dticks(safe_df, d_col)
            fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
        else:
            raise ValueError("Line chart requires a datetime axis")

        fig.update_yaxes(title=value_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        return fig

    def build_area(self, context: GraphContext) -> go.Figure:
        nums, cats, dates = self._resolve_axis_cols(context)
        if not nums or not dates:
            raise ValueError("Area chart requires one numerical and one datetime column")

        value_col = nums[0]
        d_col = dates[0]
        fig = go.Figure()

        if cats:
            c_col = cats[0]
            safe_df = context.df[[d_col, c_col, value_col]].copy()
            safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[d_col, c_col])
            for i, group in enumerate(safe_df[c_col].unique()):
                temp = safe_df[safe_df[c_col] == group]
                spec = CartesianSpec(temp[d_col], temp[value_col], str(group), select_palette(i), "%{y:.2s}")
                fig.add_trace(self.trace_factory.area(spec))
        else:
            safe_df = context.df[[d_col, value_col]].copy()
            safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[d_col])
            spec = CartesianSpec(safe_df[d_col], safe_df[value_col], value_col, select_palette(0), "%{y:.2s}")
            fig.add_trace(self.trace_factory.area(spec))

        d_ticks = get_dticks(safe_df, d_col)
        fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
        fig.update_yaxes(title=value_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        return fig

    def build_pie(self, context: GraphContext, hole: float) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or not cats:
            raise ValueError("Pie/Donut chart requires one numerical and one categorical column")

        value_col, label_col = nums[0], cats[0]
        ensure_columns_exist(context.df, [value_col, label_col])
        safe_df = context.df[[label_col, value_col]].dropna(subset=[label_col]).copy()
        colors = [select_palette(i) for i in range(max(3, safe_df.shape[0]))]
        return go.Figure(self.trace_factory.pie(safe_df[label_col], safe_df[value_col], colors, hole=hole))

    def build_pareto(self, context: GraphContext) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or not cats:
            raise ValueError("Pareto chart requires one numerical and one categorical column")

        n_col, c_col = nums[0], cats[0]
        ensure_columns_exist(context.df, [n_col, c_col])
        safe_df = context.df[[c_col, n_col]].copy().sort_values(n_col, ascending=False)
        safe_df["cum_sum"] = safe_df[n_col].cumsum()
        total = safe_df[n_col].sum()
        safe_df["cumulative_percentage"] = (safe_df["cum_sum"] / total * 100).round(2) if total else 0
        average = round(float(safe_df[n_col].mean()), 2) if not safe_df.empty else 0

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        bar_spec = CartesianSpec(safe_df[c_col], safe_df[n_col], n_col, select_palette(0), "%{y:.2s}")
        line_spec = CartesianSpec(safe_df[c_col], safe_df["cumulative_percentage"], "Cumulative Percentage", select_palette(2), "%{y:.2s}")
        fig.add_trace(self.trace_factory.bar(bar_spec), secondary_y=False)
        fig.add_trace(self.trace_factory.line(line_spec), secondary_y=True)

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

    def build_funnel(self, context: GraphContext) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or not cats:
            raise ValueError("Funnel chart requires one numerical and one categorical column")
        n_col, c_col = nums[0], cats[0]
        safe_df = context.df[[c_col, n_col]].copy()
        colors = [select_palette(i) for i in range(safe_df.shape[0])]
        return go.Figure(self.trace_factory.funnel(safe_df[c_col], safe_df[n_col], colors))

    def build_waterfall(self, context: GraphContext) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or not cats:
            raise ValueError("Waterfall chart requires one numerical and one categorical column")
        n_col, c_col = nums[0], cats[0]
        safe_df = context.df[[c_col, n_col]].copy()
        return go.Figure(
            self.trace_factory.waterfall(
                labels=safe_df[c_col],
                values=safe_df[n_col],
                increasing=select_palette(6),
                decreasing=select_palette(11),
                total=select_palette(0),
            )
        )

    def build_combo_bar_line(self, context: GraphContext) -> go.Figure:
        nums, cats, dates = self._resolve_axis_cols(context)
        if len(nums) < 2:
            raise ValueError("Combo chart requires at least two numerical columns")
        n1, n2 = nums[:2]

        if cats:
            axis_col = cats[0]
        elif dates:
            axis_col = dates[0]
        else:
            raise ValueError("Combo chart requires one categorical or datetime axis")

        safe_df = context.df[[axis_col, n1, n2]].copy()
        if dates and axis_col == dates[0]:
            safe_df[axis_col] = pd.to_datetime(safe_df[axis_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[axis_col])

        bar_spec = CartesianSpec(safe_df[axis_col], safe_df[n1], n1, select_palette(0), "%{y:.2s}")
        line_spec = CartesianSpec(safe_df[axis_col], safe_df[n2], n2, select_palette(1), "%{y:.2s}")

        fig = go.Figure()
        fig.add_trace(self.trace_factory.bar(bar_spec))
        fig.add_trace(self.trace_factory.line(line_spec))

        if dates and axis_col == dates[0]:
            d_ticks = get_dticks(safe_df, axis_col)
            fig.update_xaxes(title=axis_col, linewidth=1.2, tick0=safe_df[axis_col].min(), tickformat="%b %Y", dtick=d_ticks)
        else:
            fig.update_xaxes(title=axis_col, linewidth=1.2, tickvals=list(range(safe_df.shape[0])), ticktext=truncate_labels(safe_df[axis_col].tolist(), 20))
        fig.update_yaxes(title=f"{n1} and {n2}", showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_layout(bargap=get_bargap(safe_df[axis_col].nunique()))
        return fig

    def _build_multi_series_bar(self, context: GraphContext, barmode: str, orientation: str = "v") -> go.Figure:
        nums, cats, dates = self._resolve_axis_cols(context)
        if not nums:
            raise ValueError("Bar chart requires at least one numerical column")

        if len(cats) >= 2:
            n_col = nums[0]
            c1, c2 = cats[:2]
            safe_df = context.df[[n_col, c1, c2]].copy()
            primary, secondary = (c1, c2) if safe_df[c1].nunique() >= safe_df[c2].nunique() else (c2, c1)
            totals = safe_df.groupby(primary)[n_col].sum()
            ascending = orientation == "h"
            category_order = totals.sort_values(ascending=ascending).index.tolist() if (barmode == "stack" or orientation == "h") else safe_df[primary].dropna().unique().tolist()

            fig = go.Figure()
            for i, sec in enumerate(safe_df[secondary].dropna().unique()):
                temp = safe_df[safe_df[secondary] == sec].set_index(primary).reindex(category_order).reset_index()
                spec = CartesianSpec(
                    x=temp[primary],
                    y=temp[n_col],
                    name=str(sec),
                    color=select_palette(i),
                    texttemplate="%{y:.2s}" if orientation == "v" else "%{x:.2s}",
                    orientation=orientation,
                )
                trace = self.trace_factory.bar(spec)
                if barmode != "stack":
                    trace.offsetgroup = i + 1
                fig.add_trace(trace)

            if orientation == "v":
                fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
                fig.update_xaxes(title=primary, linewidth=1.2, tickvals=list(range(len(category_order))), ticktext=truncate_labels(category_order, 20))
            else:
                fig.update_xaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
                fig.update_yaxes(title=primary, linewidth=1.2, ticklabelstandoff=10, tickvals=list(range(len(category_order))), ticktext=truncate_labels(category_order, 30))

            fig.update_layout(barmode=barmode, bargap=get_bargap(len(category_order), orientation=orientation))
            return fig

        if cats and dates:
            n_col = nums[0]
            c_col = cats[0]
            d_col = dates[0]
            safe_df = context.df[[n_col, c_col, d_col]].copy()
            safe_df[d_col] = pd.to_datetime(safe_df[d_col], errors="coerce")
            safe_df = safe_df.dropna(subset=[d_col, c_col])

            fig = go.Figure()
            for i, group in enumerate(safe_df[c_col].unique()):
                temp = safe_df[safe_df[c_col] == group]
                spec = CartesianSpec(temp[d_col], temp[n_col], str(group), select_palette(i), "%{y:.2s}")
                trace = self.trace_factory.bar(spec)
                trace.offsetgroup = i + 1
                fig.add_trace(trace)

            d_ticks = get_dticks(safe_df, d_col)
            num_unique = safe_df[d_col].nunique() if barmode == "stack" else safe_df.shape[0]
            fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
            fig.update_xaxes(title=d_col, linewidth=1.2, tick0=safe_df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
            fig.update_layout(barmode=barmode, bargap=get_bargap(num_unique))
            return fig

        if cats or dates:
            return self.build_bar(context)

        raise ValueError("Grouped/Stacked bar requires category/date axis")

    def build_grouped_bar(self, context: GraphContext) -> go.Figure:
        return self._build_multi_series_bar(context, barmode="group", orientation="v")

    def build_stacked_bar(self, context: GraphContext) -> go.Figure:
        return self._build_multi_series_bar(context, barmode="stack", orientation="v")

    def build_treemap(self, context: GraphContext) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or len(cats) < 2:
            raise ValueError("Treemap requires one numerical and two categorical columns")
        n_col = nums[0]
        c1, c2 = cats[:2]
        path = [c1, c2] if context.df[c1].nunique() < context.df[c2].nunique() else [c2, c1]
        return px.treemap(context.df, path=path, values=n_col, color=path[0], color_discrete_sequence=[select_palette(i) for i in range(10)])

    def build_sunburst(self, context: GraphContext) -> go.Figure:
        nums, cats, _ = self._resolve_axis_cols(context)
        if not nums or len(cats) < 2:
            raise ValueError("Sunburst requires one numerical and two categorical columns")
        n_col = nums[0]
        path = cats[:2]
        fig = px.sunburst(context.df, path=path, values=n_col, color_discrete_sequence=[select_palette(i) for i in range(10)])
        fig.update_traces(insidetextorientation="auto")
        return fig
