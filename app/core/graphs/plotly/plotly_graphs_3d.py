import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from .helper import get_bargap, color_palette, get_dticks

def get_3d_vertical_bar_chart(df: pd.DataFrame, num_cols: list, cat_cols: list):
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    temp = df.copy()
    n_col_1, n_col_2 = num_cols
    c_col = cat_cols[0]

    tooltip_list = cat_cols + num_cols
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=temp[c_col],
            y=temp[n_col_1],
            offsetgroup=1,
            name=n_col_1,
            marker_color=color_palette[0],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            text=temp[n_col_1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.add_trace(
        go.Bar(
            x=temp[c_col],
            y=temp[n_col_2],
            offsetgroup=2,
            name=n_col_2,
            marker_color=color_palette[1],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            text=temp[n_col_2],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.update_yaxes(
        title=n_col_1 + "<br> and " + n_col_2,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    fig.update_xaxes(
        title=c_col,
        linewidth=1.2,
        tickvals=list(range(temp.shape[0])),
        ticktext=[label if len(label) <= 20 else label[:20] for label in temp[c_col].values.tolist()]
    )
    fig.update_layout(bargap=gap)
    return fig


def get_3d_bar_and_line_chart(df: pd.DataFrame, num_cols: list, cat_cols: list):
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    temp = df.copy()
    n_col_1, n_col_2 = num_cols
    c_col = cat_cols[0]

    tooltip_list = cat_cols + num_cols
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=temp[c_col],
            y=temp[n_col_1],
            name=n_col_1,
            marker_color=color_palette[0],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            text=temp[n_col_1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.add_trace(
        go.Scatter(
            x=temp[c_col],
            y=temp[n_col_2],
            mode='lines+markers',
            line=dict(shape="spline"),
            name=n_col_2, marker_color=color_palette[1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.update_yaxes(
        title=n_col_1 + "<br> and " + n_col_2,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    fig.update_xaxes(
        title=c_col,
        linewidth=1.2,
        tickvals=list(range(temp.shape[0])),
        ticktext=[label if len(label) <= 20 else label[:20] for label in temp[c_col].values.tolist()]
    )
    fig.update_layout(bargap=gap)
    return fig


def get_3d_horizontal_bar_chart(df: pd.DataFrame, num_cols: list, cat_cols: list):
    # Sorting for horizontal graph
    df["dummy"] = df.loc[:, num_cols].sum(axis=1)
    df = df.sort_values("dummy", ascending=True)
    df = df.drop("dummy", axis=1)

    num_unique = df.shape[0]
    gap = get_bargap(num_unique, orientation="h")
    temp = df.copy()
    n_col_1, n_col_2 = num_cols
    c_col = cat_cols[0]

    tooltip_list = cat_cols + num_cols
    hover_main = "%{x}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=temp[c_col],
            x=temp[n_col_1],
            offsetgroup=1,
            name=n_col_1,
            marker_color=color_palette[0],
            # texttemplate="%{x}",
            texttemplate="%{x:.2s}",
            text=temp[n_col_1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template,
            orientation="h"
        )
    )
    fig.add_trace(
        go.Bar(
            y=temp[c_col],
            x=temp[n_col_2],
            offsetgroup=2,
            name=n_col_2,
            marker_color=color_palette[1],
            # texttemplate="%{x}",
            texttemplate="%{x:.2s}",
            text=temp[n_col_2],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template,
            orientation="h"
        )
    )
    fig.update_xaxes(
        title=n_col_1 + "<br> and " + n_col_2,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    fig.update_yaxes(
        title=c_col,
        ticklabelstandoff=10,
        linewidth=1.2,
        tickvals=list(range(temp.shape[0])),
        ticktext=[label if len(label) <= 30 else label[:30] for label in temp[c_col].values.tolist()]
    )
    fig.update_layout(bargap=gap)
    return fig


def get_3d_vertical_bar_chart_date(df: pd.DataFrame, num_cols: list, cat_cols: list = [], date_cols: list = []):
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    temp = df.copy()
    n_col_1, n_col_2 = num_cols
    primary_col = date_cols[0]

    tooltip_list = date_cols + num_cols
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=temp[primary_col],
            y=temp[n_col_1],
            offsetgroup=1,
            name=n_col_1,
            marker_color=color_palette[0],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            text=temp[n_col_1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.add_trace(
        go.Bar(
            x=temp[primary_col],
            y=temp[n_col_2],
            offsetgroup=2,
            name=n_col_2,
            marker_color=color_palette[1],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            text=temp[n_col_1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.update_yaxes(
        title=n_col_1 + "<br> and " + n_col_2,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, primary_col)
    fig.update_xaxes(
        title=primary_col,
        linewidth=1.2,
        tick0=df[date_cols[0]].min(),
        tickformat="%b %Y",
        dtick=d_ticks
    )
    fig.update_layout(bargap=gap)
    return fig


def get_3d_bar_and_line_chart_date(df: pd.DataFrame, num_cols: list, cat_cols: list = [], date_cols: list = []):
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    temp = df.copy()
    n_col_1, n_col_2 = num_cols
    primary_col = date_cols[0]

    tooltip_list = date_cols + num_cols
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=temp[primary_col],
            y=temp[n_col_1],
            name=n_col_1,
            marker_color=color_palette[0],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            text=temp[n_col_1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.add_trace(
        go.Scatter(
            x=temp[primary_col],
            y=temp[n_col_2],
            line=dict(shape="spline"),
            mode="lines+markers",
            name=n_col_2,
            marker_color=color_palette[1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.update_yaxes(
        title=n_col_1 + "<br> and " + n_col_2,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, primary_col)
    fig.update_xaxes(
        title=primary_col,
        linewidth=1.2,
        tick0=df[date_cols[0]].min(),
        tickformat="%b %Y",
        dtick=d_ticks
    )
    return fig


def get_3d_linechart(df: pd.DataFrame, num_cols: list, cat_cols: list = [], date_cols: list = []):
    temp = df.copy()
    n_col_1, n_col_2 = num_cols
    primary_col = date_cols[0]

    tooltip_list = date_cols + num_cols
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=temp[primary_col],
            y=temp[n_col_1],
            name=n_col_1,
            mode='lines+markers',
            line=dict(shape="spline"),
            marker_color=color_palette[0],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.add_trace(
        go.Scatter(
            x=temp[primary_col],
            y=temp[n_col_2],
            name=n_col_2,
            mode='lines+markers',
            line=dict(shape="spline"),
            marker_color=color_palette[1],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template
        )
    )
    fig.update_yaxes(
        title=n_col_1 + "<br> and " + n_col_2,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, primary_col)
    fig.update_xaxes(
        title=primary_col,
        linewidth=1.2,
        tick0=df[date_cols[0]].min(),
        tickformat="%b %Y",
        dtick=d_ticks
    )
    return fig


def get_3d_multiple_lines(df: pd.DataFrame, num_cols: list, cat_cols: list, date_cols: list, draw_area=False):
    d_col = date_cols[0]
    n_col = num_cols[0]
    c_col = cat_cols[0]

    tooltip_list = date_cols + cat_cols + num_cols
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
                marker_color=color_palette[i % len(color_palette)],#color_palette[i % len(color_palette)],#color_palette[i],
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


def get_3d_multiple_bars(df: pd.DataFrame, num_cols: list, cat_cols: list, date_cols: list, barmode="group"):
    if barmode == "stack":
        num_unique = df[date_cols[0]].nunique()
    else:
        num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    temp = df.copy()
    d_col = date_cols[0]
    n_col = num_cols[0]
    c_col = cat_cols[0]

    tooltip_list = date_cols + cat_cols + num_cols
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, j in enumerate(df[c_col].unique()):
        temp = df[df[c_col] == j]
        fig.add_trace(
            go.Bar(
                x=temp[d_col],
                y=temp[n_col],
                # texttemplate="%{y}",
                texttemplate="%{y:.2s}",
                offsetgroup=i + 1,
                text=temp[n_col],
                marker_color=color_palette[i % len(color_palette)],#color_palette[i],
                customdata=temp[tooltip_list],
                hovertemplate=hover_template,
                name=j,
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
    fig.update_layout(bargap=gap, barmode=barmode)
    return fig

def get_3d_cat_bars(df: pd.DataFrame, num_cols: list, cat_cols: list, barmode: str = "group", orientation="v"):
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
    totals = temp.groupby(primary_c_col)[n_col].sum()

    if barmode == "stack" or orientation == "h":
        ascending = orientation == "h"
        categories_order = totals.sort_values(ascending=ascending).index.tolist()
        num_unique = len(categories_order)
    else:
        categories_order = temp[primary_c_col].unique()
        num_unique = temp.shape[0]

    gap = get_bargap(num_unique)
    tooltip_list = cat_cols + num_cols

    fig = go.Figure()

    if orientation == "v":
        hover_main = "%{y}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template = hover_main + hover_template_add.replace("(", "{").replace(")", "}")

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            temp2 = temp2.set_index(primary_c_col).reindex(categories_order).reset_index()
            fig.add_trace(
                go.Bar(
                    x=temp2[primary_c_col],
                    y=temp2[n_col],
                    marker_color=color_palette[i % len(color_palette)],
                    # texttemplate="%{y}",
                    texttemplate="%{y:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    name=j,
                    **({"offsetgroup": i + 1} if barmode != "stack" else {})
                )
            )

        fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_xaxes(
            title=primary_c_col,
            linewidth=1.2,
            tickvals=list(range(len(categories_order))),
            ticktext=[label if len(str(label)) <= 20 else str(label)[:20] for label in categories_order]
        )

    else:
        temp["dummy"] = temp.loc[:, num_cols].sum(axis=1)
        temp = temp.sort_values("dummy", ascending=True).drop("dummy", axis=1)

        hover_main = "%{x}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template = hover_main + hover_template_add.replace("(", "{").replace(")", "}")

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            temp2 = temp2.set_index(primary_c_col).reindex(categories_order).reset_index()
            fig.add_trace(
                go.Bar(
                    y=temp2[primary_c_col],
                    x=temp2[n_col],
                    marker_color=color_palette[i % len(color_palette)],
                    # texttemplate="%{x}",
                    texttemplate="%{x:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    orientation=orientation,
                    name=j,
                    **({"offsetgroup": i + 1} if barmode != "stack" else {})
                )
            )

        fig.update_xaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_yaxes(
            title=primary_c_col,
            linewidth=1.2,
            ticklabelstandoff=10,
            tickvals=list(range(len(categories_order))),
            ticktext=[label if len(str(label)) <= 30 else str(label)[:30] for label in categories_order]
        )

    fig.update_layout(bargap=gap, barmode=barmode)
    return fig

def get_3d_cat_bars1(df: pd.DataFrame, num_cols: list, cat_cols: list, barmode: str = "group", orientation="v"):
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

    # if barmode == "stack":
    #     num_unique = temp[primary_c_col].nunique()
    # else:
    #     num_unique = temp.shape[0]

    totals = temp.groupby(primary_c_col)[n_col].sum()

    if barmode == "stack" or orientation == "h":
        # Sorting required for both stacked and horizontal bars
        ascending = orientation == "h"
        categories_order = totals.sort_values(ascending=ascending).index.tolist()
        num_unique = len(categories_order)
    else:
        # Grouped + vertical bar case (no sorting needed)
        categories_order = temp[primary_c_col].unique()
        num_unique = temp.shape[0]
        
    gap = get_bargap(num_unique)

    tooltip_list = cat_cols + num_cols

    fig = go.Figure()
    if orientation == "v":
        hover_main = "%{y}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
        hover_template = hover_main + hover_template_add

        # for i, j in enumerate(temp[secondary_c_col].unique()):
        #     temp2 = temp[temp[secondary_c_col] == j]
        # categories_order = temp[primary_c_col].unique()

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            # temp2 = temp2.set_index(primary_c_col).loc[categories_order].reset_index()  # Aligning the order
            temp2 = temp2.set_index(primary_c_col).reindex(categories_order).reset_index()
            fig.add_trace(
                go.Bar(
                    x=temp2[primary_c_col],
                    y=temp2[n_col],
                    offsetgroup=i + 1,
                    marker_color=color_palette[i % len(color_palette)],#,
                    # texttemplate="%{y}",
                    texttemplate="%{y:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    name=j
                )
            )

        fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_xaxes(
            title=primary_c_col,
            linewidth=1.2,
            tickvals=list(range(len(categories_order))),
            ticktext=[label if len(str(label)) <= 20 else str(label)[:20] for label in categories_order]
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

        # for i, j in enumerate(temp[secondary_c_col].unique()):
        #     temp2 = temp[temp[secondary_c_col] == j]
        # categories_order = temp[primary_c_col].unique()
        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            temp2 = temp2.set_index(primary_c_col).reindex(categories_order).reset_index()
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
        fig.update_xaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        fig.update_yaxes(
            title=primary_c_col,
            linewidth=1.2,
            ticklabelstandoff=10,
            tickvals=list(range(len(categories_order))),
            ticktext=[label if len(str(label)) <= 30 else str(label)[:30] for label in categories_order]
        )
    fig.update_layout(bargap=gap, barmode=barmode)
    return fig


def get_3d_treemap(df: pd.DataFrame, num_cols: list, cat_cols: list):
    n_col = num_cols[0]
    c_col_1, c_col_2 = cat_cols
    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length < c_col_2_unique_length:
        path = [c_col_1, c_col_2]
    else:
        path = [c_col_2, c_col_1]

    fig = px.treemap(df, path=path, values=n_col, color=path[0], color_discrete_sequence=color_palette)
    fig.update_layout(title=f"{n_col} across {c_col_1} and {c_col_2}")
    return fig

