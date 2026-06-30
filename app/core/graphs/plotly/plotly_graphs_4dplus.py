import plotly.graph_objects as go
import pandas as pd
from .helper import get_bargap, color_palette, get_dticks


def get_4d_cat_bars(df: pd.DataFrame, num_cols: list, cat_cols: list, barmode: str = "group",
                    orientation="v", tooltip_list=[]):
    
    n_col = num_cols[0]
    c_col_1, c_col_2 = cat_cols

    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length >= c_col_2_unique_length:
        primary_c_col = c_col_1
        secondary_c_col = c_col_2
    else:
        primary_c_col = c_col_2
        secondary_c_col = c_col_1
    temp = df.copy()

    if barmode == "stack":
        num_unique = temp[primary_c_col].nunique()
    else:
        num_unique = temp.shape[0]
    gap = get_bargap(num_unique)

    fig = go.Figure()
    if orientation == "v":
        hover_main = "%{y}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
        hover_template = hover_main + hover_template_add

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            fig.add_trace(
                go.Bar(
                    x=temp2[primary_c_col],
                    y=temp2[n_col],
                    offsetgroup=i + 1,
                    marker_color=color_palette[i % len(color_palette)],#color_palette[i],
                    # texttemplate="%{y}",
                    texttemplate="%{y:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    name=j
                )
            )

        fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        lables = []
        for i in temp[primary_c_col]:
            if i not in lables:
                lables.append(i)
        fig.update_xaxes(
            title=primary_c_col,
            linewidth=1.2,
            tickvals=list(range(temp[primary_c_col].nunique())),
            ticktext=[label if len(label) <= 20 else label[:20] for label in lables]
        )
    else:
        # Sorting for horizontal graph
        temp["dummy"] = temp.loc[:, num_cols].sum(axis=1)
        temp = temp.sort_values("dummy", ascending=True)
        temp = temp.drop("dummy", axis=1)

        hover_main = "%{x}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
        hover_template = hover_main + hover_template_add

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            fig.add_trace(
                go.Bar(
                    y=temp2[primary_c_col],
                    x=temp2[n_col],
                    offsetgroup=i + 1,
                    marker_color=color_palette[i % len(color_palette)],#color_palette[i],
                    # texttemplate="%{x}",
                    texttemplate="%{x:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    orientation=orientation,
                    name=j
                )
            )
        fig.update_xaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False,
                        ticklen=0)  # need clarification
        lables = []
        for i in temp[primary_c_col]:
            if i not in lables:
                lables.append(i)
        fig.update_yaxes(
            title=primary_c_col,
            linewidth=1.2,
            ticklabelstandoff=10,
            tickvals=list(range(temp[primary_c_col].nunique())),
            ticktext=[label if len(label) <= 30 else label[:30] for label in lables]
        )
    fig.update_layout(bargap=gap, barmode=barmode)
    return fig

def get_4d_multiple_lines(df: pd.DataFrame, num_cols: list, cat_cols: list, date_cols: list,
                          tooltip_list=[], draw_area=False):
    d_col = date_cols[0]
    n_col = num_cols[0]
    c_col = cat_cols[0]

    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, j in enumerate(df[c_col].unique()):
        temp = df[df[c_col] == j]
        fig.add_trace(
            go.Scatter(
                x=temp[d_col],
                y=temp[n_col],
                line=dict(shape="spline"),
                mode="lines+markers",
                marker_color=color_palette[i % len(color_palette)], #color_palette[i],
                customdata=temp[tooltip_list],
                hovertemplate=hover_template,
                name=j,
                fill="tonexty" if draw_area else None
            )
        )
    fig.update_yaxes(
        title=n_col,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(
        title=d_col,
        linewidth=1.2,
        tick0=df[d_col].min(),
        tickformat="%b %Y",
        dtick=d_ticks
    )
    return fig


def get_4d_multiple_lines_multiple_num(df: pd.DataFrame, num_cols: list, date_cols: list, tooltip_list=None):
    temp = df.copy()
    if tooltip_list is None:
        tooltip_list = []

    d_col = date_cols[0]

    hover_main = "%{y}<br><br>"
    hover_template_add = "<br>".join([f"{t}: " + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, n_col in enumerate(num_cols):
        fig.add_trace(go.Scatter(
            x=temp[d_col],
            y=temp[n_col],
            customdata=temp[tooltip_list],
            name=n_col,
            mode='lines+markers',
            line=dict(shape="spline"),
            marker_color=color_palette[i % len(color_palette)],#color_palette[i],
            hovertemplate=hover_template
        ))
    fig.update_yaxes(
        title=num_cols[0] if num_cols else "",
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(
        title=d_col,
        linewidth=1.2,
        tick0=df[d_col].min(),
        tickformat="%b %Y",
        dtick=d_ticks
    )
    return fig


def get_4d_vertical_bar_chart(df: pd.DataFrame, num_cols: list, cat_cols: list = [], date_cols: list = [],
                              barmode: str = "group",
                              tooltip_list=None):
    temp = df.copy()

    if tooltip_list is None:
        tooltip_list = []

    if barmode == "stack":
        num_unique = temp.shape[0]
    else:
        num_unique = temp.shape[0] * len(num_cols)
    gap = get_bargap(num_unique)

    if len(cat_cols) > 0:
        c_col = cat_cols[0]
    else:
        c_col = date_cols[0]

    hover_main = "%{y}<br><br>"
    hover_template_add = "<br>".join([f"{t}: " + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    # Add a trace for each numerical column
    for i, n_col in enumerate(num_cols):
        fig.add_trace(go.Bar(
            x=temp[c_col],
            y=temp[n_col],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template,
            offsetgroup=i + 1,  # Offset groups for side-by-side bars
            name=n_col,
            marker_color=color_palette[i % len(color_palette)],# color_palette[i],
            text=temp[n_col],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
        ))
    fig.update_yaxes(
        title=num_cols[0] if num_cols else "",
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )

    if len(cat_cols) > 0:
        fig.update_xaxes(
            title=c_col,
            linewidth=1.2,
            tickvals=list(range(temp.shape[0])),
            ticktext=[label if len(label) <= 20 else label[:20] for label in temp[c_col].values.tolist()]
        )
    else:
        d_ticks = get_dticks(df, c_col)
        fig.update_xaxes(
            title=c_col,
            linewidth=1.2,
            tick0=df[c_col].min(),
            tickformat="%b %Y",
            dtick=d_ticks
        )
    fig.update_layout(bargap=gap, barmode=barmode)
    return fig


def get_4d_bar_and_line_chart(df: pd.DataFrame, num_cols: list, cat_cols: list = [], date_cols: list = [],
                              tooltip_list=None):
    if tooltip_list is None:
        tooltip_list = []
    temp = df.copy()

    if len(cat_cols) > 0:
        c_col = cat_cols[0]
    else:
        c_col = date_cols[0]

    num_unique = df[c_col].nunique()
    gap = get_bargap(num_unique)

    hover_main = "%{y}<br><br>"
    hover_template_add = "<br>".join([f"{t}: " + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, n_col in enumerate(num_cols):
        if i % 2 == 0:  # Add bar traces for even-indexed columns
            fig.add_trace(
                go.Bar(
                    x=temp[c_col],
                    y=temp[n_col],
                    customdata=temp[tooltip_list],
                    hovertemplate=hover_template,
                    name=n_col,
                    marker_color=color_palette[i % len(color_palette)],#color_palette[i],
                    text=temp[n_col],
                    # texttemplate="%{y}"
                    texttemplate="%{y:.2s}"
                    
                )
            )
        else:  # Add line traces for odd-indexed columns
            fig.add_trace(
                go.Scatter(
                    x=temp[c_col],
                    y=temp[n_col],
                    customdata=temp[tooltip_list],
                    line=dict(shape="spline"),
                    hovertemplate=hover_template,
                    name=n_col,
                    mode='lines+markers',  # 'lines+markers+text'
                    marker_color=color_palette[i % len(color_palette)],#color_palette[i],
                )
            )
    fig.update_yaxes(
        title=num_cols[0] if num_cols else "",
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    if len(cat_cols) > 0:
        fig.update_xaxes(
            title=c_col,
            linewidth=1.2,
            tickvals=list(range(temp.shape[0])),
            ticktext=[label if len(label) <= 20 else label[:20] for label in temp[c_col].values.tolist()]
        )
    else:
        d_ticks = get_dticks(df, c_col)
        fig.update_xaxes(
            title=c_col,
            linewidth=1.2,
            tick0=df[c_col].min(),
            tickformat="%b %Y",
            dtick=d_ticks
        )
    fig.update_layout(bargap=gap)
    return fig
