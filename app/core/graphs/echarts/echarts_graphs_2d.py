import numpy as np
import pandas as pd
from typing import List
from .base_graphs import (
    base_vertical_barchart,
    base_horizontal_barchart,
    base_areachart_datetime,
    base_linechart_datetime,
    base_linechart,
    base_piechart,
    color_palette
)


def get_2d_scatter_plot(df: pd.DataFrame, num_cols: list):
    return None


# Case of 1 categorical and 1 numeirc variable
def get_2d_bar_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str], orientation: str = "v"):
    if orientation == "v":
        chart = base_vertical_barchart(df, cat_cols[0], num_cols[0])
    else:
        chart = base_horizontal_barchart(df, cat_cols[0], num_cols[0])
    return chart

# Case of 1 Datetime and 1 numeric column
def get_2d_line_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str], draw_area: bool = False):
    if draw_area:
        chart = base_areachart_datetime(df, cat_cols[0], num_cols[0])
    else:
        chart = base_linechart_datetime(df, cat_cols[0], num_cols[0])
    return chart

# Case of 1 Categorical and 1 Numeric with Pareto
def get_pareto_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    df = df.sort_values(num_cols[0], ascending=False)
    df["cum_sum"] = df[num_cols[0]].cumsum()
    df["Pareto"] = round(df["cum_sum"] / df[num_cols[0]].sum() * 100, 2)
    
    use_secondary_axis = True
    
    base_graph = base_vertical_barchart(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_linechart(df, cat_cols[0], "Pareto", color=color_palette[8],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["yAxis"][1]["alignTicks"] = True
    return combo


def get_2d_pie_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    return base_piechart(df, cat_cols[0], num_cols[0])
