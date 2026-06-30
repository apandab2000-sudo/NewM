import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from .helper import get_bargap, color_palette, get_dticks

# 2D Charts
def get_2d_scatter_plot(df: pd.DataFrame, num_cols: list):
    fig = go.Figure(
        data=go.Scatter(
            x=df[num_cols[0]],
            y=df[num_cols[1]],
            mode='markers',
            marker_color=color_palette[0]
        )
    )
    fig.update_xaxes(title=num_cols[0], linewidth=1.2, showgrid=False)
    fig.update_yaxes(title=num_cols[1], linewidth=1.2, showline=False, showgrid=True)
    return fig


def get_2d_bar_chart(df: pd.DataFrame, num_cols: list, cat_cols: list = [], date_cols: list = [],
                     orientation: str = "v"):
    if len(cat_cols) > 0:
        primary_col = cat_cols[0]
    else:
        primary_col = date_cols[0]

    tooltip_list = [primary_col]
    fig = go.Figure()

    if orientation == "v":
        hovertemplate = primary_col + "=%{customdata[0]}: <br>" + num_cols[0] + "=%{y}<br><br>"
        fig.add_trace(
            go.Bar(
                x=df[primary_col],
                y=df[num_cols[0]],
                marker_color=color_palette[0],
                # texttemplate="%{y}",
                texttemplate="%{y:.2s}",
                customdata=df[tooltip_list],
                hovertemplate=hovertemplate,
                name="."
            )
        )
        if len(cat_cols) > 0:
            fig.update_xaxes(
                tickvals=list(range(df.shape[0])),
                ticktext=[label if len(label) <= 20 else label[:20] for label in df[primary_col].values.tolist()]
            )
        if len(cat_cols) > 0:
            fig.update_xaxes(title=primary_col, linewidth=1.2)
        else:
            d_ticks = get_dticks(df, date_cols[0])
            fig.update_xaxes(title=date_cols[0], linewidth=1.2, showgrid=False, tick0=df[date_cols[0]].min(),
                             tickformat="%b %Y", dtick=d_ticks)
        fig.update_yaxes(title=num_cols[0], showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    else:
        # Sorting for horizontal graph
        df["dummy"] = df.loc[:, num_cols].sum(axis=1)
        df = df.sort_values("dummy", ascending=True)
        df = df.drop("dummy", axis=1)

        hovertemplate = primary_col + "=%{customdata[0]}: <br>" + num_cols[0] + "=%{x}<br><br>"
        fig.add_trace(
            go.Bar(
                y=df[primary_col],
                x=df[num_cols[0]],
                marker_color=color_palette[0],
                # texttemplate="%{x}",
                texttemplate="%{x:.2s}",
                customdata=df[tooltip_list],
                hovertemplate=hovertemplate,
                orientation="h",
                name="."
            )
        )
        if len(cat_cols) > 0:
            fig.update_yaxes(
                tickvals=list(range(df.shape[0])),
                ticktext=[label if len(label) <= 30 else label[:30] for label in df[primary_col].values.tolist()]
            )
        fig.update_yaxes(title=primary_col, linewidth=1.2, ticklabelstandoff=10)
        fig.update_xaxes(title=num_cols[0], showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        # fig.update_layout(yaxis=dict(autorange="reversed"))
    num_unique = df.shape[0]
    gap = get_bargap(num_unique, orientation=orientation)

    fig.update_layout(bargap=gap)
    return fig


def get_2d_line_chart(df: pd.DataFrame, num_cols: list, date_cols: list, draw_area: bool = False):
    tooltip_list = [date_cols[0]]
    hovertemplate = date_cols[0] + "=%{customdata[0]}: <br>" + num_cols[0] + "=%{y}<br><br>"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df[date_cols[0]],
            y=df[num_cols[0]],
            mode="lines+markers+text",
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            textposition="top center",
            customdata=df[tooltip_list],
            hovertemplate=hovertemplate,
            line=dict(color=color_palette[0], shape="spline"),
            marker=dict(color=color_palette[2]),
            fill="tonexty" if draw_area else None,
            name="."
        )
    )
    d_ticks = get_dticks(df, date_cols[0])
    fig.update_yaxes(title=num_cols[0], showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(title=date_cols[0], linewidth=1.2, showgrid=False, tick0=df[date_cols[0]].min(),
                     tickformat="%b %Y", dtick=d_ticks)
    return fig


def get_pareto_chart(df: pd.DataFrame, numerical_columns: list, categorical_columns: list):
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    df["cum_sum"] = df[numerical_columns[0]].cumsum()
    df["Cumulative Percentage"] = round(df["cum_sum"] / df[numerical_columns[0]].sum() * 100, 2)
    average = round(df[numerical_columns[0]].mean(), 2)

    print(df)

    tooltip_list = [numerical_columns[0], "Cumulative Percentage"]
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=df[categorical_columns[0]],
            y=df[numerical_columns[0]],
            yaxis="y",
            name=numerical_columns[0],
            marker_color=color_palette[0],
            text=df[numerical_columns[0]],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
            customdata=df[tooltip_list],
            hovertemplate=hover_template
        ),
        secondary_y=False
    )
    fig.add_trace(
        go.Scatter(
            x=df[categorical_columns[0]],
            y=df["Cumulative Percentage"],
            yaxis="y2",
            line=dict(shape="spline"),
            mode="lines+markers",
            name="Cumulative Percentage",
            marker_color=color_palette[2],
            text=df["Cumulative Percentage"],
            textposition="top center",
            customdata=df[tooltip_list],
            hovertemplate=hover_template
        ),
        secondary_y=True
    )
    fig.add_hline(
        average,
        annotation_text=f"Avg({numerical_columns[0]}) = {average}",
        line_dash="dash",
        line_color="#666666",
        line_width=2,
        annotation_position="right top"
    )
    fig.update_layout(
        yaxis=dict(title=numerical_columns[0]),
        yaxis2=dict(title="Cumulative Percentage"),
        bargap=gap
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(
        title=categorical_columns[0],
        tickvals=list(range(df.shape[0])),
        ticktext=[label if len(label) <= 20 else label[:20] for label in df[categorical_columns[0]].values.tolist()]
    )
    return fig


def get_2d_pie_chart(df: pd.DataFrame, numerical_columns: list, categorical_columns: list):
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=df[categorical_columns[0]], values=df[numerical_columns[0]], hole=0.5,
                         name=f"{numerical_columns[0]} across {categorical_columns[0]}",
                         marker_colors=color_palette, textinfo='label+percent',
                         textposition="outside",
                         hovertemplate='%{label}<br>Count: %{value}<br>Percent: %{percent}'))
    return fig
