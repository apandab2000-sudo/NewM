import numpy as np
import pandas as pd
from typing import List
from .base_graphs import (
    base_vertical_barchart,
    base_horizontal_barchart,
    color_palette,
    base_vertical_barchart_datetime,
    base_linechart,
    base_linechart_datetime,
    base_3d_cat_bars,
    base_3d_multiple_bars,
    base_3d_multiple_lines,
    base_treemap
)


def is_secondary_axis_required(df, num_cols: List[str], threshold=5):
    num_col_1 = num_cols[0]
    num_col_2 = num_cols[1]
    
    range1 = df[num_col_1].max() - df[num_col_1].min()
    range2 = df[num_col_2].max() - df[num_col_2].min()

    ratio = max(range1, range2) / max(min(range1, range2), 1)
    use_secondary_axis = ratio > threshold # currently keeping threshshold of 5
    return bool(use_secondary_axis)


# case of 1 categorical and 2 numerical
def get_3d_vertical_bar_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    use_secondary_axis = is_secondary_axis_required(df, num_cols)
    
    base_graph = base_vertical_barchart(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_vertical_barchart(df, cat_cols[0], num_cols[1], color=color_palette[1],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["yAxis"][1]["alignTicks"] = True
    return combo


# case of 1 categorical and 2 numerical - bars represented horizontally
def get_3d_horizontal_bar_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    use_secondary_axis = is_secondary_axis_required(df, num_cols)
    
    base_graph = base_horizontal_barchart(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_horizontal_barchart(df, cat_cols[0], num_cols[1], color=color_palette[1],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["xAxis"][1]["alignTicks"] = True
    return combo  


# case of 1 catgeorical and 2 numerical - 1 numeric represented as line chart
def get_3d_bar_and_line_chart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    use_secondary_axis = is_secondary_axis_required(df, num_cols)
    
    base_graph = base_vertical_barchart(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_linechart(df, cat_cols[0], num_cols[1], color=color_palette[1],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["yAxis"][1]["alignTicks"] = True
    return combo


# case of 1 datetime and 2 numerical
def get_3d_vertical_bar_chart_date(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    use_secondary_axis = is_secondary_axis_required(df, num_cols)
    
    base_graph = base_vertical_barchart_datetime(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_vertical_barchart_datetime(df, cat_cols[0], num_cols[1], color=color_palette[1],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["yAxis"][1]["alignTicks"] = True
    return combo


# case of 1 datetime and 2 numerical - 1 numerical represented as line
def get_3d_bar_and_line_chart_date(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    use_secondary_axis = is_secondary_axis_required(df, num_cols)
    
    base_graph = base_vertical_barchart_datetime(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_linechart_datetime(df, cat_cols[0], num_cols[1], color=color_palette[1],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["yAxis"][1]["alignTicks"] = True
    return combo


# case of 1 datetime and 2 numerical - both numerical represented as line
def get_3d_linechart(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    use_secondary_axis = is_secondary_axis_required(df, num_cols)
    
    base_graph = base_linechart_datetime(df, cat_cols[0], num_cols[0], color=color_palette[0],
        use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    secondary_graph = base_linechart_datetime(df, cat_cols[0], num_cols[1], color=color_palette[1],
        is_base_graph = False, use_secondary_axis=use_secondary_axis, range_end_value=15, multi_axis_graphs=True)
    
    combo = base_graph.overlap(secondary_graph)
    combo.options["labelLayout"] = {"hideOverlap": True}
    combo.options["yAxis"][1]["alignTicks"] = True
    return combo

# case of 1 datetime 1 categorical and 1 numerical - all values represented as barchart
def get_3d_multiple_lines(df: pd.DataFrame, cat_cols: List[str], date_cols: List[str], num_cols: List[str], draw_area=False):
    return base_3d_multiple_lines(df, cat_cols, date_cols, num_cols, draw_area)


# case of 1 datetime 1 categorical and 1 numerical - all values represented as linechart
def get_3d_multiple_bars(df: pd.DataFrame, cat_cols: List[str], date_cols: List[str], num_cols: List[str], barmode="group"):
    return base_3d_multiple_bars(df, cat_cols, date_cols, num_cols, barmode)


# case of 2 categorical and 1 numerical column
def get_3d_cat_bars(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str], barmode: str = "group", orientation="v"):
    return base_3d_cat_bars(df, cat_cols, num_cols, barmode, orientation)


# case of 2 categorical and 1 numerical column
def get_3d_treemap(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    return base_treemap(df, cat_cols, num_cols)