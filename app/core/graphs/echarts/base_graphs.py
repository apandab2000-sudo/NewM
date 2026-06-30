from pyecharts.charts import Bar, Pie, Line, TreeMap
from pyecharts import options as opts
import numpy as np
import pandas as pd
from typing import List
from pyecharts.commons.utils import JsCode

color_palette = [ "#2caffe", "#544fc5", "#00e272", "#fe6a35", "#6b8abc", "#d568fb", "#2ee0ca", "#fa4b42", "#feb56a", "#91e8e1" ]
extended_color_palette = ["#003f5c","#2f4b7c","#665191","#a05195","#d45087","#f95d6a","#ff7c43","#ffa600"]

number_formatter_js_axis = JsCode("""
function(x){
    var v = x;
    if (v > 0) {
        if (v >= 1000000000) return (v / 1000000000).toFixed(0) + 'B';
        if (v >= 1000000) return (v / 1000000).toFixed(0) + 'M';
        if (v >= 1000) return (v / 1000).toFixed(0) + 'K';
        return v.toLocaleString();
    } else {
        if (v <= -1000000000) return (v / 1000000000).toFixed(0) + 'B';
        if (v <= -1000000) return (v / 1000000).toFixed(0) + 'M';
        if (v <= -1000) return (v / 1000).toFixed(0) + 'K';
        return v.toLocaleString();
    }   
}
""".strip())

number_formatter_js_labels = JsCode("""
function(params) {
    var v = params.data;
    if (typeof v === 'object' && v !== null && 'value' in v) {
        v = v.value;
    } else if (Array.isArray(params.data)) {
        v = params.data[1];
    }
    if (v > 0) {
        if (v >= 1000000000) return (v / 1000000000).toFixed(1) + 'B';
        if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
        if (v >= 1000) return (v / 1000).toFixed(1) + 'K';
        return v.toLocaleString();
    } else {
        if (v <= -1000000000) return (v / 1000000000).toFixed(1) + 'B';
        if (v <= -1000000) return (v / 1000000).toFixed(1) + 'M';
        if (v <= -1000) return (v / 1000).toFixed(1) + 'K';
        return v.toLocaleString();
    } 
}
""".strip())

#################### VERTICAL BARCHART #####################################
def base_vertical_barchart(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0], 
                           is_base_graph=True, use_secondary_axis=False, range_end_value=20,
                          multi_axis_graphs = False):

    # Whether to show data zoom axis
    show_data_zoom = True if len(df)>(range_end_value+5) else False

    bar = Bar(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        end_value = int(range_end_value*100/len(df)) # showing only top % values in starting 
        bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "containLabel": True
        }
    else:
        end_value = None
        bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%",
            "bottom": "10%", 
            "containLabel": True
        }

    bar.add_xaxis(df[cat_col].tolist())
    bar.add_yaxis(
        series_name=num_col, 
        y_axis=df[num_col].tolist(),
        yaxis_index=None if is_base_graph else (1 if use_secondary_axis else None),
        category_gap="40%",
        bar_max_width="50%",
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color, 
            border_radius=[3,3,3,3]
        ),
        emphasis_opts=opts.EmphasisOpts(focus="series"),
    )
    if use_secondary_axis and is_base_graph:
        bar.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(
                    color="#666", 
                    formatter=number_formatter_js_axis, 
                    font_size=10
                )
            )
        )
    bar.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross" if use_secondary_axis else "shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=70,
                overflow="truncate"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col if not multi_axis_graphs else None,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
        ) if is_base_graph else None,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            type_="scroll",
            pos_left="left",
            pos_bottom="0%",
            item_height=12,
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=0,
            range_end=end_value,
            min_value_span=2,
            range_mode="value",
            is_show_detail=False
        )
    )
    bar.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    return bar

################# BASE VERTICAL BARCHART DATETIME ###########################
def base_vertical_barchart_datetime(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0], 
                           is_base_graph=True, use_secondary_axis=False, range_end_value=20,
                          multi_axis_graphs = False):

    # Whether to show data zoom axis
    show_data_zoom = True if len(df)>(range_end_value+5) else False

    df = df.sort_values(cat_col)
    df[cat_col] = df[cat_col].dt.date 

    bar = Bar(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        start_value = df.iloc[-30][cat_col]
        bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "containLabel": True
        }
    else:
        start_value = None
        bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "bottom": "10%",
            "containLabel": True
        }
    print(start_value)

    bar.add_xaxis(df[cat_col].tolist())
    bar.add_yaxis(
        series_name=num_col, 
        y_axis=df[num_col].tolist(),
        yaxis_index=None if is_base_graph else (1 if use_secondary_axis else None),
        category_gap="40%",
        bar_max_width="50%",
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color, 
            border_radius=[3,3,3,3]
        ),
        emphasis_opts=opts.EmphasisOpts(focus="series"),
    )
    if use_secondary_axis and is_base_graph:
        bar.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(
                    color="#666", 
                    formatter=number_formatter_js_axis, 
                    font_size=10
                )
            )
        )
    bar.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross" if use_secondary_axis else "shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=70,
                overflow="truncate"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col if not multi_axis_graphs else None,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
        ) if is_base_graph else None,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            pos_left="right",
            item_height=12,
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=None, 
            range_end=None, 
            start_value=start_value, 
            min_value_span=2, 
            is_show_detail=False
        )
    )
    bar.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    return bar


#################### HORIZONTAL BARCHART #####################################
def base_horizontal_barchart(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0], 
                           is_base_graph=True, use_secondary_axis=False, range_end_value=20,
                          multi_axis_graphs = False):

    bar = Bar(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))

    bar.options["grid"] = {
        "left": "5%", 
        "right": "5%", 
        "top": "8%" if not multi_axis_graphs else "15%", 
        "bottom": "10%", 
        "containLabel": True
    }

    max_length = int(df[cat_col].str.len().max())
    name_gap_y = max_length*6+10 # considering each character is of 6px
    
    # Adding Data
    bar.add_xaxis(df[cat_col].tolist()[::-1])
    bar.add_yaxis(
        series_name=num_col, 
        y_axis=df[num_col].tolist(),
        xaxis_index=None if is_base_graph else (1 if use_secondary_axis else None),
        category_gap="40%",
        bar_max_width="50%",
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color, 
            border_radius=[3, 3, 3, 3]
        ),
        emphasis_opts=opts.EmphasisOpts(focus="series"),
    )
    
    if use_secondary_axis and is_base_graph:
        bar.extend_axis(
            xaxis=opts.AxisOpts(
                position="top",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
            )
        )
    bar.reversal_axis()
    # Initializing Basic Bargraph Settings
    bar.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross" if use_secondary_axis else "shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=num_col if not multi_axis_graphs else None,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10),
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee"))
        ),
        yaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=name_gap_y,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=True),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=120,
                overflow="truncate"
            )
        ),
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            type_="scroll",
            pos_left="right",
            item_height=12,
            pos_right="5%"
        ),
    )
    
    bar.set_series_opts(
        label_opts=opts.LabelOpts(position="right", formatter=number_formatter_js_labels, font_size=10, color="#666")
    )
    return bar


####################### LINE CHART ########################################
def base_linechart(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0], 
                           is_base_graph=True, use_secondary_axis=False, range_end_value=20,
                          multi_axis_graphs = False):

    # Whether to show data zoom axis
    show_data_zoom = True if len(df)>(range_end_value+5) else False

    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        end_value = int(range_end_value*100/len(df)) # showing only top % values in starting 
        line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "containLabel": True
        }
    else:
        end_value = None
        line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%",
            "bottom": "10%", 
            "containLabel": True
        }

    line.add_xaxis(df[cat_col].tolist())
    line.add_yaxis(
        series_name=num_col, 
        y_axis=df[num_col].tolist(),
        yaxis_index=None if is_base_graph else (1 if use_secondary_axis else None),
        linestyle_opts=opts.LineStyleOpts(color=color, width=2),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value[1] >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color, 
        ),
        is_smooth=True,
        z=2,
        emphasis_opts=opts.EmphasisOpts(focus="series"),
    )
    if use_secondary_axis and is_base_graph:
        line.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(
                    color="#666", 
                    formatter=number_formatter_js_axis if num_col!="Pareto" else "{value}%", 
                    font_size=10
                )
            )
        )
    line.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross" if use_secondary_axis else "shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=70,
                overflow="truncate"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col if not multi_axis_graphs else None,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False, on_zero_axis_index = 0),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                formatter=number_formatter_js_axis, 
                font_size=10
            )
        ) if is_base_graph else None,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            type_="scroll",
            pos_left="right",
            item_height=12,
            pos_right="5%"
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=0,
            range_end=end_value,
            min_value_span=2,
            range_mode="value",
            is_show_detail=False
        )
    )
    line.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    return line


########################### PIE CHART ######################################
def base_piechart(df: pd.DataFrame, cat_col: str, num_col: str):

    data = [list(z) for z in zip(df[cat_col], df[num_col])]
    avg = df[num_col].mean()

    pie = Pie(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    pie.add(
        series_name=num_col,
        data_pair=data,
        radius=["55%", "80%"],
        center=["50%", "50%"],
        label_opts=opts.LabelOpts(is_show=False, position="center"),
        itemstyle_opts=opts.ItemStyleOpts(
            border_radius=5,
            border_color="#fff",
            border_width=2,
        )
    )
    pie.set_colors(color_palette)
    pie.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="item", 
            axis_pointer_type="shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        legend_opts=opts.LegendOpts(orient="vertical", pos_left="80%", pos_top="center", textstyle_opts=opts.TextStyleOpts(font_size=11)),
        title_opts=opts.TitleOpts(
            title="",
            subtitle=f"Avg\n{avg:,.2f}",
            subtitle_textstyle_opts=opts.TextStyleOpts(
                color="#222",
                font_size=14,
                font_weight="bold",
                align="center"
            ),
            pos_left="center",
            pos_top="center",
        )
    )
    pie.set_series_opts(label_opts=opts.LabelOpts(
        is_show=True,
            position="outside",
            formatter="{b|{b}}\n{d|{d}%}",
            rich={
                "c": {"fontSize": 10, "color": "#666"},
                "d": {"fontSize": 11, "color": "#333", "fontWeight": "bold"}
            },
    ))
    return pie


###################################### LINE CHART - DATETIME ########################################
def base_linechart_datetime(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0], 
                           is_base_graph=True, use_secondary_axis=False, range_end_value=30,
                          multi_axis_graphs = False):

    print("GENERATING LINECHART")
    # Whether to show data zoom axis
    show_data_zoom = True if len(df)>(range_end_value+5) else False

    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))

    df = df.sort_values(cat_col)
    df[cat_col] = pd.to_datetime(df[cat_col]).dt.date
    
    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        start_value = df.iloc[-30][cat_col]
        line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "containLabel": True
        }
    else:
        start_value = None
        line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "bottom": "10%",
            "containLabel": True
        }
    print(start_value)
    
    # Adding Data
    line.add_xaxis(df[cat_col].tolist())
    line.add_yaxis(
        series_name=num_col, 
        y_axis=df[num_col].tolist(),
        yaxis_index=None if is_base_graph else (1 if use_secondary_axis else None),
        linestyle_opts=opts.LineStyleOpts(color=color, width=2),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value[1] >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color, 
        ),
        is_smooth=True,
        z=2,
        emphasis_opts=opts.EmphasisOpts(focus="series")
    )
    if use_secondary_axis and is_base_graph:
        line.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
            )
        )
    
    # Initializing Basic Bargraph Settings
    line.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            type_="time",
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(color="#666", font_size=10),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10),
        ) if is_base_graph else None ,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            type_="scroll",
            pos_left="right",
            item_height=12
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=None, 
            range_end=None, 
            start_value=start_value, 
            min_value_span=2, 
            is_show_detail=False
        )
    )
    line.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    return line

############################## AREA CHART - Datetime ##################################
def base_areachart_datetime(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0], 
                           is_base_graph=True, use_secondary_axis=False, range_end_value=30,
                          multi_axis_graphs = False):

    # Whether to show data zoom axis
    show_data_zoom = True if len(df)>(range_end_value+5) else False

    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))

    df = df.sort_values(cat_col)
    df[cat_col] = pd.to_datetime(df[cat_col]).dt.date
    
    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        start_value = df.iloc[-30][cat_col]
        line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "containLabel": True
        }
    else:
        start_value = None
        line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%" if not multi_axis_graphs else "15%", 
            "bottom": "10%",
            "containLabel": True
        }
    print(start_value)
    
    # Adding Data
    line.add_xaxis(df[cat_col].tolist())
    line.add_yaxis(
        series_name=num_col, 
        y_axis=df[num_col].tolist(),
        yaxis_index=None if is_base_graph else (1 if use_secondary_axis else None),
        linestyle_opts=opts.LineStyleOpts(color=color, width=2),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value[1] >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color, 
        ),
        is_smooth=True,
        z=2,
        emphasis_opts=opts.EmphasisOpts(focus="series"),
        areastyle_opts=opts.AreaStyleOpts(opacity=0.5, color=color_palette[0])
    )
    if use_secondary_axis and is_base_graph:
        line.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
            )
        )
    
    # Initializing Basic Bargraph Settings
    line.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            type_="time",
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(color="#666", font_size=10),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10),
        ) if is_base_graph else None ,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            type_="scroll",
            pos_left="right",
            item_height=12
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=None, 
            range_end=None, 
            start_value=start_value, 
            min_value_span=2, 
            is_show_detail=False
        )
    )
    line.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    return line


def base_3d_cat_bars(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str], barmode="group", orientation="v"):
    num_col = num_cols[0]
    c_col_1, c_col_2 = cat_cols

    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length >= c_col_2_unique_length:
        primary_c_col = c_col_1
        secondary_c_col = c_col_2
    else:
        primary_c_col = c_col_2
        secondary_c_col = c_col_1

    if barmode == "group":
        if orientation == "v":
            range_end_value = max(2, int(20/df[secondary_c_col].nunique()))
        else:
            range_end_value = max(2, int(10/df[secondary_c_col].nunique()))

    if barmode == "stack":
        if orientation == "v":
            range_end_value = 20
        else:
            range_end_value = 10

    max_length = int(df[primary_c_col].str.len().max())
    name_gap_y = max_length*6+10

    show_data_zoom = True if c_col_1_unique_length*c_col_2_unique_length>range_end_value+5 and orientation=="v" else False

    bar = Bar(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        end_value = int(range_end_value*100/len(df)) # showing only top % values in starting 
        bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "15%", 
            "containLabel": True
        }
    else:
        end_value = None
        bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "15%",
            "bottom": "10%", 
            "containLabel": True
        }

    bar.add_xaxis(df[primary_c_col].unique().tolist())

    for i, col in enumerate(df[secondary_c_col].unique().tolist()):
        bar.add_yaxis(
            series_name=col, 
            y_axis=df[df[secondary_c_col]==col][num_col].tolist(),
            category_gap="40%",
            bar_max_width="50%",
            stack="stack1" if not barmode=="group" else None,
            itemstyle_opts=opts.ItemStyleOpts(
                color=color_palette[i], 
                border_radius=[3, 3, 3, 3]
            ),
            emphasis_opts=opts.EmphasisOpts(focus="series"),
        )

    if orientation!="v":
        bar.reversal_axis()

    bar.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=primary_c_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=70,
                overflow="break"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ) if orientation=="v" else opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=num_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10),
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee"))
        ),
        yaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
        ) if orientation=="v" else opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=name_gap_y,
            name=primary_c_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=True),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=120,
                overflow="truncate"
            )
        ),
        legend_opts=opts.LegendOpts(
            is_show=True,
            type_="scroll",
            pos_left="right",
            item_height=12,
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=0,
            range_end=end_value,
            min_value_span=2,
            range_mode="value",
            is_show_detail=False
        )
    )
    bar.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top" if orientation=="v" else "right", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    bar.options["labelLayout"] = {"hideOverlap": True}
    return bar



def base_3d_multiple_bars(df: pd.DataFrame, cat_cols: List[str], dt_cols: List[str], num_cols: List[str], barmode="group"):
    num_col = num_cols[0]
    secondary_c_col = cat_cols[0]
    primary_c_col = dt_cols[0]

    if barmode == "group":
        range_end_value = max(2, int(20/df[secondary_c_col].nunique()))

    if barmode == "stack":
        range_end_value = 20

    show_data_zoom = True if df[primary_c_col].nunique()*df[secondary_c_col].nunique()>range_end_value+5 else False

    bar = Bar(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    
    bar.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "15%",
            "containLabel": True
        }
    
    if show_data_zoom:
        start_value = df.iloc[-30][primary_c_col] if len(df)>30 else df.iloc[0][primary_c_col] 
    else:
        start_value = None
    print(start_value)

    df = df.sort_values(primary_c_col)
    df[primary_c_col] = pd.to_datetime(df[primary_c_col]).dt.date 

    bar.add_xaxis(df[primary_c_col].unique().tolist())

    for i, col in enumerate(df[secondary_c_col].unique().tolist()):
        bar.add_yaxis(
            series_name=col, 
            y_axis=df[df[secondary_c_col]==col][num_col].tolist(),
            category_gap="40%",
            bar_max_width="50%",
            stack="stack1" if not barmode=="group" else None,
            itemstyle_opts=opts.ItemStyleOpts(
                color=color_palette[i], 
                border_radius=[3, 3, 3, 3]
            ),
            emphasis_opts=opts.EmphasisOpts(focus="series"),
        )

    bar.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=primary_c_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=70,
                overflow="break"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
        ),
        legend_opts=opts.LegendOpts(
            is_show=True,
            type_="scroll",
            pos_left="right",
            item_height=12,
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=None, 
            range_end=None, 
            start_value=start_value, 
            min_value_span=2, 
            is_show_detail=False
        )
    )
    bar.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    bar.options["labelLayout"] = {"hideOverlap": True}
    return bar


def base_3d_multiple_lines(df: pd.DataFrame, cat_cols: List[str], dt_cols: List[str], num_cols: List[str], draw_area=False):
    num_col = num_cols[0]
    secondary_c_col = cat_cols[0]
    primary_c_col = dt_cols[0]

    range_end_value = 20

    show_data_zoom = True if df[primary_c_col].nunique()>range_end_value+5 else False

    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    
    line.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "15%", 
            "containLabel": True
        }
    
    if show_data_zoom:
        start_value = df.iloc[-30][primary_c_col]
    else:
        start_value = None
    print(start_value)

    df = df.sort_values(primary_c_col)
    df[primary_c_col] = pd.to_datetime(df[primary_c_col]).dt.date 

    line.add_xaxis(df[primary_c_col].unique().tolist())

    for i, col in enumerate(df[secondary_c_col].unique().tolist()):
        line.add_yaxis(
            series_name=col, 
            y_axis=df[df[secondary_c_col]==col][num_col].tolist(),
            stack="stack1" if draw_area else None,
            itemstyle_opts=opts.ItemStyleOpts(
                color=color_palette[i], 
                border_radius=[3, 3, 3, 3]
            ),
            emphasis_opts=opts.EmphasisOpts(focus="series"),
            areastyle_opts=opts.AreaStyleOpts(opacity=0.4, color=color_palette[i]) if draw_area else None
        )

    line.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis", 
            axis_pointer_type="cross",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            type_="time",
            name_location="middle",
            name_gap=30,
            name=primary_c_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666", 
                font_size=10,
                text_width=70,
                overflow="break"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_rotate=90,
            name_gap=45,
            name=num_col,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
        ),
        legend_opts=opts.LegendOpts(
            is_show=True,
            type_="scroll",
            pos_left="right",
            item_height=12,
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom, 
            range_start=None, 
            range_end=None, 
            start_value=start_value, 
            min_value_span=2, 
            is_show_detail=False
        )
    )
    line.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top", 
            formatter=number_formatter_js_labels, 
            font_size=10, color="#666"
        )
    )
    line.options["labelLayout"] = {"hideOverlap": True}
    return line


def base_treemap(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
    num_col = num_cols[0]
    c_col_1, c_col_2 = cat_cols
    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length>=c_col_2_unique_length:
        primary_c_col = c_col_1
        secondary_c_col = c_col_2
    else:
        primary_c_col = c_col_2
        secondary_c_col = c_col_1
    
    
    treemap_data = []
    for i in df[primary_c_col].unique():
        temp = df[df[primary_c_col]==i]
        treemap_data.append(
            {
                "value": sum(temp[num_col]),
                # "value": len(temp),  # count of records for that category

                "name": i,
                "children": [{"name":k, "value":v} for k, v in zip(temp[secondary_c_col], temp[num_col])]
                # "children": [{"name": k, "value": v} for k, v in temp[secondary_c_col].value_counts().items()]

            }
        )

    treemap = TreeMap(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    
    treemap.options["grid"] = {
            "left": "5%", 
            "right": "5%", 
            "top": "8%", 
            "containLabel": True
        }
    treemap.add(
        series_name = f"{primary_c_col}",
        data = treemap_data,
        levels=[
            opts.TreeMapLevelsOpts(
                treemap_itemstyle_opts=opts.TreeMapItemStyleOpts(
                    border_color="#ddd", border_width=2, gap_width=2
                )
            ),
            opts.TreeMapLevelsOpts(
                color_saturation=[0.3, 0.5],
                treemap_itemstyle_opts=opts.TreeMapItemStyleOpts(
                    border_color_saturation=0.7, gap_width=2, border_width=2
                ),
            )
        ]
        
    )

    treemap.set_global_opts(
        legend_opts=opts.LegendOpts(is_show=False)
    )
    return treemap


############################ base 4d new ###############
def base_vertical_barchart_4d(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0],
                              is_base_graph=True, use_secondary_axis=False, range_end_value=20,
                              multi_axis_graphs=False):
    show_data_zoom = True if len(df) > (range_end_value + 5) else False
    bar = Bar(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
   
    if show_data_zoom:
        end_value = int(range_end_value * 100 / len(df))
        bar.options["grid"] = {
            "left": "5%",
            "right": "5%",
            "top": "8%" if not multi_axis_graphs else "15%",
            "containLabel": True
        }
    else:
        end_value = None
        bar.options["grid"] = {
            "left": "5%",
            "right": "5%",
            "top": "8%" if not multi_axis_graphs else "15%",
            "bottom": "10%",
            "containLabel": True
        }
    bar.add_xaxis(df[cat_col].tolist())  # x axis labels like country names
    bar.add_yaxis(
        series_name=num_col,
        y_axis=df[num_col].tolist(),  # height of bar set
        yaxis_index=0 if is_base_graph else (1 if use_secondary_axis else 0),  # uses primary y-axis
        category_gap="40%",
        bar_max_width="50%",
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color,
            border_radius=[3, 3, 3, 3]
        ),
        emphasis_opts=opts.EmphasisOpts(focus="series"),
    )
    if use_secondary_axis and is_base_graph:
        bar.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(
                    color="#666",
                    formatter=number_formatter_js_axis,
                    font_size=10
                )
            )
        )
    bar.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            axis_pointer_type="cross" if use_secondary_axis else "shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666",
                font_size=10,
                text_width=70,
                overflow="break"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            name_location="middle",
            name_rotate="90",
            name_gap=45,
            name=num_col if not multi_axis_graphs else None,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color="#666", formatter=number_formatter_js_axis, font_size=10)
        ) if is_base_graph else None,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            pos_left="right",
            item_height=12,
            pos_right=100
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom,
            range_start=0,
            range_end=end_value,
            min_value_span=2,
            range_mode="value",
            is_show_detail=False
        )
    )
    bar.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top",
            formatter=number_formatter_js_labels,
            font_size=10, color="#666"
        )
    )
    return bar


def base_linechart_4d(df: pd.DataFrame, cat_col: str, num_col: str, color: str = color_palette[0],
                      is_base_graph=True, use_secondary_axis=False, range_end_value=20,
                      multi_axis_graphs=False):
    # Whether to show data zoom axis
    show_data_zoom = True if len(df) > (range_end_value + 5) else False
    line = Line(init_opts=opts.InitOpts(renderer="svg", width="100%", height="350px", bg_color="#ffffff"))
    if show_data_zoom:
        end_value = int(range_end_value * 100 / len(df))  # showing only top % values in starting
        line.options["grid"] = {
            "left": "5%",
            "right": "5%",
            "top": "8%" if not multi_axis_graphs else "15%",
            "containLabel": True
        }
    else:
        end_value = None
        line.options["grid"] = {
            "left": "5%",
            "right": "5%",
            "top": "8%" if not multi_axis_graphs else "15%",
            "bottom": "10%",
            "containLabel": True
        }
    line.add_xaxis(df[cat_col].tolist())
    line.add_yaxis(
        series_name=num_col,
        y_axis=df[num_col].tolist(),
        yaxis_index=0 if is_base_graph else (1 if use_secondary_axis else 0),
        linestyle_opts=opts.LineStyleOpts(color=color, width=2),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(x) {{return x.value[1] >= 0 ? '{color_palette[0]}' : '{color_palette[7]}';}}") if not multi_axis_graphs else color,
        ),
        is_smooth=True,
        z=2,
        emphasis_opts=opts.EmphasisOpts(focus="series"),
    )
    if use_secondary_axis and is_base_graph:
        line.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(
                    color="#666",
                    formatter=number_formatter_js_axis if num_col != "Pareto" else "{value}%",
                    font_size=10
                )
            )
        )
    line.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            axis_pointer_type="cross" if use_secondary_axis else "shadow",
            textstyle_opts=opts.TextStyleOpts(font_size=10, color="#fff"),
            background_color="#000"
        ),
        xaxis_opts=opts.AxisOpts(
            name_location="middle",
            name_gap=30,
            name=cat_col,
            name_textstyle_opts=opts.TextStyleOpts(font_size=11),
            axislabel_opts=opts.LabelOpts(
                color="#666",
                font_size=10,
                text_width=70,
                overflow="truncate"
            ),
            splitline_opts=opts.SplitLineOpts(is_show=False, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axistick_opts=opts.AxisTickOpts(is_show=False)
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            name_location="middle",
            name_rotate="90",
            name_gap=45,
            name=num_col if not multi_axis_graphs else None,
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color="#eee")),
            axisline_opts=opts.AxisLineOpts(is_show=False, on_zero_axis_index=0),
            axislabel_opts=opts.LabelOpts(
                color="#666",
                formatter=number_formatter_js_axis,
                font_size=10
            )
        ) if is_base_graph else None,
        legend_opts=opts.LegendOpts(
            is_show=True if multi_axis_graphs else False,
            pos_left="right",
            item_height=12,
            pos_right=100,
        ),
        datazoom_opts=opts.DataZoomOpts(
            is_show=show_data_zoom,
            range_start=0,
            range_end=end_value,
            min_value_span=2,
            range_mode="value",
            is_show_detail=False
        )
    )
    line.set_series_opts(
        label_opts=opts.LabelOpts(
            position="top",
            formatter=number_formatter_js_labels,
            font_size=10, color="#666"
        )
    )
    return line