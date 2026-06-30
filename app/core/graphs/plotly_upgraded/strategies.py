"""Strategy registry for graph generation.

Strategy pattern: each graph type has its own strategy object, making behavior
open for extension while closed for modification.
"""

from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go

from .architecture import FigureComposer, GraphContext, GraphStrategy


@dataclass(frozen=True)
class _NamedStrategy(GraphStrategy):
    name: str

    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        raise NotImplementedError()


class GaugeStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_gauge(context)


class ScatterStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_scatter(context)


class BarStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_bar(context)


class HorizontalBarStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_horizontal_bar(context)


class LineStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_line(context)


class AreaStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_area(context)


class PieStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_pie(context, hole=0.0)


class DonutStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_pie(context, hole=0.5)


class ParetoStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_pareto(context)


class FunnelStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_funnel(context)


class WaterfallStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_waterfall(context)


class ComboBarLineStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_combo_bar_line(context)


class GroupedBarStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_grouped_bar(context)


class StackedBarStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_stacked_bar(context)


class TreemapStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_treemap(context)


class SunburstStrategy(_NamedStrategy):
    def build(self, context: GraphContext, composer: FigureComposer) -> go.Figure:
        return composer.build_sunburst(context)


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, GraphStrategy] = {
            "gauge": GaugeStrategy("gauge"),
            "scatter": ScatterStrategy("scatter"),
            "bar": BarStrategy("bar"),
            "horizontal_bar": HorizontalBarStrategy("horizontal_bar"),
            "line": LineStrategy("line"),
            "area": AreaStrategy("area"),
            "pie": PieStrategy("pie"),
            "donut": DonutStrategy("donut"),
            "pareto": ParetoStrategy("pareto"),
            "funnel": FunnelStrategy("funnel"),
            "waterfall": WaterfallStrategy("waterfall"),
            "combo_bar_line": ComboBarLineStrategy("combo_bar_line"),
            "grouped_bar": GroupedBarStrategy("grouped_bar"),
            "stacked_bar": StackedBarStrategy("stacked_bar"),
            "treemap": TreemapStrategy("treemap"),
            "sunburst": SunburstStrategy("sunburst"),
        }

    def resolve(self, graph_type: str) -> GraphStrategy:
        if graph_type not in self._strategies:
            raise ValueError(f"Unsupported graph type: {graph_type}")
        return self._strategies[graph_type]

    def supported(self) -> list[str]:
        return sorted(self._strategies.keys())
